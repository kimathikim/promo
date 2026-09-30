// promo squad API for Vercel: the same protocol as `promo serve`, backed by
// Upstash Redis over its REST API (no npm dependencies).
//
//   GET  /r/<room>/api                 snapshot (members, feed, cursor)
//   POST /r/<room>/api/heartbeat       { name, state, stats, events, since, offline }
//   POST /r/<room>/api/event           { name, events }
//
// Env: KV_REST_API_URL + KV_REST_API_TOKEN (or UPSTASH_REDIS_REST_URL/_TOKEN),
// set automatically when you add Upstash Redis from the Vercel Marketplace.
// Optional PROMO_PRIVATE_ROOMS="team-a:token1,team-b:token2" for private rooms.

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
    INCRBY: (k, n) => (memory[k] = (memory[k] || 0) + Number(n)),
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

async function snapshot(run, room, since) {
  const k = keys(room);
  const [flat, events, seq] = await run([["HGETALL", k.m], ["LRANGE", k.e, 0, 99], ["GET", k.s]]);
  const now = Date.now() / 1000;
  const members = [];
  for (let i = 0; i < (flat || []).length; i += 2) {
    const m = JSON.parse(flat[i + 1]);
    const online = !m.offline && now - (m.last_seen || 0) < ONLINE;
    members.push({ name: m.name, online, last_seen: m.last_seen || 0,
      state: online ? m.state : null, stats: m.stats || {} });
  }
  members.sort((a, b) => (b.stats.today_min || 0) - (a.stats.today_min || 0));
  const feed = (events || []).map((e) => JSON.parse(e)).filter((e) => e.seq > since).reverse();
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
  const member = {
    name,
    key: existing?.key || (memberKey ? hashKey(memberKey) : null),
    last_seen: Date.now() / 1000,
    offline: Boolean(body.offline),
    state: cleanState(body.state),
    stats: "stats" in body ? cleanStats(body.stats) : existing?.stats || cleanStats({}),
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
    if (req.method !== "POST" || !["heartbeat", "event"].includes(action)) {
      return send(404, { error: "not found" });
    }
    const body = await readBody(req);
    const memberKey = req.headers["x-promo-key"] || "";
    const result = action === "heartbeat"
      ? await heartbeat(run, room, body, memberKey)
      : await postEvents(run, room, body, memberKey);
    return send(200, result);
  } catch (err) {
    return send(err.status || 500, { error: err.status ? err.message : "server error" });
  }
};

// exported for tests
module.exports.cleanStats = cleanStats;
module.exports.cleanEvent = cleanEvent;
