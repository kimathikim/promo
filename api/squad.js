// promo squad API for Vercel: the same protocol as `promo serve`, backed by
// Upstash Redis over its REST API (no npm dependencies).
//
//   GET  /r/<room>/api                 snapshot (members, feed, cursor)
//   POST /r/<room>/api/heartbeat       { name, state, stats, events, since, offline }
//   POST /r/<room>/api/event           { name, events }
//   POST /r/<room>/api/leave           { name }  removes you and your feed items
//   POST /r/<room>/api/moderate        { name, hidden }  needs X-Promo-Admin
//
// Env: KV_REST_API_URL + KV_REST_API_TOKEN (or UPSTASH_REDIS_REST_URL/_TOKEN),
// set automatically when you add Upstash Redis from the Vercel Marketplace.
// Optional PROMO_PRIVATE_ROOMS="team-a:token1,team-b:token2" for private rooms.
// Optional PROMO_ADMIN_TOKEN to hide or unhide members (hide, never delete).
//
// Integrity: an open-source client can't prove its numbers, so the server
// checks them against the clock instead. Today's and this week's minutes can't
// grow faster than wall time since the member's last heartbeat (plus slack).
// Each violation is clamped and counted; at STRIKES the member is hidden from
// everyone else's board but keeps working, so cheating just stops paying.

const crypto = require("crypto");

const NAME_RE = /^[A-Za-z0-9_.-]{1,24}$/;
const ROOM_RE = /^[A-Za-z0-9_.-]{1,40}$/;
const PHASES = new Set(["focus", "break", "long_break"]);
const EVENT_TYPES = new Set(["session", "achievement", "level_up", "kudos"]);
const TITLES = ["Intern", "Junior Dev", "Mid-level Dev", "Senior Dev", "Staff Engineer",
  "Principal Engineer", "Distinguished Engineer", "10x Engineer", "Blazingly Fast"];
const HEARTBEAT = 120;          // seconds between keep-alives we ask clients for
const ONLINE = HEARTBEAT * 2.5; // seen within this window = online
const MAX_BODY = 16 * 1024;
const MAX_MEMBERS = 5000;
const MAX_EVENTS = 300;
const SLACK_MIN = 30;            // allowed drift between client and server clocks
const STRIKES = 3;               // implausible updates before a member is hidden
const RETAIN_DAYS = 90;          // members not seen for this long are removed
const WRITES_PER_MINUTE = 60;    // per IP

// ---------------------------------------------------------------- storage --
function redis() {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return null;
  return async (commands) => {
    const res = await fetch(`${url.replace(/\/$/, "")}/pipeline`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(commands),
    });
    if (!res.ok) throw new Error(`redis ${res.status}`);
    const out = await res.json();
    return out.map((r) => {
      if (r.error) throw new Error(r.error);
      return r.result;
    });
  };
}

// In-memory fallback for local development (`node scripts/dev.js`). On Vercel
// without Redis, data would vanish between invocations, so we refuse instead.
const memory = globalThis.__promoMemory || (globalThis.__promoMemory = {});
function memoryRedis() {
  const h = (k) => (memory[k] = memory[k] || {});
  const ops = {
    HGET: (k, f) => h(k)[f] ?? null,
    HSET: (k, f, v) => { h(k)[f] = v; return 1; },
    HGETALL: (k) => Object.entries(h(k)).flat(),
    HLEN: (k) => Object.keys(h(k)).length,
    HDEL: (k, ...f) => f.filter((x) => delete h(k)[x]).length,
    INCRBY: (k, n) => (memory[k] = (memory[k] || 0) + Number(n)),
    INCR: (k) => (memory[k] = (memory[k] || 0) + 1),
    EXPIRE: () => 1,
    DEL: (k) => (delete memory[k] ? 1 : 0),
    RPUSH: (k, ...v) => { memory[k] = [...(memory[k] || []), ...v]; return memory[k].length; },
    GET: (k) => (memory[k] ?? null),
    LPUSH: (k, ...v) => { memory[k] = [...v.reverse(), ...(memory[k] || [])]; return memory[k].length; },
    LTRIM: (k, a, b) => { memory[k] = (memory[k] || []).slice(a, Number(b) + 1); return "OK"; },
    LRANGE: (k, a, b) => (memory[k] || []).slice(a, Number(b) + 1),
  };
  return async (commands) => commands.map(([cmd, ...args]) => ops[cmd](...args));
}

