// promo leaderboard: a live, keyboard-driven terminal view of a squad room.
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const params = new URLSearchParams(location.search);
  const room = (location.pathname.match(/^\/r\/([A-Za-z0-9_.-]{1,40})/) || [])[1]
    || params.get("room") || "global";
  const apiBase = (params.get("api") || window.PROMO_API || location.origin).replace(/\/$/, "");
  const token = params.get("key") || "";
  const endpoint = `${apiBase}/r/${encodeURIComponent(room)}/api${token ? `?key=${encodeURIComponent(token)}` : ""}`;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const POLL_MS = 15000;

  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  const S = {
    snap: null, sort: store.get("promo.sort") || "today", sel: 0, filter: "",
    me: params.get("me") || store.get("promo.me") || "", expanded: "",
    ranks: new Map(), seen: new Set(), demo: false, lastOk: 0, firstFeed: true,
  };

  // ------------------------------------------------------------ formatting
  const pad = (n) => String(n).padStart(2, "0");
  const fmtMin = (m) => {
    m = Math.round(m || 0);
    const h = Math.floor(m / 60), r = m % 60;
    return h && r ? `${h}h ${pad(r)}m` : h ? `${h}h` : `${r}m`;
  };
  const clock = (sec) => {
    sec = Math.max(0, Math.ceil(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  };
  const ago = (t) => {
    const s = Math.max(0, Date.now() / 1000 - t);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  };
  const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const isoWeek = (d) => {
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    const day = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - day);
    const y = t.getUTCFullYear();
    const w = Math.ceil(((t - Date.UTC(y, 0, 1)) / 86400000 + 1) / 7);
    return `${y}-W${pad(w)}`;
  };
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const LABEL = { focus: "Focus", break: "Break", long_break: "Long break" };

  // Members report their own local day; a stale "today" from yesterday must
  // not keep someone on top, so values expire with the calendar.
  function fresh(m, now) {
    const st = m.stats || {};
    const sinceSeen = now - (m.last_seen || 0);
    const today = isoDay(new Date());
    const dayOk = st.day ? st.day === today || (sinceSeen < 43200 &&
      Math.abs(new Date(st.day) - new Date(today)) <= 86400000) : sinceSeen < 86400;
    const weekOk = st.week ? st.week === isoWeek(new Date()) || sinceSeen < 86400 : sinceSeen < 604800;
    return {
      ...m,
      today: dayOk ? st.today_min || 0 : 0,
      week: weekOk ? st.week_min || 0 : 0,
      streak: sinceSeen < 172800 ? st.streak || 0 : 0,
      xp: st.xp || 0,
    };
  }

  function remaining(st, now) {
    if (!st) return 0;
    return st.paused || !st.ends_at ? st.remaining || 0 : st.ends_at - now;
  }

  function describe(e) {
    const who = e.name;
    switch (e.type) {
      case "session": return `${who} finished ${fmtMin(e.minutes)}${e.level ? ` (${e.level})` : ""}`;
      case "achievement": return `${who} unlocked ${e.title}`;
      case "level_up": return `${who} reached ${e.title}`;
      case "kudos": return `${who} sent kudos to ${e.to}`;
      default: return `${who}: ${e.type}`;
    }
  }

  // ------------------------------------------------------------ data
  async function load() {
    if (S.demo) return render(Demo.step());
    try {
      const res = await fetch(endpoint, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const snap = await res.json();
      S.lastOk = Date.now();
      setLive(true);
      render(snap);
    } catch (err) {
      if (!S.snap || S.demo || params.has("demo")) startDemo(err);
      setLive(false);
    }
  }

  function startDemo(err) {
    S.demo = true;
    const b = $("#demo-banner");
    b.hidden = false;
    b.textContent = params.has("demo")
      ? "▲ demo data: a simulated squad, so you can see how the board moves."
      : `▲ can't reach ${endpoint.replace(/\?.*/, "")} (${err.message}). Showing demo data until a promo API is connected.`;
    render(Demo.step());
  }

  function setLive(on) {
    const live = $("#live");
    live.className = `live ${on ? "on" : "off"}`;
    live.textContent = on ? "Live" : S.demo ? "Demo" : "Offline";
  }

  // ------------------------------------------------------------ render
  function render(snap) {
    S.snap = snap;
    S.offset = (snap.now || Date.now() / 1000) - Date.now() / 1000; // server clock - ours
    const now = snap.now || Date.now() / 1000;
    const members = snap.members.map((m) => fresh(m, now));
    const focusing = members.filter((m) => m.online && m.state && m.state.phase === "focus");
    document.title = `${focusing.length ? `(${focusing.length}) ` : ""}promo · ${room}`;
    renderTotals(members, focusing);
    renderNow(members, now);
    renderBoard(members, now);
    renderFeed(snap.events || []);
    status(`${S.demo ? "Demo data" : "Connected"} · ${members.length} developer${members.length === 1 ? "" : "s"} · ${focusing.length} focusing now`);
  }

  function status(text) {
    $("#status-line").textContent = text;
  }

  function renderTotals(members, focusing) {
    $("#total-today").textContent = fmtMin(members.reduce((a, m) => a + m.today, 0));
    $("#total-devs").textContent = members.length;
    $("#total-now").textContent = focusing.length;
    const hot = members.filter((m) => m.online && m.state && m.state.combo >= 2)
      .sort((a, b) => b.state.combo - a.state.combo)[0];
    $("#total-combo").textContent = hot ? `×${hot.state.combo} ${hot.name}` : "—";
  }

  function renderNow(members, now) {
    const list = $("#now");
    list.replaceChildren();
    const active = members.filter((m) => m.online && m.state)
      .sort((a, b) => (a.state.phase !== "focus") - (b.state.phase !== "focus") || remaining(a.state, now) - remaining(b.state, now));
    if (!active.length) {
      list.append(el("li", "none", "Nobody is focusing right now. Start a session and you're first on this screen."));
      return;
    }
    for (const m of active.slice(0, 12)) {
      const st = m.state;
      const li = el("li", `card is-${st.paused ? "paused" : st.phase}`);
      li.dataset.name = m.name;
      const who = el("div", "who");
      const meta = el("span", "meta");
      if (st.combo >= 2) meta.append(el("span", "combo", `×${st.combo}`));
      meta.append(el("span", "phase", st.paused ? "Paused" : LABEL[st.phase]));
      who.append(el("span", "name", m.name), meta);
      const flip = el("div", "timer");
      flip.setAttribute("aria-label", "time left");
      const bar = el("div", "progress");
      bar.append(el("span"));
      const arc = el("span", "arc");
      arc.setAttribute("aria-hidden", "true");
      li.append(arc, who, el("p", "task", st.task ? `“${st.task}”` : st.project || ""), flip, bar);
      li._state = st;
      li._now0 = now;
      list.append(li);
    }
    tickCards(true);
  }

  function tickCards(initial = false) {
    if (!S.snap) return;
    const now = Date.now() / 1000 + (S.offset || 0);
    for (const li of document.querySelectorAll("#now .card")) {
      const st = li._state;
      const left = remaining(st, now);
      const text = clock(left);
      const flip = li.querySelector(".timer");
      const combo = flip.querySelector(".combo");
      const old = flip._text || "";
      if (text !== old) {
        const cells = [];
        [...text].forEach((ch, i) => {
          if (ch === ":") return cells.push(el("i", "", ":"));
          const b = el("b", !initial && !reduced && ch !== old[i] ? "tick" : "", ch);
          cells.push(b);
        });
        flip.replaceChildren(...cells, ...(combo ? [combo] : []));
        flip._text = text;
        flip.setAttribute("aria-label", `${text} left`);
      }
      const pct = st.planned ? Math.min(100, 100 * (1 - Math.max(0, left) / st.planned)) : 0;
      li.querySelector(".progress span").style.width = `${pct}%`;
    }
  }

  const METRIC = {
    today: { label: "Today", noun: " today", val: (m) => m.today, fmt: fmtMin },
    week: { label: "Week", noun: " this week", val: (m) => m.week, fmt: fmtMin },
    streak: { label: "Streak", noun: " streak", val: (m) => m.streak, fmt: (v) => `${v}d` },
    xp: { label: "XP", noun: "", val: (m) => m.xp, fmt: (v) => `${Number(v).toLocaleString()} xp` },
  };

  function rankedList(members) {
    const metric = METRIC[S.sort];
    return members
      .slice()
      .sort((a, b) => metric.val(b) - metric.val(a) || (b.stats.xp || 0) - (a.stats.xp || 0) || a.name.localeCompare(b.name))
      .map((m, i) => ({ ...m, rank: i + 1 }));
  }

  function renderBoard(members, now) {
    const metric = METRIC[S.sort];
    const ranked = rankedList(members);
    const shown = ranked.filter((m) => !S.filter || m.name.toLowerCase().includes(S.filter.toLowerCase()));
    const max = Math.max(1, ...ranked.map(metric.val));
    const tbody = $("#rows");
    tbody.replaceChildren();
    $("#metric-h").textContent = metric.label;
    S.sel = Math.min(S.sel, Math.max(0, shown.length - 1));

    const prev = S.ranks.get(S.sort) || new Map();
    const next = new Map();
    shown.forEach((m, i) => {
      next.set(m.name, m.rank);
      const tr = el("tr", [i === S.sel && "sel", m.name === S.me && "me"].filter(Boolean).join(" "));
      tr.dataset.name = m.name;
      tr.dataset.index = i;
      const was = prev.get(m.name);
      const rank = el("td", `rank${m.rank <= 3 ? " top" : ""}`, String(m.rank).padStart(2, "0"));
      if (was && was !== m.rank) {
        rank.append(el("span", `delta ${was > m.rank ? "up" : "down"}`, `${was > m.rank ? "▲" : "▼"}${Math.abs(was - m.rank)}`));
        tr.classList.add("moved");
      }
      const dev = el("td", "dev", m.name);
      if (m.online) {
        const focusing = m.state && m.state.phase === "focus";
        const dot = el("span", `on${focusing ? "" : " idle"}`);
        dot.title = focusing ? "focusing" : "online";
        dev.append(dot, el("span", "sr-only", focusing ? " (focusing)" : " (online)"));
      }
      if (m.name === S.me) dev.append(el("span", "you-tag", "You"));
      const bar = el("td", "bar-col");
      bar.setAttribute("aria-hidden", "true");
      const track = el("div", "bar");
      const fill = el("span");
      fill.style.width = `${Math.round((metric.val(m) / max) * 100)}%`;
      track.append(fill);
      bar.append(track);
      tr.append(rank, dev, bar, el("td", "num metric", metric.fmt(metric.val(m))),
        el("td", "lvl", m.stats.level || ""), el("td", "num combo-col", `×${m.stats.best_combo || 0}`));
      tbody.append(tr);
      if (S.expanded === m.name) tbody.append(detailRow(m, now));
    });
    S.ranks.set(S.sort, next);

    const empty = $("#empty");
    empty.hidden = shown.length > 0;
    empty.textContent = ranked.length
      ? `No developer matches "${S.filter}".`
      : "This room is empty. Run the two commands below and you'll appear here within a minute.";
    renderYou(ranked, metric);
  }

  function detailRow(m, now) {
    const tr = el("tr", "detail");
    const td = el("td");
    td.colSpan = 6;
    const bits = [
      ["sessions", m.stats.sessions || 0], ["streak", `${m.streak}d`], ["best combo", `×${m.stats.best_combo || 0}`],
      ["xp", (m.xp || 0).toLocaleString()], ["last seen", m.online ? "now" : ago(m.last_seen || 0)],
    ];
    bits.forEach(([k, v], i) => {
      if (i) td.append(" · ");
      td.append(`${k} `, el("b", "", String(v)));
    });
    if (m.state) {
      td.append(" · now ", el("b", "", `${LABEL[m.state.phase].toLowerCase()} ${clock(remaining(m.state, now))}`));
      if (m.state.task) td.append(` on “${m.state.task}”`);
    }
    const btn = el("button", "btn btn-sm", m.name === S.me ? "Not me" : "That's me");
    btn.addEventListener("click", (e) => { e.stopPropagation(); setMe(m.name === S.me ? "" : m.name); });
    td.append(btn);
    tr.append(td);
    return tr;
  }

  function renderYou(ranked, metric) {
    const p = $("#you");
    const me = ranked.find((m) => m.name === S.me);
    if (!S.me) { p.hidden = true; return; }
    p.hidden = false;
    if (!me) {
      p.textContent = `you (${S.me}) aren't in this room yet. join below and start a session.`;
      return;
    }
    const v = metric.val(me);
    if (me.rank === 1) {
      const second = ranked[1];
      p.textContent = second
        ? `you: #1 · ${metric.fmt(v)}${metric.noun} · ${metric.fmt(v - metric.val(second))} ahead of ${second.name}. hold the line.`
        : `you: #1 · ${metric.fmt(v)}${metric.noun}.`;
    } else {
      const above = ranked[me.rank - 2];
      const gap = metric.val(above) - v;
      p.textContent = `you: #${me.rank} · ${metric.fmt(v)}${metric.noun} · ${gap > 0 ? `${metric.fmt(gap)} behind` : "tied with"} ${above.name} (#${above.rank})`;
    }
  }

  function renderFeed(events) {
    const feed = $("#feed");
    const fresh = events.filter((e) => !S.seen.has(`${e.seq}:${e.name}:${e.t}`));
    if (S.firstFeed) {
      feed.replaceChildren();
      events.slice(-40).forEach((e) => feed.prepend(feedItem(e, false)));
      events.forEach((e) => S.seen.add(`${e.seq}:${e.name}:${e.t}`));
      S.firstFeed = false;
    } else {
      fresh.forEach((e) => {
        S.seen.add(`${e.seq}:${e.name}:${e.t}`);
        feed.prepend(feedItem(e, true));
      });
      while (feed.children.length > 60) feed.lastChild.remove();
    }
    if (!feed.children.length) feed.append(el("li", "muted", "Waiting for the first win…"));
  }

  function feedItem(e, isNew) {
    const li = el("li", `k-${e.type}${isNew && !reduced ? " fresh" : ""}`);
    const d = new Date(e.t * 1000);
    const t = el("time", "", `${pad(d.getHours())}:${pad(d.getMinutes())}`);
    t.dateTime = d.toISOString();
    t.title = d.toLocaleString();
    li.append(t, el("span", "ev", describe(e)));
    return li;
  }

  // ------------------------------------------------------------ interaction
  function setSort(sort) {
    if (!METRIC[sort]) return;
    S.sort = sort;
    store.set("promo.sort", sort);
    document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sort === sort)));
    if (S.snap) render(S.snap);
  }

  function setMe(name) {
    S.me = name;
    store.set("promo.me", name || null);
    if (S.snap) render(S.snap);
  }

  function rowsVisible() { return [...document.querySelectorAll("#rows tr:not(.detail)")]; }

  function moveSel(to) {
    const rows = rowsVisible();
    if (!rows.length) return;
    S.sel = Math.max(0, Math.min(rows.length - 1, to));
    rows.forEach((r, i) => r.classList.toggle("sel", i === S.sel));
    rows[S.sel].scrollIntoView({ block: "nearest" });
  }

  function openFilter() {
    $("#filter-wrap").hidden = false;

    $("#filter").focus();
  }

  function closeFilter(clear) {
    if (clear) { S.filter = ""; $("#filter").value = ""; }
    $("#filter-wrap").hidden = !S.filter;

    $("#filter").blur();
    if (S.snap) render(S.snap);
  }

  document.addEventListener("keydown", (e) => {
    if (e.target.id === "filter") {
      if (e.key === "Escape") closeFilter(true);
      if (e.key === "Enter") closeFilter(false);
      return;
    }
    if (e.target.closest("input, textarea, dialog") || e.metaKey || e.ctrlKey || e.altKey) return;
    const rows = rowsVisible();
    const name = rows[S.sel] && rows[S.sel].dataset.name;
    const map = {
      1: () => setSort("today"), 2: () => setSort("week"), 3: () => setSort("streak"), 4: () => setSort("xp"),
      j: () => moveSel(S.sel + 1), ArrowDown: () => moveSel(S.sel + 1),
      k: () => moveSel(S.sel - 1), ArrowUp: () => moveSel(S.sel - 1),
      g: () => moveSel(0), G: () => moveSel(rows.length - 1),
      Enter: () => { S.expanded = S.expanded === name ? "" : name; render(S.snap); },
      m: () => name && setMe(name === S.me ? "" : name),
      "/": () => openFilter(),
      "?": () => $("#help").showModal(),
      Escape: () => closeFilter(true),
    };
    if (map[e.key]) { e.preventDefault(); map[e.key](); }
  });

  $("#filter").addEventListener("input", (e) => { S.filter = e.target.value; S.sel = 0; if (S.snap) render(S.snap); });
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setSort(b.dataset.sort)));
  $("#rows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr:not(.detail)");
    if (!tr) return;
    S.sel = Number(tr.dataset.index);
    S.expanded = S.expanded === tr.dataset.name ? "" : tr.dataset.name;
    render(S.snap);
  });
  document.querySelectorAll(".copy[data-copy]").forEach((btn) => btn.addEventListener("click", async () => {
    const text = $(`#${btn.dataset.copy}`).textContent;
    try { await navigator.clipboard.writeText(text); } catch {
      const r = document.createRange(); r.selectNodeContents($(`#${btn.dataset.copy}`));
      getSelection().removeAllRanges(); getSelection().addRange(r);
    }
    btn.textContent = "Copied";
    btn.classList.add("done");
    setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1600);
  }));

  // ------------------------------------------------------------ boot
  function typeCommand(text, done) {
    const out = $("#cmd");
    if (reduced) { out.textContent = text; return done(); }
    let i = 0;
    const step = () => {
      out.textContent = text.slice(0, ++i);
      if (i < text.length) setTimeout(step, 22 + Math.random() * 30);
      else done();
    };
    step();
  }

  function boot() {
    $("#room-name").textContent = room;
    $("#ghost").textContent = room;
    const url = `${location.origin}/r/${room}`;
    $("#join-cmd").textContent = `promo squad join ${url} --name YOUR_NAME${token ? " --token YOUR_TOKEN" : ""}`;
    document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sort === S.sort)));
    status("connecting…");
    typeCommand(`promo squad --room ${room} --watch`, () => {
      load();
      setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
    });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
    setInterval(() => {
      tickCards();
      if (S.lastOk) $("#updated").textContent = `updated ${Math.round((Date.now() - S.lastOk) / 1000)}s ago`;
      else if (S.demo) $("#updated").textContent = "demo";
    }, 1000);
  }

  // ------------------------------------------------------------ demo squad
  const Demo = (() => {
    const names = ["ada", "linus", "grace", "ken", "margaret", "dennis", "barbara", "guido",
      "anders", "rich", "sandi", "tj", "prime", "yuki"];
    const levels = ["Intern", "Junior Dev", "Mid-level Dev", "Senior Dev", "Staff Engineer",
      "Principal Engineer", "Distinguished Engineer", "10x Engineer", "Blazingly Fast"];
    const tasks = ["fix flaky tests", "ship auth", "refactor parser", "write docs", "", "", "perf pass"];
    let seq = 0, members = null;
    const events = [];
    const rnd = (a, b) => a + Math.random() * (b - a);
    const pick = (a) => a[Math.floor(Math.random() * a.length)];
    const push = (name, ev) => events.push({ seq: ++seq, t: Date.now() / 1000 - rnd(0, 5), name, ...ev });

    function init() {
      const now = Date.now() / 1000;
      members = names.map((name, i) => {
        const xp = Math.round(rnd(80, 9000) / (1 + i * 0.25));
        const online = Math.random() < 0.7;
        const focusing = online && Math.random() < 0.65;
        const planned = pick([25, 30, 45, 50, 60]) * 60;
        return {
          name, online, last_seen: online ? now : now - rnd(3600, 30000),
          state: online ? {
            phase: focusing ? "focus" : pick(["break", "break", "long_break"]),
            paused: false, planned, ends_at: now + rnd(60, focusing ? planned : 400),
            task: focusing ? pick(tasks) : "", combo: Math.floor(rnd(0, 7)),
          } : null,
          stats: {
            today_min: Math.round(rnd(0, 320) / (1 + i * 0.15)), week_min: Math.round(rnd(200, 1800) / (1 + i * 0.1)),
            streak: Math.floor(rnd(0, 30)), xp, sessions: Math.floor(xp / 30),
            best_combo: Math.floor(rnd(1, 12)), level: levels[Math.min(8, Math.floor(Math.sqrt(xp / 150)))],
          },
        };
      });
      for (let i = 0; i < 14; i++) chatter(true);
      events.sort((a, b) => a.t - b.t).forEach((e, i) => { e.seq = i + 1; e.t -= (14 - i) * 240; });
      seq = events.length;
    }

    function chatter(silent) {
      const m = pick(members);
      const r = Math.random();
      if (r < 0.5) push(m.name, { type: "session", minutes: pick([25, 30, 45, 50]), level: pick(["Normal", "Focused", "Flow", "Flow"]) });
      else if (r < 0.7) push(m.name, { type: "achievement", title: pick(["Deep Work", "C-C-C-Combo", "In The Zone", "Ship It", "Night Owl", "On Fire"]) });
      else if (r < 0.85) push(m.name, { type: "kudos", to: pick(members.filter((x) => x !== m)).name });
      else push(m.name, { type: "level_up", title: m.stats.level });
      if (!silent) {
        m.stats.today_min += pick([25, 30, 45]);
        m.stats.xp += Math.round(rnd(20, 70));
      }
    }

    function step() {
      if (!members) init();
      const now = Date.now() / 1000;
      for (const m of members) {
        if (m.state && m.state.ends_at < now) {
          const wasFocus = m.state.phase === "focus";
          m.state = { ...m.state, phase: wasFocus ? "break" : "focus", planned: wasFocus ? 300 : 1500, ends_at: now + (wasFocus ? 300 : 1500) };
          if (wasFocus) { m.stats.today_min += 25; push(m.name, { type: "session", minutes: 25, level: pick(["Focused", "Flow"]) }); }
        }
      }
      if (Math.random() < 0.6) chatter(false);
      return { room, now, cursor: seq, members: JSON.parse(JSON.stringify(members)), events: events.slice(-50) };
    }
    return { step };
  })();

  boot();
})();
