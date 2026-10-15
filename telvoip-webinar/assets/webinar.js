/*
 * Telvoip Live: behaviour for all four pages.
 * Connect (index) → Engage (live) → Resolve (replay); confirmed is the
 * resolved ticket in between. No dependencies.
 */
(function () {
  "use strict";

  var W = window.WEBINAR;
  if (!W) return;
  var doc = document.documentElement;
  doc.classList.remove("no-js");
  var page = document.body.getAttribute("data-page");

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function svgEl(tag, attrs) {
    var n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }
  var reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  function calm() { return reduced || doc.hasAttribute("data-saver"); }

  /* ---------- Storage ---------- */

  var store = {
    get: function (k) { try { return JSON.parse(localStorage.getItem("telvoip-live:" + k)); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem("telvoip-live:" + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  var reg = store.get("registrant");
  if (reg && reg.webinar !== W.slug) reg = null;

  /* ---------- Time ---------- */

  var start = new Date(W.startUTC);
  var end = new Date(start.getTime() + W.durationMin * 60000);
  var userTZ = (function () { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return "UTC"; } })();

  function fmt(d, tz, opts) {
    var o = Object.assign({ timeZone: tz }, opts);
    try { return new Intl.DateTimeFormat("en-GB", o).format(d); }
    catch (e) { o.timeZone = "UTC"; return new Intl.DateTimeFormat("en-GB", o).format(d); }
  }
  function hhmm(d, tz) { return fmt(d, tz || userTZ, { hour: "2-digit", minute: "2-digit", hour12: false }); }
  function longDate(d, tz) { return fmt(d, tz || userTZ, { weekday: "long", day: "numeric", month: "long", year: "numeric" }); }
  function shortDate(d, tz) { return fmt(d, tz || userTZ, { weekday: "short", day: "numeric", month: "short" }); }
  function cityOf(tz) {
    var z = W.zones.filter(function (x) { return x.tz === tz; })[0];
    return z ? z.city : (tz.split("/").pop() || tz).replace(/_/g, " ");
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  function mmss(s) { s = Math.max(0, Math.floor(s)); return pad(Math.floor(s / 60)) + ":" + pad(s % 60); }
  function at(min) { return hhmm(new Date(start.getTime() + min * 60000)); }
  function chapterStarts() { var t = 0; return W.agenda.map(function (c) { var s = t; t += c.min; return s; }); }
  function initials(name) {
    return (name || "").split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p[0]; }).join("").toUpperCase() || "?";
  }
  function seeded(seed) {
    var s = seed >>> 0 || 1;
    return function () { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return ((s >>> 0) % 1000) / 1000; };
  }

  /* ---------- Shared renders ---------- */

  function renderShared() {
    $$("[data-text]").forEach(function (n) { var v = W[n.getAttribute("data-text")]; if (v != null) n.textContent = v; });
    $$("[data-zones]").forEach(function (list) {
      list.textContent = "";
      var zones = W.zones.slice();
      if (!zones.some(function (z) { return z.tz === userTZ; })) zones.push({ city: "Your time", tz: userTZ, you: true });
      zones.forEach(function (z) {
        var li = el("li");
        if (z.you || z.tz === userTZ) li.classList.add("you");
        li.appendChild(el("div", "t", hhmm(start, z.tz)));
        li.appendChild(el("div", "c", z.you ? "You · " + cityOf(z.tz) : z.city + (z.tz === userTZ ? " · you" : "")));
        list.appendChild(li);
      });
    });
    $$("[data-when]").forEach(function (n) { n.textContent = shortDate(start) + " · " + hhmm(start) + " " + cityOf(userTZ) + " · " + W.durationMin + " min"; });
    $$("[data-long-when]").forEach(function (n) { n.textContent = longDate(start); });

    var tel = "tel:" + W.tollFree.replace(/[^\d+]/g, "");
    $$("[data-tollfree]").forEach(function (a) { a.href = tel; if (!a.textContent.trim()) a.textContent = W.tollFree; });
    $$("[data-wa]").forEach(function (a) { a.href = "https://wa.me/" + W.whatsappNumber + "?text=" + encodeURIComponent(W.keyword); });
    $$("[data-sms]").forEach(function (a) {
      if (!W.smsNumber) { (a.closest("li") || a).hidden = true; return; }
      a.href = "sms:" + W.smsNumber + "?body=" + encodeURIComponent(W.keyword);
    });
    $$("[data-mail-register]").forEach(function (a) {
      a.href = "mailto:" + W.email + "?subject=" + encodeURIComponent("Register me: " + W.series + ", " + W.shortTitle);
    });
    $$("[data-email]").forEach(function (a) { a.href = "mailto:" + W.email; a.textContent = W.email; });
    $$("[data-demo]").forEach(function (a) { a.href = W.demoUrl; });
    $$("[data-address]").forEach(function (n) { n.textContent = W.address; });
    $$("[data-keyword]").forEach(function (n) { n.textContent = W.keyword; });

    // Journey: Connect is done once you have a seat.
    if (reg) $$('.journey li[data-step="connect"]').forEach(function (li) { li.classList.add("done"); });
  }

  /* ---------- Data saver ---------- */

  function initSaver() {
    var c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    var auto = !!(c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || "")));
    var pref = store.get("saver");
    set(pref == null ? auto : !!pref, false);
    $$("[data-saver-toggle]").forEach(function (b) { b.addEventListener("click", function () { set(!doc.hasAttribute("data-saver"), true); }); });
    function set(on, remember) {
      if (on) doc.setAttribute("data-saver", ""); else doc.removeAttribute("data-saver");
      $$("[data-saver-toggle]").forEach(function (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); });
      if (remember) store.set("saver", on);
      document.dispatchEvent(new CustomEvent("saver", { detail: on }));
    }
  }

  function initMeter() {
    var m = $("[data-meter]");
    if (!m || !window.performance || !performance.getEntriesByType) return;
    function measure() {
      var bytes = 0, nav = performance.getEntriesByType("navigation")[0];
      if (nav) bytes += nav.transferSize || nav.encodedBodySize || 0;
      performance.getEntriesByType("resource").forEach(function (r) { bytes += r.transferSize || r.encodedBodySize || 0; });
      if (!bytes) return;
      var kb = Math.max(1, Math.round(bytes / 1024));
      $(".v", m).textContent = kb + " KB";
      $(".gauge i", m).style.width = Math.min(100, (kb / 2048) * 100).toFixed(1) + "%";
      m.title = "A typical web page weighs about 2 MB. This one: " + kb + " KB.";
    }
    if (document.readyState === "complete") setTimeout(measure, 60);
    else window.addEventListener("load", function () { setTimeout(measure, 60); });
  }

  /* ---------- Calendar + sharing ---------- */

  function stamp(d) { return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); }
  function url(name) { return new URL(name, location.href).href; }
  function calText() { return W.subtitle + "\n\nJoin: " + url("live.html") + "\nListen by phone: " + W.tollFree; }
  function initCalendar() {
    $$("[data-ics]").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.preventDefault();
        var esc = function (s) { return String(s).replace(/[\\,;]/g, "\\$&").replace(/\n/g, "\\n"); };
        var body = [
          "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Telvoip//Telvoip Live//EN", "METHOD:PUBLISH",
          "BEGIN:VEVENT", "UID:" + W.slug + "-" + stamp(start) + "@telvoip.io", "DTSTAMP:" + stamp(new Date()),
          "DTSTART:" + stamp(start), "DTEND:" + stamp(end),
          "SUMMARY:" + esc(W.series + ": " + W.shortTitle), "DESCRIPTION:" + esc(calText()), "LOCATION:" + esc(url("live.html")),
          "BEGIN:VALARM", "TRIGGER:-PT15M", "ACTION:DISPLAY", "DESCRIPTION:" + esc(W.shortTitle + " starts in 15 minutes"), "END:VALARM",
          "END:VEVENT", "END:VCALENDAR",
        ].join("\r\n");
        var a = el("a");
        a.href = URL.createObjectURL(new Blob([body], { type: "text/calendar" }));
        a.download = W.slug + ".ics";
        document.body.appendChild(a); a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      });
    });
    $$("[data-gcal]").forEach(function (a) {
      a.href = "https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + encodeURIComponent(W.series + ": " + W.shortTitle) +
        "&dates=" + stamp(start) + "/" + stamp(end) + "&details=" + encodeURIComponent(calText()) + "&location=" + encodeURIComponent(url("live.html"));
    });
    $$("[data-share-wa]").forEach(function (a) {
      a.href = "https://wa.me/?text=" + encodeURIComponent(W.series + ": " + W.shortTitle + " · " + shortDate(start, "Africa/Nairobi") + ", " +
        hhmm(start, "Africa/Nairobi") + " EAT. Free seat: " + url("./"));
    });
    $$("[data-copy]").forEach(function (b) {
      b.addEventListener("click", function () {
        var link = url("./"), label = b.textContent;
        var ok = function () { b.textContent = "Link copied"; setTimeout(function () { b.textContent = label; }, 1800); };
        if (navigator.clipboard) navigator.clipboard.writeText(link).then(ok, function () { prompt("Copy this link", link); });
        else prompt("Copy this link", link);
      });
    });
  }

  /* ---------- CONNECT 1: the switchboard ---------- */

  function initSwitchboard() {
    var host = $("[data-switchboard]");
    if (!host) return;
    var svg = svgEl("svg", { viewBox: "0 0 560 400", role: "img", "aria-label": "Six channels flowing into one Telvoip dashboard" });
    var core = { x: 372, y: 150, w: 176, h: 100 };
    var paths = {};
    W.channels.forEach(function (c, i) {
      var y = 26 + i * 64;
      var p = svgEl("path", { class: "sb-wire", d: "M138 " + (y + 19) + " C 260 " + (y + 19) + ", 270 200, " + core.x + " 200" });
      svg.appendChild(p);
      paths[c.id] = { path: p, color: c.color };
      var g = svgEl("g", { class: "sb-node" });
      g.appendChild(svgEl("rect", { x: 10, y: y, width: 128, height: 38, rx: 10 }));
      g.appendChild(svgEl("circle", { cx: 28, cy: y + 19, r: 5, fill: c.color }));
      var t = svgEl("text", { x: 42, y: y + 24 });
      t.textContent = c.label;
      g.appendChild(t);
      svg.appendChild(g);
    });
    svg.appendChild(svgEl("path", { class: "sb-out", d: "M460 250 L460 330" }));
    var cg = svgEl("g", { class: "sb-core" });
    cg.appendChild(svgEl("rect", { x: core.x, y: core.y, width: core.w, height: core.h, rx: 18 }));
    var t1 = svgEl("text", { x: core.x + 18, y: core.y + 44 }); t1.textContent = "1 dashboard";
    var t2 = svgEl("text", { x: core.x + 18, y: core.y + 68, class: "sub" }); t2.textContent = "EVERY CONVERSATION";
    cg.appendChild(t1); cg.appendChild(t2);
    svg.appendChild(cg);
    var rg = svgEl("g", { class: "sb-node" });
    rg.appendChild(svgEl("rect", { x: 400, y: 330, width: 120, height: 38, rx: 10 }));
    rg.appendChild(svgEl("circle", { cx: 418, cy: 349, r: 5, fill: "#25D366" }));
    var rt = svgEl("text", { x: 432, y: 354 }); rt.textContent = "Resolved";
    rg.appendChild(rt);
    svg.appendChild(rg);
    $("[data-sb-canvas]", host).appendChild(svg);

    var countEl = $("[data-sb-count]");
    var ticker = $("[data-sb-ticker]");
    var count = 0, i = 0, visible = true, timer = 0;
    var chById = {};
    W.channels.forEach(function (c) { chById[c.id] = c; });

    function land(item) {
      count++;
      countEl.textContent = String(count);
      ticker.textContent = "";
      var tag = el("span", "tag", chById[item.ch].label);
      tag.style.background = chById[item.ch].color;
      ticker.appendChild(tag);
      ticker.appendChild(el("span", "msg", item.text));
    }
    function spawn() {
      if (!visible || document.hidden) return;
      var item = W.traffic[i++ % W.traffic.length];
      if (calm()) { land(item); return; }
      var p = paths[item.ch], len = p.path.getTotalLength();
      var dot = svgEl("circle", { r: 6, fill: p.color, class: "sb-pulse" });
      svg.appendChild(dot);
      var t0 = performance.now(), dur = 1500;
      (function step(now) {
        var k = Math.min(1, (now - t0) / dur);
        var e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        var pt = p.path.getPointAtLength(e * len);
        dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y);
        if (k < 1) requestAnimationFrame(step);
        else { dot.remove(); land(item); }
      })(t0);
    }
    function run() { clearInterval(timer); timer = setInterval(spawn, calm() ? 2600 : 1100); }
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }).observe(host);
    }
    spawn(); run();
    document.addEventListener("saver", run);
  }

  /* ---------- CONNECT 2: register in the unified inbox ---------- */

  function initInbox() {
    var box = $("[data-inbox]");
    if (!box) return;
    var msgs = $("[data-messages]", box);
    var quick = $("[data-quick]", box);
    var form = $("[data-composer]", box);
    var input = $("input", form);
    var sendBtn = $("button", form);
    var errEl = $("[data-composer-error]", box);
    var handleEl = $("[data-handle]", box);
    var answers = { channels: [] };
    var t0 = 0, tick = 0, stepIx = -1, busy = false, turns = 0;

    // The 360 panel starts with what any CRM knows on first contact.
    setField("tz", cityOf(userTZ) + " · " + hhmm(new Date()));
    setField("source", "Webchat · telvoip.io");

    var steps = [
      {
        key: "name",
        ask: function () { return "Hi 👋 you've reached the " + W.series + " desk. I can save you a free seat for “" + W.shortTitle + "”, " + shortDate(start) + " at " + hhmm(start) + " your time. Who am I speaking with?"; },
        placeholder: "Your full name",
        check: function (v) { return v.length < 2 ? "Just your name, so we know who's on the line." : ""; },
        save: function (v) {
          answers.name = v;
          $("[data-p-name]").textContent = v;
          var av = $("[data-p-av]"); av.textContent = initials(v); av.classList.add("filled");
        },
      },
      {
        key: "email",
        ask: function () { return "Karibu, " + answers.name.split(" ")[0] + "! What's your work email? Your seat and the replay go there."; },
        placeholder: "you@company.co.ke", type: "email",
        check: function (v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) ? "" : "That email doesn't look complete."; },
        save: function (v) { answers.email = v; $("[data-p-sub]").textContent = v; setField("email", v); },
      },
      {
        key: "company",
        ask: function () { return "Which company are you with?"; },
        placeholder: "Company name", chips: ["Just me / freelance"],
        check: function (v) { return v ? "" : "Add a company, or tap the chip."; },
        save: function (v) { answers.company = v; setField("company", v); },
      },
      {
        key: "role",
        ask: function () { return "Got it. Which best describes you? I'll route the agenda to the parts that matter for you."; },
        chips: W.roles.map(function (r) { return r.label; }), chipsOnly: true,
        save: function (v) {
          answers.role = v;
          var r = W.roles.filter(function (x) { return x.label === v; })[0];
          answers.roleId = r ? r.id : "";
          setField("role", v);
        },
      },
      {
        key: "channels",
        ask: function () { return "Which channels does your team answer today? Tap all that apply, then Done."; },
        multi: W.channels.map(function (c) { return c.label; }), chipsOnly: true,
        save: function (v) { setField("channels", v); },
      },
      {
        key: "phone",
        ask: function () { return "Want the reminder on WhatsApp? Drop your number with country code, or skip."; },
        placeholder: "+254 7XX XXX XXX", type: "tel", chips: ["Skip"],
        check: function (v) { return v.replace(/\D/g, "").length < 9 ? "Add the full number, with country code." : ""; },
        save: function (v) { answers.phone = v; setField("phone", v + " · WhatsApp"); },
      },
      {
        key: "question",
        ask: function () { return "Last one. Any question for the speakers? Questions sent now are answered first in the Open line."; },
        placeholder: "Ask the speakers…", chips: ["No question"],
        check: function () { return ""; },
        save: function (v) { answers.question = v; },
      },
    ];

    function setField(k, v) {
      var li = $('[data-p-field="' + k + '"]');
      if (!li) return;
      $("b", li).textContent = v || "";
      li.classList.remove("flash"); void li.offsetWidth; li.classList.add("flash");
    }
    function scroll() { msgs.scrollTop = msgs.scrollHeight; }
    function bubble(who, text) {
      var m = el("div", "msg " + who);
      m.appendChild(document.createTextNode(text));
      if (who !== "sys") m.appendChild(el("span", "meta", (who === "me" ? "You" : "Telvoip Live") + " · " + hhmm(new Date())));
      msgs.appendChild(m); scroll();
      return m;
    }
    function botSay(text, then) {
      busy = true;
      var typing = el("div", "msg them typing");
      typing.setAttribute("aria-label", "Typing");
      typing.innerHTML = "<i></i><i></i><i></i>";
      msgs.appendChild(typing); scroll();
      setTimeout(function () { typing.remove(); bubble("them", text); busy = false; if (then) then(); }, calm() ? 150 : 650);
    }
    function lock(on) { input.disabled = on; sendBtn.disabled = on; }

    function ask(i) {
      stepIx = i;
      var s = steps[i];
      quick.textContent = "";
      errEl.textContent = "";
      botSay(s.ask(), function () {
        input.type = s.type || "text";
        input.placeholder = s.placeholder || "Tap an option above";
        input.value = "";
        lock(!!s.chipsOnly);
        if (s.multi) {
          var picked = [];
          s.multi.forEach(function (label) {
            var b = el("button", null, label);
            b.type = "button";
            b.setAttribute("aria-pressed", "false");
            b.addEventListener("click", function () {
              var on = b.getAttribute("aria-pressed") !== "true";
              b.setAttribute("aria-pressed", on ? "true" : "false");
              b.style.background = on ? "var(--purple)" : "";
              b.style.color = on ? "#fff" : "";
              if (on) picked.push(label); else picked.splice(picked.indexOf(label), 1);
            });
            quick.appendChild(b);
          });
          var done = el("button", null, "Done ✓");
          done.type = "button";
          done.addEventListener("click", function () {
            answers.channels = picked.slice();
            reply(picked.length ? picked.join(", ") : "None yet", true);
          });
          quick.appendChild(done);
        } else if (s.chips) {
          s.chips.forEach(function (label) {
            var b = el("button", null, label);
            b.type = "button";
            b.addEventListener("click", function () { reply(label, true); });
            quick.appendChild(b);
          });
        }
        if (!s.chipsOnly) input.focus({ preventScroll: true });
        else { var first = $("button", quick); if (first) first.focus({ preventScroll: true }); }
      });
    }

    function reply(value, fromChip) {
      if (busy || stepIx < 0) return;
      var s = steps[stepIx];
      value = String(value || "").trim();
      var skipping = fromChip && /^(Skip|No question)$/.test(value);
      if (!fromChip && s.check) {
        var err = s.check(value);
        if (err) { errEl.textContent = err; input.focus(); return; }
      }
      if (!t0) startClock();
      turns++;
      input.value = "";
      bubble("me", value);
      if (!skipping) s.save(value);
      quick.textContent = "";
      if (stepIx < steps.length - 1) ask(stepIx + 1);
      else finish();
    }

    function startClock() {
      t0 = Date.now();
      tick = setInterval(function () { handleEl.textContent = mmss((Date.now() - t0) / 1000); }, 1000);
    }

    function finish() {
      clearInterval(tick);
      var secs = Math.max(1, Math.round((Date.now() - t0) / 1000));
      handleEl.textContent = mmss(secs);
      lock(true);
      input.placeholder = "Conversation resolved";
      botSay("You're in, " + answers.name.split(" ")[0] + " 🎉 Closing this ticket and scoring the conversation…", function () {
        bubble("sys", "Ticket resolved · first contact · " + mmss(secs));
        var data = {
          name: answers.name, email: answers.email, company: answers.company || "", role: answers.role || "",
          roleId: answers.roleId || "", channels: answers.channels, phone: answers.phone || "",
          whatsapp: !!answers.phone, question: answers.question || "", tz: userTZ, webinar: W.slug,
          handleSeconds: secs, turns: turns, at: new Date().toISOString(),
        };
        data.ticket = ticketFor(data.email);
        scoreQA(data);
        store.set("registrant", data);
        var go = function () { setTimeout(function () { location.href = "confirmed.html"; }, calm() ? 600 : 2600); };
        if (W.registerEndpoint) {
          fetch(W.registerEndpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
            .then(function (r) { if (!r.ok) throw new Error(r.status); go(); })
            .catch(function () { bubble("them", "Hmm, the line dropped while saving your seat. Check your connection and refresh to try again."); });
        } else go();
      });
    }

    function scoreQA(d) {
      var qa = $("[data-qa]");
      $(".pending", qa).hidden = true;
      $$("[data-qa-row]", qa).forEach(function (r) { r.hidden = false; });
      // Effort: seconds per reply. A plain heuristic, labelled as such in the panel.
      var perTurn = d.handleSeconds / Math.max(1, d.turns);
      var effort = perTurn < 8 ? "Low" : perTurn < 16 ? "Medium" : "High";
      $("[data-qa-fcr]", qa).textContent = "Yes";
      $("[data-qa-time]", qa).textContent = mmss(d.handleSeconds);
      $("[data-qa-effort]", qa).textContent = effort;
      $("[data-qa-sent]", qa).textContent = "Positive";
      setTimeout(function () {
        $("[data-qa-bar-sent]", qa).style.width = "88%";
        $("[data-qa-bar-effort]", qa).style.width = effort === "Low" ? "90%" : effort === "Medium" ? "60%" : "30%";
      }, 50);
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); if (!input.disabled) reply(input.value, false); });
    $$('a[href="#connect"]').forEach(function (a) {
      a.addEventListener("click", function () { begin(); setTimeout(function () { if (!input.disabled) input.focus({ preventScroll: true }); }, 900); });
    });

    var started = false;
    function begin() {
      if (started) return; started = true;
      if (reg) {
        bubble("sys", "Returning customer");
        botSay("Welcome back, " + reg.name.split(" ")[0] + ". You already have a seat (ticket #" + reg.ticket + "). Want to update your details?", function () {
          var b = el("button", null, "Update my details"); b.type = "button";
          b.addEventListener("click", function () { ask(0); });
          var c = el("a", null, "See my seat →"); c.href = "confirmed.html"; c.className = "btn small";
          quick.appendChild(b); quick.appendChild(c);
          lock(true);
          $("[data-p-name]").textContent = reg.name; $("[data-p-sub]").textContent = reg.email;
          var av = $("[data-p-av]"); av.textContent = initials(reg.name); av.classList.add("filled");
          setField("email", reg.email); setField("company", reg.company); setField("role", reg.role);
          setField("channels", (reg.channels || []).join(", ")); if (reg.phone) setField("phone", reg.phone + " · WhatsApp");
        });
      } else {
        bubble("sys", "New conversation · Webchat");
        ask(0);
      }
    }
    lock(true);
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { begin(); io.disconnect(); } }, { threshold: 0.35 });
      io.observe(box);
    } else begin();
  }

  function ticketFor(s) {
    var h = 0;
    for (var i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return "TL-" + String(1000 + (h % 9000));
  }

  /* ---------- CONNECT 3: route the agenda ---------- */

  function initRouter() {
    var flow = $("[data-flow]");
    if (!flow) return;
    var starts = chapterStarts();
    var longest = Math.max.apply(null, W.agenda.map(function (c) { return c.min; }));
    var items = W.agenda.map(function (c, i) {
      var li = el("li");
      li.appendChild(el("div", "node", at(starts[i])));
      var card = el("div", "card");
      var head = el("header");
      head.appendChild(el("h3", null, c.title));
      head.appendChild(el("span", "len", c.min + " min"));
      card.appendChild(head);
      card.appendChild(el("p", null, c.body));
      if (c.speaker != null) card.appendChild(el("div", "by", "With " + W.speakers[c.speaker].name));
      var bar = el("div", "bar"); var fill = el("i"); fill.style.width = (c.min / longest * 100) + "%"; bar.appendChild(fill);
      card.appendChild(bar);
      li.appendChild(card);
      flow.appendChild(li);
      return li;
    });
    var who = $("[data-who]");
    var result = $("[data-route-result]");
    var buttons = W.roles.map(function (r, i) {
      var b = el("button");
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      b.appendChild(el("b", null, String(i + 1)));
      b.appendChild(document.createTextNode(r.label));
      b.addEventListener("click", function () { route(b.getAttribute("aria-pressed") === "true" ? null : r.id); });
      who.insertBefore(b, result);
      return { b: b, id: r.id };
    });
    function route(id) {
      buttons.forEach(function (x) { x.b.setAttribute("aria-pressed", x.id === id ? "true" : "false"); });
      flow.classList.toggle("routed", !!id);
      if (!id) { result.textContent = "Pick one and the agenda lights up the segments built for you."; items.forEach(function (li) { li.className = ""; }); return; }
      var mins = 0, picks = [];
      W.agenda.forEach(function (c, i) {
        var on = c.for.indexOf(id) >= 0;
        items[i].className = on ? "on" : "off";
        if (on) { mins += c.min; picks.push(at(starts[i]) + " " + c.title); }
      });
      result.textContent = "";
      result.appendChild(document.createTextNode("Routed. Your must-watch: "));
      result.appendChild(el("b", null, picks.join(" · ")));
      result.appendChild(document.createTextNode(" (" + mins + " of " + W.durationMin + " min)."));
    }
    route(reg && reg.roleId ? reg.roleId : null);
    var range = $("[data-flow-range]");
    if (range) range.textContent = at(0) + "–" + at(W.durationMin) + " " + cityOf(userTZ) + " time";
  }

  /* ---------- Proof ---------- */

  function initProof() {
    var mq = $("[data-clients]");
    if (mq) {
      var track = el("div", "track");
      W.clients.concat(W.clients).forEach(function (c, i) {
        var s = el("span", null, c);
        if (i >= W.clients.length) s.setAttribute("aria-hidden", "true");
        track.appendChild(s);
      });
      mq.appendChild(track);
    }
    var box = $("[data-results]");
    if (box) {
      var fills = [];
      W.results.forEach(function (r) {
        var a = el("article", "result");
        a.appendChild(el("span", "who-tag", r.who));
        a.appendChild(el("span", "metric", r.metric));
        var mp = el("div", "meter-pair");
        var max = Math.max(r.from, r.to);
        [["Before", r.from, "before"], ["After", r.to, "after"]].forEach(function (row) {
          var d = el("div", row[2]);
          d.appendChild(el("span", null, row[0]));
          var tr = el("span", "track"); var f = el("i", "fill"); tr.appendChild(f); d.appendChild(tr);
          var label = r.unit === "sec" ? mmss(row[1]).replace(/^0/, "")
            : row[2] === "before" ? "baseline" : (r.to > r.from ? "+" : "−") + Math.abs(r.to - r.from) + "%";
          d.appendChild(el("b", null, label));
          mp.appendChild(d);
          fills.push({ el: f, w: row[1] / max * 100 });
        });
        a.appendChild(mp);
        a.appendChild(el("p", null, r.note));
        box.appendChild(a);
      });
      var fire = function () { fills.forEach(function (f) { f.el.style.width = f.w + "%"; }); };
      if ("IntersectionObserver" in window && !calm()) {
        var io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { fire(); io.disconnect(); } }, { threshold: 0.3 });
        io.observe(box);
      } else fire();
    }
    var q = $("[data-quote]");
    if (q) {
      $("blockquote", q).textContent = W.testimonial.quote;
      $("figcaption", q).textContent = W.testimonial.name + " · Telvoip customer";
    }
  }

  function renderTriad() {
    var box = $("[data-triad]");
    if (!box) return;
    var glyphs = [
      '<svg class="glyph" viewBox="0 0 100 100" aria-hidden="true"><path d="M80 50a30 30 0 1 1-9-21.4M80 18v14H66" fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      '<svg class="glyph" viewBox="0 0 100 100" aria-hidden="true"><path d="M10 80 40 50 60 65 90 25M70 25h20v20" fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      '<svg class="glyph" viewBox="0 0 100 100" aria-hidden="true"><path d="M50 12l11 24 26 3-19 18 5 26-23-13-23 13 5-26-19-18 26-3z" fill="currentColor"/></svg>',
    ];
    W.outcomes.forEach(function (o, i) {
      var a = el("article");
      a.innerHTML = glyphs[i % 3];
      a.appendChild(el("span", "n", "Revenue moment 0" + (i + 1)));
      a.appendChild(el("div", "word", o.word));
      a.appendChild(el("h3", null, o.title));
      a.appendChild(el("p", null, o.body));
      box.appendChild(a);
    });
  }

  function renderAgents() {
    var box = $("[data-agents]");
    if (!box) return;
    W.speakers.forEach(function (s) {
      var a = el("article", "agent-card");
      var top = el("div", "top");
      top.appendChild(el("div", "ini", initials(s.name)));
      var t = el("div"); t.appendChild(el("h3", null, s.name)); t.appendChild(el("div", "role", s.role));
      top.appendChild(t);
      a.appendChild(top);
      var sk = el("div", "skills", "Routing skills ");
      (s.skills || []).forEach(function (k) { sk.appendChild(el("span", null, k)); });
      a.appendChild(sk);
      var local = el("div", "local");
      var left = el("span", null, s.city + " · ");
      var now = el("b"); now.setAttribute("data-now", s.tz); left.appendChild(now);
      local.appendChild(left);
      var st = el("span"); st.setAttribute("data-status", s.tz); local.appendChild(st);
      a.appendChild(local);
      box.appendChild(a);
    });
    function tickNow() {
      var n = new Date();
      $$("[data-now]").forEach(function (b) { b.textContent = hhmm(n, b.getAttribute("data-now")); });
      $$("[data-status]").forEach(function (s) {
        var h = parseInt(fmt(n, s.getAttribute("data-status"), { hour: "2-digit", hour12: false }), 10);
        var on = h >= 8 && h < 18;
        s.textContent = on ? "Available" : "Off shift";
        s.closest(".agent-card").querySelector(".ini").classList.toggle("on", on);
      });
    }
    tickNow(); setInterval(tickNow, 30000);
  }

  function renderFAQ() {
    var box = $("[data-faq]");
    if (!box) return;
    W.faq.forEach(function (f) {
      var d = el("details"); d.appendChild(el("summary", null, f.q)); d.appendChild(el("p", null, f.a)); box.appendChild(d);
    });
  }

  /* ---------- Confirmed: the resolved ticket ---------- */

  function initConfirmed() {
    if (page !== "confirmed") return;
    var first = reg ? reg.name.split(" ")[0] : "";
    $("[data-greet]").textContent = first ? "Resolved, " + first + "." : "Resolved.";
    $$("[data-tid]").forEach(function (n) { n.textContent = "#" + (reg ? reg.ticket : "TL-····"); });
    $("[data-t-name]").textContent = reg ? reg.name + (reg.company ? " · " + reg.company : "") : "Guest";
    $("[data-t-date]").textContent = longDate(start);
    $("[data-t-time]").textContent = hhmm(start) + "–" + hhmm(end) + " " + cityOf(userTZ);
    $("[data-t-africa]").textContent = hhmm(start, "Africa/Nairobi") + " EAT · " + hhmm(start, "Africa/Lagos") + " WAT";
    $("[data-t-handle]").textContent = reg ? mmss(reg.handleSeconds) + " · " + reg.turns + " replies" : "-";
    if (reg) $("[data-sent-to]").textContent = reg.email;
    if (reg && reg.whatsapp) $("[data-wa-note]").textContent = " Reminders will also reach WhatsApp on " + reg.phone + ".";

    var tl = $("[data-timeline]");
    var closed = reg ? new Date(reg.at) : new Date();
    var opened = reg ? new Date(closed.getTime() - reg.handleSeconds * 1000) : closed;
    var rows = [["Conversation opened on Webchat", opened], ["Customer 360° profile created", opened]];
    if (reg && reg.roleId) rows.push(["Agenda routed: " + reg.role, closed]);
    if (reg && reg.question) rows.push(["Question queued for the Open line", closed]);
    rows.push(["Seat confirmed · ticket resolved", closed]);
    rows.forEach(function (r) {
      var li = el("li"); li.appendChild(el("span", null, r[0])); li.appendChild(el("time", null, hhmm(r[1]))); tl.appendChild(li);
    });

    if (reg && reg.question) { var q = $("[data-queued]"); q.hidden = false; $("q", q).textContent = reg.question; }

    var csat = $("[data-csat]");
    var out = $("output", csat);
    var saved = store.get("csat");
    for (var i = 1; i <= 5; i++) (function (n) {
      var b = el("button", null, String(n)); b.type = "button";
      b.setAttribute("aria-label", n + " out of 5");
      b.setAttribute("aria-pressed", saved === n ? "true" : "false");
      b.addEventListener("click", function () {
        $$("button", csat).forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true"); store.set("csat", n);
        out.textContent = n >= 4 ? "Thanks. Logged." : "Thanks. Tell us what to fix at the Open line.";
      });
      csat.insertBefore(b, out);
    })(i);

    var done = store.get("checklist") || {};
    $$("[data-check]").forEach(function (c) {
      var k = c.getAttribute("data-check");
      c.checked = !!done[k];
      c.addEventListener("change", function () { done[k] = c.checked; store.set("checklist", done); });
    });
  }

  /* ---------- ENGAGE: live room ---------- */

  function liveState() {
    var forced = new URLSearchParams(location.search).get("state");
    if (/^(pre|live|ended)$/.test(forced || "")) return forced;
    var now = Date.now();
    if (now < start.getTime() - 5 * 60000) return "pre";
    if (now < end.getTime() + 15 * 60000) return "live";
    return "ended";
  }

  function initLive() {
    if (page !== "live") return;
    var state = liveState();
    var badge = $("[data-live-badge]");
    var screen = $("[data-screen]");
    var msg = $("[data-screen-msg]");
    $("[data-stage-when]").textContent = shortDate(start) + " · " + hhmm(start) + " " + cityOf(userTZ);

    if (state === "pre") {
      badge.textContent = "Waiting room";
      $("[data-countdown]").hidden = false;
      var tickCd = function () {
        var s = Math.max(0, Math.floor((start.getTime() - Date.now()) / 1000));
        $("[data-cd=d]").textContent = pad(Math.floor(s / 86400));
        $("[data-cd=h]").textContent = pad(Math.floor(s % 86400 / 3600));
        $("[data-cd=m]").textContent = pad(Math.floor(s % 3600 / 60));
        $("[data-cd=s]").textContent = pad(s % 60);
      };
      tickCd(); setInterval(tickCd, 1000);
    } else if (state === "live") {
      badge.textContent = "Live"; badge.classList.add("live");
      if (W.streamEmbedUrl && !doc.hasAttribute("data-saver")) {
        var f = el("iframe"); f.src = W.streamEmbedUrl; f.title = W.shortTitle + " live stream";
        f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen"; screen.appendChild(f);
      } else {
        msg.hidden = false;
        $("h2", msg).textContent = W.streamEmbedUrl ? "Audio-only mode" : "The stream connects here";
        $("p", msg).textContent = W.streamEmbedUrl
          ? "Data saver is on, so video is off. Call " + W.tollFree + " to listen."
          : "Set streamEmbedUrl in assets/config.js. Until then, call " + W.tollFree + " to listen.";
      }
    } else {
      badge.textContent = "Ended";
      msg.hidden = false;
      $("h2", msg).textContent = "Call ended. Ticket resolved.";
      $("p", msg).textContent = "";
      var a = el("a", null, "Open the replay and AI report →"); a.href = "replay.html";
      $("p", msg).appendChild(a);
    }

    var ro = $("[data-runorder]");
    var starts = chapterStarts();
    var nowMin = (Date.now() - start.getTime()) / 60000;
    W.agenda.forEach(function (c, i) {
      var li = el("li");
      if ((state === "live" && nowMin >= starts[i] && nowMin < starts[i] + c.min) || (state !== "live" && i === 0)) li.className = "now";
      li.appendChild(el("time", null, at(starts[i])));
      li.appendChild(el("span", null, c.title));
      ro.appendChild(li);
    });

    // Speaker test: a generated ringback tone, nothing downloaded.
    var test = $("[data-sound-test]");
    test.addEventListener("click", function () {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { test.textContent = "No audio"; return; }
      var ctx = new AC(), g = ctx.createGain(), t = ctx.currentTime;
      g.gain.value = 0.0001; g.connect(ctx.destination);
      [440, 480].forEach(function (fq) { var o = ctx.createOscillator(); o.frequency.value = fq; o.connect(g); o.start(); o.stop(t + 2.2); });
      g.gain.exponentialRampToValueAtTime(0.12, t + 0.05); g.gain.setValueAtTime(0.12, t + 0.9);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 1.0); g.gain.setValueAtTime(0.0001, t + 1.2);
      g.gain.exponentialRampToValueAtTime(0.12, t + 1.25); g.gain.setValueAtTime(0.12, t + 2.1);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 2.2);
      test.setAttribute("aria-pressed", "true"); test.textContent = "Ringing…";
      setTimeout(function () { test.textContent = "Heard it ✓"; ctx.close(); }, 2300);
    });

    $$("[data-react]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (calm()) return;
        var f = el("span", "floaty", b.textContent);
        f.style.left = (b.offsetLeft + 8) + "px";
        b.parentNode.appendChild(f);
        setTimeout(function () { f.remove(); }, 1700);
      });
    });

    // Q&A as an omnichannel inbox, ranked by votes.
    var chans = {}; W.channels.forEach(function (c) { chans[c.id] = c; });
    var list = $("[data-queue]");
    var qs = store.get("queue") || [
      { id: "s1", ch: "whatsapp", text: "Can AI QA score calls in Swahili as well as English?", who: "Sample · Support lead, Nairobi", votes: 14 },
      { id: "s2", ch: "webchat", text: "How do you move a WhatsApp chat to a voice call without losing history?", who: "Sample · CX manager, Lagos", votes: 9 },
      { id: "s3", ch: "email", text: "Which CRMs does the dialer connect to out of the box?", who: "Sample · Sales ops, Kampala", votes: 6 },
    ];
    if (reg && reg.question && !qs.some(function (q) { return q.id === "reg"; })) {
      qs.push({ id: "reg", ch: "webchat", text: reg.question, who: "You · sent at registration", votes: 1, mine: true, voted: true });
    }
    function draw() {
      qs.sort(function (a, b) { return b.votes - a.votes; });
      list.textContent = "";
      qs.forEach(function (q) {
        var c = chans[q.ch] || chans.webchat;
        var li = el("li"); if (q.mine) li.className = "mine";
        var body = el("div");
        var from = el("div", "from");
        var tag = el("i", null, c.label); tag.style.background = c.color;
        from.appendChild(tag); from.appendChild(el("b", null, q.who));
        body.appendChild(from); body.appendChild(el("div", null, q.text));
        li.appendChild(body);
        var v = el("button", "vote", "▲ " + q.votes); v.type = "button";
        v.setAttribute("aria-pressed", q.voted ? "true" : "false");
        v.setAttribute("aria-label", (q.voted ? "Remove vote, " : "Vote up, ") + q.votes + " votes");
        v.addEventListener("click", function () { q.voted = !q.voted; q.votes += q.voted ? 1 : -1; store.set("queue", qs); draw(); });
        li.appendChild(v);
        list.appendChild(li);
      });
      $("[data-queue-count]").textContent = qs.length + " in queue";
    }
    draw();
    $("[data-ask]").addEventListener("submit", function (e) {
      e.preventDefault();
      var i = $("input", e.target), t = i.value.trim();
      if (!t) return;
      qs.push({ id: "q" + Date.now(), ch: "webchat", text: t, who: "You · just now", votes: 1, mine: true, voted: true });
      store.set("queue", qs); i.value = ""; draw();
    });
  }

  /* ---------- RESOLVE: replay as an AI QA report ---------- */

  function initReplay() {
    if (page !== "replay") return;
    var total = W.durationMin * 60, pos = 0, playing = false, timer = 0;
    var starts = chapterStarts().map(function (m) { return m * 60; });
    var svg = $("[data-sentiment]");
    var Wd = 600, H = 120, n = 60;
    var r = seeded(424242), v = 0.5, pts = [];
    for (var i = 0; i <= n; i++) {
      v = Math.max(0.12, Math.min(0.95, v * 0.7 + (0.35 + r() * 0.5) * 0.3 + (i / n) * 0.06));
      pts.push([i / n * Wd, H - 10 - v * (H - 24)]);
    }
    function pathD(p) {
      var d = "M" + p[0][0] + " " + p[0][1];
      for (var k = 1; k < p.length; k++) {
        var mx = (p[k - 1][0] + p[k][0]) / 2;
        d += " C" + mx + " " + p[k - 1][1] + " " + mx + " " + p[k][1] + " " + p[k][0] + " " + p[k][1];
      }
      return d;
    }
    var defs = svgEl("defs", {});
    var grad = svgEl("linearGradient", { id: "sentFill", x1: 0, y1: 0, x2: 0, y2: 1 });
    grad.appendChild(svgEl("stop", { offset: "0%", "stop-color": "#FF5C00", "stop-opacity": ".45" }));
    grad.appendChild(svgEl("stop", { offset: "100%", "stop-color": "#FF5C00", "stop-opacity": "0" }));
    defs.appendChild(grad); svg.appendChild(defs);
    svg.setAttribute("viewBox", "0 0 " + Wd + " " + H);
    svg.setAttribute("preserveAspectRatio", "none");
    var line = pathD(pts);
    svg.appendChild(svgEl("path", { d: line + " L" + Wd + " " + H + " L0 " + H + " Z", fill: "url(#sentFill)" }));
    svg.appendChild(svgEl("path", { d: line, class: "line", "vector-effect": "non-scaling-stroke" }));
    starts.forEach(function (s, k) {
      if (k === 0) return;
      var x = s / total * Wd;
      svg.appendChild(svgEl("line", { x1: x, x2: x, y1: 0, y2: H, class: "chap", "vector-effect": "non-scaling-stroke" }));
    });
    var head = svgEl("line", { x1: 0, x2: 0, y1: 0, y2: H, class: "head", "vector-effect": "non-scaling-stroke" });
    svg.appendChild(head);

    var legend = $("[data-legend]");
    W.agenda.forEach(function (c) { legend.appendChild(el("span", null, c.title)); });

    var posEl = $("[data-pos]"), play = $("[data-play]"), nowCh = $("[data-now-chapter]");
    var list = $("[data-moments]"), items = [];
    W.agenda.forEach(function (c, k) {
      var li = el("li"), b = el("button"); b.type = "button";
      b.appendChild(el("time", null, mmss(starts[k])));
      var d = el("span");
      d.appendChild(el("b", null, c.title));
      d.appendChild(document.createTextNode(c.body));
      if (c.speaker != null) d.appendChild(el("span", "spk", W.speakers[c.speaker].name));
      b.appendChild(d);
      b.addEventListener("click", function () { seek(starts[k]); });
      li.appendChild(b); list.appendChild(li); items.push(b);
    });

    function draw() {
      var x = pos / total * Wd;
      head.setAttribute("x1", x); head.setAttribute("x2", x);
      posEl.textContent = mmss(pos) + " / " + mmss(total);
      var ch = 0; starts.forEach(function (s, k) { if (pos >= s) ch = k; });
      items.forEach(function (b, k) { b.setAttribute("aria-current", k === ch ? "true" : "false"); });
      nowCh.textContent = W.agenda[ch].title;
      svg.setAttribute("aria-valuenow", String(Math.floor(pos)));
      svg.setAttribute("aria-valuetext", mmss(pos) + ", " + W.agenda[ch].title);
    }
    function seek(s) { pos = Math.max(0, Math.min(total, s)); draw(); }
    function toggle() {
      playing = !playing;
      play.setAttribute("aria-label", playing ? "Pause" : "Play");
      $("[data-icon-play]", play).hidden = playing; $("[data-icon-pause]", play).hidden = !playing;
      clearInterval(timer);
      if (playing) timer = setInterval(function () { seek(pos + 10); if (pos >= total) toggle(); }, 250);
    }
    play.addEventListener("click", toggle);
    svg.addEventListener("click", function (e) { var b = svg.getBoundingClientRect(); seek((e.clientX - b.left) / b.width * total); });
    svg.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") { seek(pos + 15); e.preventDefault(); }
      if (e.key === "ArrowLeft") { seek(pos - 15); e.preventDefault(); }
    });

    $$("[data-size-audio]").forEach(function (n) { n.textContent = W.replayAudioSizeMB + " MB"; });
    $$("[data-size-video]").forEach(function (n) { n.textContent = W.replayVideoSizeMB + " MB"; });
    if (doc.hasAttribute("data-saver")) $("input[value=audio]").checked = true;
    document.addEventListener("saver", function (e) { if (e.detail) $("input[value=audio]").checked = true; });

    var sum = $("[data-summary]");
    W.outcomes.forEach(function (o) { sum.appendChild(el("li", null, o.word + ": " + o.title + ".")); });
    draw();
  }

  /* ---------- Boot ---------- */

  initSaver();
  renderShared();
  initCalendar();
  initSwitchboard();
  initInbox();
  renderTriad();
  initRouter();
  initProof();
  renderAgents();
  renderFAQ();
  initConfirmed();
  initLive();
  initReplay();
  initMeter();
})();