function db() {
  const r = redis();
  if (r) return r;
  if (process.env.VERCEL) throw Object.assign(new Error(
    "storage not configured: add Upstash Redis to this Vercel project"), { status: 503 });
  return memoryRedis();
}

// ------------------------------------------------------------- validation --
const clip = (v, max, kind = "num") => {
  if (kind === "str") return v == null ? "" : String(v).slice(0, max);
  const n = Number(v);
  return Number.isFinite(n) ? Math.max(0, Math.min(max, kind === "int" ? Math.round(n) : n)) : 0;
};

function cleanState(st) {
  if (!st || typeof st !== "object" || !PHASES.has(st.phase)) return null;
  return {
    phase: st.phase,
    paused: Boolean(st.paused),
    ends_at: st.ends_at ? clip(st.ends_at, 1e10) : null,
    remaining: clip(st.remaining, 86400),
    planned: clip(st.planned, 86400),
    task: clip(st.task, 80, "str"),
    project: clip(st.project, 40, "str"),
    combo: clip(st.combo, 10000, "int"),
  };
}

// Plausibility caps: nobody focuses more than 24h a day.
function cleanStats(st) {
  st = st && typeof st === "object" ? st : {};
  return {
    today_min: clip(st.today_min, 1440),
    week_min: clip(st.week_min, 10080),
    streak: clip(st.streak, 3650, "int"),
    xp: clip(st.xp, 1e7, "int"),
    sessions: clip(st.sessions, 1e6, "int"),
    best_combo: clip(st.best_combo, 10000, "int"),
    level: TITLES.includes(st.level) ? st.level : TITLES[0],
    day: /^\d{4}-\d{2}-\d{2}$/.test(st.day || "") ? st.day : "",
    week: /^\d{4}-W\d{2}$/.test(st.week || "") ? st.week : "",
  };
}

// Clamp minutes that grew faster than the clock allows since the last heartbeat.
function plausible(prev, next, now) {
  const p = prev && prev.stats;
  if (!p || !prev.last_seen) return { stats: next, strike: false };
  const allowed = Math.max(0, (now - prev.last_seen) / 60) + SLACK_MIN;
  const out = { ...next };
  let strike = false;
  for (const [field, period] of [["today_min", "day"], ["week_min", "week"]]) {
    if (p[period] && p[period] === next[period] && out[field] > (p[field] || 0) + allowed) {
      out[field] = Math.round(((p[field] || 0) + allowed) * 10) / 10;
      strike = true;
    }
  }
  return { stats: out, strike };
}

function cleanEvent(ev) {
  if (!ev || typeof ev !== "object" || !EVENT_TYPES.has(ev.type)) return null;
  const out = { type: ev.type };
  for (const k of ["title", "level", "to"]) if (k in ev) out[k] = clip(ev[k], 40, "str");
  for (const k of ["minutes", "commits"]) if (k in ev) out[k] = clip(ev[k], 100000, "int");
  if (ev.type === "kudos" && !NAME_RE.test(out.to || "")) return null;
  return out;
}

const hashKey = (key) => crypto.createHash("sha256").update(String(key)).digest("hex");

function privateToken(room) {
  for (const pair of (process.env.PROMO_PRIVATE_ROOMS || "").split(",")) {
    const [r, t] = pair.split(":");
    if (r && t && r.trim() === room) return t.trim();
  }
  return null;
}

function authorized(req, room, query) {
  const token = privateToken(room);
  if (!token) return true;
  const header = req.headers.authorization || "";
  const supplied = header.startsWith("Bearer ") ? header.slice(7) : (query.get("key") || "");
  const a = Buffer.from(supplied), b = Buffer.from(token);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

// ---------------------------------------------------------------- handlers --
const keys = (room) => ({ m: `promo:${room}:members`, e: `promo:${room}:events`, s: `promo:${room}:seq` });
const fail = (status, message) => Object.assign(new Error(message), { status });

function clientIp(req) {
  const fwd = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
  return fwd || req.headers["x-real-ip"] || req.socket?.remoteAddress || "unknown";
}

async function rateLimit(run, req) {
  const bucket = `promo:rl:${hashKey(clientIp(req)).slice(0, 16)}:${Math.floor(Date.now() / 60000)}`;
  const [count] = await run([["INCR", bucket], ["EXPIRE", bucket, 120]]);
  if (count > WRITES_PER_MINUTE) throw fail(429, "slow down");
}

async function snapshot(run, room, since) {
  const k = keys(room);
  const [flat, events, seq] = await run([["HGETALL", k.m], ["LRANGE", k.e, 0, 99], ["GET", k.s]]);
  const now = Date.now() / 1000;
  const members = [], stale = [], hidden = new Set();
  for (let i = 0; i < (flat || []).length; i += 2) {
    const m = JSON.parse(flat[i + 1]);
    if (now - (m.last_seen || 0) > RETAIN_DAYS * 86400) { stale.push(flat[i]); continue; }
    if (m.hidden) { hidden.add(m.name); continue; }
    const online = !m.offline && now - (m.last_seen || 0) < ONLINE;
    members.push({ name: m.name, online, last_seen: m.last_seen || 0,
      state: online ? m.state : null, stats: m.stats || {} });
  }
  if (stale.length) await run([["HDEL", k.m, ...stale]]);
  members.sort((a, b) => (b.stats.today_min || 0) - (a.stats.today_min || 0));
  const feed = (events || []).map((e) => JSON.parse(e))
    .filter((e) => e.seq > since && !hidden.has(e.name)).reverse();
  return { room, now, cursor: Number(seq || 0), heartbeat: HEARTBEAT, members, events: feed };
}

async function writeEvents(run, room, name, events) {
  const clean = (Array.isArray(events) ? events : []).slice(0, 20).map(cleanEvent).filter(Boolean);
  if (!clean.length) return [];
  const k = keys(room);
  const [last] = await run([["INCRBY", k.s, clean.length]]);
  const now = Date.now() / 1000;
  const stored = clean.map((e, i) => JSON.stringify({ seq: last - clean.length + 1 + i, t: now, name, ...e }));
  return [["LPUSH", k.e, ...stored], ["LTRIM", k.e, 0, MAX_EVENTS - 1]];
}

async function claim(run, room, name, key) {
  // The first client to use a name owns it; later writes must carry the same key.
  const [raw] = await run([["HGET", keys(room).m, name]]);
  const existing = raw ? JSON.parse(raw) : null;
  if (existing && existing.key && existing.key !== hashKey(key || "")) {
    throw Object.assign(new Error(`the name "${name}" is taken in this room`), { status: 403 });
  }
  if (!existing) {
    const [count] = await run([["HLEN", keys(room).m]]);
    if (count >= MAX_MEMBERS) throw Object.assign(new Error("room is full"), { status: 403 });
  }
  return existing;
}

async function heartbeat(run, room, body, memberKey) {
  const name = String(body.name || "");
  if (!NAME_RE.test(name)) throw Object.assign(new Error("invalid name"), { status: 400 });
  const existing = await claim(run, room, name, memberKey);
  const now = Date.now() / 1000;
  const checked = "stats" in body ? plausible(existing, cleanStats(body.stats), now)
    : { stats: existing?.stats || cleanStats({}), strike: false };
  const strikes = (existing?.strikes || 0) + (checked.strike ? 1 : 0);
  const member = {
    name,
    key: existing?.key || (memberKey ? hashKey(memberKey) : null),
    last_seen: now,
    offline: Boolean(body.offline),
    state: cleanState(body.state),
    stats: checked.stats,
    strikes,
    hidden: Boolean(existing?.hidden) || strikes >= STRIKES,
  };
  const writes = [["HSET", keys(room).m, name, JSON.stringify(member)],
    ...(await writeEvents(run, room, name, body.events))];
  await run(writes);
  return snapshot(run, room, clip(body.since, 1e12, "int"));
}

async function postEvents(run, room, body, memberKey) {
  const name = String(body.name || "");
  if (!NAME_RE.test(name)) throw Object.assign(new Error("invalid name"), { status: 400 });
  await claim(run, room, name, memberKey);
  const writes = await writeEvents(run, room, name, body.events);
  if (writes.length) await run(writes);
  return { ok: true };
}

async function leave(run, room, body, memberKey) {
  const name = String(body.name || "");
  if (!NAME_RE.test(name)) throw fail(400, "invalid name");
  const existing = await claim(run, room, name, memberKey);
  if (!existing) return { ok: true, removed: false };
  const k = keys(room);
  const [all] = await run([["LRANGE", k.e, 0, -1]]);
  const keep = (all || []).filter((raw) => {
    const e = JSON.parse(raw);
    return e.name !== name && e.to !== name;
  });
  const writes = [["HDEL", k.m, name], ["DEL", k.e]];
  if (keep.length) writes.push(["RPUSH", k.e, ...keep]);
  await run(writes);
  return { ok: true, removed: true };
}

async function moderate(run, room, body, req) {
  const admin = process.env.PROMO_ADMIN_TOKEN || "";
  const a = Buffer.from(String(req.headers["x-promo-admin"] || "")), b = Buffer.from(admin);
  if (!admin || a.length !== b.length || !crypto.timingSafeEqual(a, b)) throw fail(401, "not an admin");
  const name = String(body.name || "");
  const [raw] = await run([["HGET", keys(room).m, name]]);
  if (!raw) throw fail(404, "no such member");
  const m = JSON.parse(raw);
  m.hidden = Boolean(body.hidden);
  if (!m.hidden) m.strikes = 0;
  await run([["HSET", keys(room).m, name, JSON.stringify(m)]]);
  return { ok: true, name, hidden: m.hidden };
}

async function readBody(req) {
  if (req.body && typeof req.body === "object" && !Buffer.isBuffer(req.body)) return req.body;
  let raw = typeof req.body === "string" ? req.body : Buffer.isBuffer(req.body) ? req.body.toString() : "";
  if (!raw) {
    for await (const chunk of req) {
      raw += chunk;
      if (raw.length > MAX_BODY) break;
    }
  }
  if (raw.length > MAX_BODY) throw Object.assign(new Error("body too large"), { status: 413 });
  let body;
  try { body = JSON.parse(raw || "{}"); } catch { throw Object.assign(new Error("invalid JSON"), { status: 400 }); }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw Object.assign(new Error("expected an object"), { status: 400 });
  }
  return body;
}

module.exports = async function handler(req, res) {
  const url = new URL(req.url, "http://localhost");
  const query = url.searchParams;
  const room = query.get("room") || "global";
  const action = query.get("action") || "";
  const send = (status, body, cache = "no-store") => {
    res.statusCode = status;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", cache);
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Promo-Key");
    res.end(JSON.stringify(body));
  };
  if (req.method === "OPTIONS") return send(204, {});
  if (!ROOM_RE.test(room)) return send(404, { error: "invalid room" });
  if (!authorized(req, room, query)) return send(401, { error: "bad or missing token" });
  try {
    const run = db();
    if (req.method === "GET" && !action) {
      // Viewers poll this; let the CDN absorb them for a few seconds.
      const snap = await snapshot(run, room, clip(query.get("since"), 1e12, "int"));
      return send(200, snap, privateToken(room) ? "no-store" : "public, s-maxage=5, stale-while-revalidate=25");
    }
    const actions = {
      heartbeat: (body, key) => heartbeat(run, room, body, key),
      event: (body, key) => postEvents(run, room, body, key),
      leave: (body, key) => leave(run, room, body, key),
      moderate: (body) => moderate(run, room, body, req),
    };
    if (req.method !== "POST" || !actions[action]) return send(404, { error: "not found" });
    await rateLimit(run, req);
    const body = await readBody(req);
    return send(200, await actions[action](body, req.headers["x-promo-key"] || ""));
  } catch (err) {
    return send(err.status || 500, { error: err.status ? err.message : "server error" });
  }
};

// exported for tests
module.exports.cleanStats = cleanStats;
module.exports.cleanEvent = cleanEvent;
module.exports.plausible = plausible;
