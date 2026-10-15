/*
 * Telvoip Live: behaviour for all four pages.
 * No dependencies. Every page works without this file; it adds the call.
 */
(function () {
  "use strict";

  var W = window.WEBINAR;
  if (!W) return;

  var doc = document.documentElement;
  doc.classList.remove("no-js");

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* ---------- Storage (never required, never trusted) ---------- */

  var store = {
    get: function (k) {
      try { return JSON.parse(localStorage.getItem("telvoip-live:" + k)); } catch (e) { return null; }
    },
    set: function (k, v) {
      try { localStorage.setItem("telvoip-live:" + k, JSON.stringify(v)); } catch (e) { /* private mode */ }
    },
  };

  /* ---------- Time ---------- */

  var start = new Date(W.startUTC);
  var end = new Date(start.getTime() + W.durationMin * 60000);
  var userTZ = (function () {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return "UTC"; }
  })();

  function fmt(d, tz, opts) {
    var o = Object.assign({ timeZone: tz }, opts);
    try { return new Intl.DateTimeFormat("en-GB", o).format(d); }
    catch (e) { o.timeZone = "UTC"; return new Intl.DateTimeFormat("en-GB", o).format(d); }
  }
  function hhmm(d, tz) { return fmt(d, tz, { hour: "2-digit", minute: "2-digit", hour12: false }); }
  function longDate(d, tz) { return fmt(d, tz, { weekday: "long", day: "numeric", month: "long", year: "numeric" }); }
  function shortDate(d, tz) { return fmt(d, tz, { weekday: "short", day: "numeric", month: "short" }); }
  function cityOf(tz) {
    var z = W.zones.filter(function (x) { return x.tz === tz; })[0];
    return z ? z.city : (tz.split("/").pop() || tz).replace(/_/g, " ");
  }
  function pad(n) { return String(n).padStart(2, "0"); }

  function renderZones() {
    $$("[data-zones]").forEach(function (list) {
      list.textContent = "";
      var zones = W.zones.slice();
      var known = zones.some(function (z) { return z.tz === userTZ; });
      if (!known) zones.push({ city: "Your time", tz: userTZ, you: true });
      zones.forEach(function (z) {
        var li = el("li");
        if (z.you || z.tz === userTZ) li.classList.add("you");
        li.appendChild(el("div", "t", hhmm(start, z.tz)));
        li.appendChild(el("div", "c", z.you ? "Your time · " + cityOf(z.tz) : z.city + (z.tz === userTZ ? " · you" : "")));
        list.appendChild(li);
      });
    });
    $$("[data-when]").forEach(function (n) {
      n.textContent = longDate(start, userTZ) + " · " + W.durationMin + " min · online";
    });
    $$("[data-short-when]").forEach(function (n) {
      n.textContent = shortDate(start, userTZ) + " · " + hhmm(start, userTZ);
    });
  }

  /* ---------- Lite line ---------- */

  function autoLite() {
    var c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    return !!(c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || "")));
  }
  function setLite(on, remember) {
    if (on) doc.setAttribute("data-lite", ""); else doc.removeAttribute("data-lite");
    $$("[data-lite-toggle]").forEach(function (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); });
    if (remember) store.set("lite", on);
    document.dispatchEvent(new CustomEvent("lite", { detail: on }));
  }
  function initLite() {
    var pref = store.get("lite");
    setLite(pref == null ? autoLite() : !!pref, false);
    $$("[data-lite-toggle]").forEach(function (b) {
      b.addEventListener("click", function () { setLite(!doc.hasAttribute("data-lite"), true); });
    });
  }

  /* ---------- Data meter: show visitors what the page cost them ---------- */

  function initMeter() {
    var m = $("[data-meter]");
    if (!m || !window.performance || !performance.getEntriesByType) return;
    function measure() {
      var bytes = 0;
      var nav = performance.getEntriesByType("navigation")[0];
      if (nav) bytes += nav.transferSize || nav.encodedBodySize || 0;
      performance.getEntriesByType("resource").forEach(function (r) {
        bytes += r.transferSize || r.encodedBodySize || 0;
      });
      if (!bytes) return;
      var kb = Math.max(1, Math.round(bytes / 1024));
      var typical = 2048; // a typical web page is 2 MB+
      $(".v", m).textContent = kb + " KB";
      $(".gauge i", m).style.width = Math.min(100, (kb / typical) * 100).toFixed(1) + "%";
      m.setAttribute("title", "A typical web page weighs about 2 MB. This one weighed " + kb + " KB.");
    }
    if (document.readyState === "complete") setTimeout(measure, 50);
    else window.addEventListener("load", function () { setTimeout(measure, 50); });
  }

  /* ---------- Calendar ---------- */

  function icsStamp(d) { return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); }
  function pageURL(name) { return new URL(name, location.href).href; }
  function calendarText() {
    return W.subtitle + "\n\nJoin: " + pageURL("live.html") + "\nAudio only: " + W.dialIn;
  }
  function downloadICS() {
    var esc = function (s) { return String(s).replace(/[\\,;]/g, "\\$&").replace(/\n/g, "\\n"); };
    var body = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Telvoip//Telvoip Live//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
      "BEGIN:VEVENT",
      "UID:" + W.slug + "-" + icsStamp(start) + "@telvoip.io",
      "DTSTAMP:" + icsStamp(new Date()),
      "DTSTART:" + icsStamp(start),
      "DTEND:" + icsStamp(end),
      "SUMMARY:" + esc(W.series + ": " + W.title),
      "DESCRIPTION:" + esc(calendarText()),
      "LOCATION:" + esc(pageURL("live.html")),
      "BEGIN:VALARM", "TRIGGER:-PT15M", "ACTION:DISPLAY", "DESCRIPTION:" + esc(W.title + " starts in 15 minutes"), "END:VALARM",
      "END:VEVENT", "END:VCALENDAR",
    ].join("\r\n");
    var a = el("a");
    a.href = URL.createObjectURL(new Blob([body], { type: "text/calendar" }));
    a.download = W.slug + ".ics";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function googleCalURL() {
    return "https://calendar.google.com/calendar/render?action=TEMPLATE" +
      "&text=" + encodeURIComponent(W.series + ": " + W.title) +
      "&dates=" + icsStamp(start) + "/" + icsStamp(end) +
      "&details=" + encodeURIComponent(calendarText()) +
      "&location=" + encodeURIComponent(pageURL("live.html"));
  }
  function initCalendarButtons() {
    $$("[data-ics]").forEach(function (b) {
      b.addEventListener("click", function (e) { e.preventDefault(); downloadICS(); });
    });
    $$("[data-gcal]").forEach(function (a) { a.href = googleCalURL(); });
  }

  /* ---------- Phone-first links ---------- */

  function initPhoneLinks() {
    $$("[data-dial]").forEach(function (a) {
      a.textContent = a.textContent.trim() || W.dialIn;
      a.href = "tel:" + W.dialIn.replace(/[^\d+]/g, "");
    });
    $$("[data-dial-text]").forEach(function (n) { n.textContent = W.dialIn; });
    $$("[data-wa]").forEach(function (a) {
      a.href = "https://wa.me/" + W.whatsappNumber + "?text=" + encodeURIComponent(W.whatsappKeyword);
    });
    $$("[data-wa-keyword]").forEach(function (n) { n.textContent = W.whatsappKeyword; });
    $$("[data-share-wa]").forEach(function (a) {
      a.href = "https://wa.me/?text=" + encodeURIComponent(
        W.series + ": " + W.title + " · " + shortDate(start, "Africa/Nairobi") + ", " +
        hhmm(start, "Africa/Nairobi") + " EAT. Free seat: " + pageURL("./"));
    });
  }

  /* ---------- Waveform: deterministic "audio" so the page renders the same every time ---------- */

  function seeded(seed) {
    var s = seed >>> 0 || 1;
    return function () { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return ((s >>> 0) % 1000) / 1000; };
  }
  function barHeights(n, seed) {
    var r = seeded(seed), out = [], v = 0.5;
    for (var i = 0; i < n; i++) {
      v = v * 0.55 + r() * 0.45;
      var edge = Math.min(1, i / 3, (n - 1 - i) / 3);
      out.push(Math.max(0.12, Math.min(1, v * (0.55 + edge * 0.6))));
    }
    return out;
  }
  function chapterStarts() {
    var t = 0;
    return W.agenda.map(function (c) { var s = t; t += c.min; return s; });
  }
  function clock(min) {
    return pad(Math.floor(min / 60)) + ":" + pad(min % 60);
  }
  function clockAt(min) {
    // wall clock in the visitor's zone at minute `min` of the session
    return hhmm(new Date(start.getTime() + min * 60000), userTZ);
  }

  function initWave() {
    var track = $("[data-wave]");
    if (!track) return;
    var axis = $("[data-wave-axis]");
    var detail = $("[data-wave-detail]");
    var list = $("[data-chapters]");
    var starts = chapterStarts();
    var segs = [];

    W.agenda.forEach(function (c, i) {
      var seg = el("button", "seg");
      seg.type = "button";
      seg.style.flex = String(c.min);
      seg.setAttribute("aria-pressed", "false");
      seg.setAttribute("aria-label", clockAt(starts[i]) + ", " + c.title + ", " + c.min + " minutes");
      var heights = barHeights(Math.max(4, Math.round(c.min * 1.6)), (i + 7) * 2654435761);
      heights.forEach(function (h) {
        var b = el("i", "b");
        b.style.height = Math.round(h * 100) + "%";
        seg.appendChild(b);
      });
      seg.addEventListener("click", function () { pick(i); });
      seg.addEventListener("mouseenter", function () { pick(i); });
      seg.addEventListener("focus", function () { pick(i); });
      track.appendChild(seg);
      segs.push(seg);

      if (axis) {
        var lab = el("span", null, clockAt(starts[i]) + " " + c.title);
        lab.style.flex = String(c.min);
        axis.appendChild(lab);
      }
      if (list) {
        var li = el("li");
        li.appendChild(el("div", "clock", clockAt(starts[i])));
        var d = el("div");
        d.appendChild(el("b", null, c.title + " · " + c.min + " min"));
        d.appendChild(el("span", null, c.body + (c.speaker != null ? " With " + W.speakers[c.speaker].name + "." : "")));
        li.appendChild(d);
        list.appendChild(li);
      }
    });

    function pick(i) {
      segs.forEach(function (s, j) { s.setAttribute("aria-pressed", j === i ? "true" : "false"); });
      if (!detail) return;
      var c = W.agenda[i];
      $(".clock", detail).textContent = clockAt(starts[i]);
      $("h3", detail).textContent = c.title + " · " + c.min + " min";
      $("p", detail).textContent = c.body + (c.speaker != null ? " With " + W.speakers[c.speaker].name + "." : "");
    }
    pick(0);
    var meta = $("[data-wave-range]");
    if (meta) meta.textContent = clockAt(0) + " to " + clockAt(W.durationMin) + " " + cityOf(userTZ) + " time";
  }

  /* ---------- Shared renders ---------- */

  function initials(name) {
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p[0]; }).join("").toUpperCase();
  }
  function renderSpeakers() {
    var box = $("[data-speakers]");
    if (!box) return;
    W.speakers.forEach(function (s) {
      var card = el("article", "contact");
      var top = el("div", "top");
      top.appendChild(el("div", "initials", initials(s.name)));
      var t = el("div");
      t.appendChild(el("h3", null, s.name));
      t.appendChild(el("div", "role", s.role));
      top.appendChild(t);
      card.appendChild(top);
      var local = el("div", "local");
      var left = el("span");
      left.appendChild(document.createTextNode(s.city + " · "));
      var now = el("b", null, "");
      now.setAttribute("data-now", s.tz);
      left.appendChild(now);
      local.appendChild(left);
      var pres = el("span", "presence", "");
      pres.setAttribute("data-presence", s.tz);
      local.appendChild(pres);
      card.appendChild(local);
      box.appendChild(card);
    });
    tickNow();
    setInterval(tickNow, 30000);
  }
  function tickNow() {
    var n = new Date();
    $$("[data-now]").forEach(function (b) { b.textContent = hhmm(n, b.getAttribute("data-now")); });
    $$("[data-presence]").forEach(function (p) {
      var h = parseInt(fmt(n, p.getAttribute("data-presence"), { hour: "2-digit", hour12: false }), 10);
      var on = h >= 8 && h < 18;
      p.classList.toggle("on", on);
      p.textContent = on ? "working hours" : "off the clock";
    });
  }
  function renderOutcomes() {
    var box = $("[data-outcomes]");
    if (!box) return;
    W.outcomes.forEach(function (o) {
      var li = el("li");
      var press = el("div", "press", "Press");
      press.appendChild(el("b", null, o.key));
      li.appendChild(press);
      li.appendChild(el("h3", null, o.title));
      li.appendChild(el("p", null, o.body));
      box.appendChild(li);
    });
  }
  function renderFAQ() {
    var box = $("[data-faq]");
    if (!box) return;
    W.faq.forEach(function (f) {
      var d = el("details");
      d.appendChild(el("summary", null, f.q));
      d.appendChild(el("p", null, f.a));
      box.appendChild(d);
    });
  }
  function renderText() {
    $$("[data-text]").forEach(function (n) {
      var v = W[n.getAttribute("data-text")];
      if (v != null) n.textContent = v;
    });
  }

  /* ---------- Landing: registration is a phone call ---------- */

  function initRegister() {
    var phone = $("[data-phone]");
    if (!phone) return;
    var form = $("#register");
    var ringing = $("[data-ringing]");
    var ivr = $("[data-ivr]");
    var connecting = $("[data-connecting]");
    var log = $("[data-ivr-log]");
    var timerEl = $("[data-call-timer]");
    var stateEl = $("[data-call-state]");
    var steps = $$(".step", form);
    var current = 0;
    var answers = {};
    var t0 = 0, timerId = 0;

    // render role menu + keypad
    var menu = $("[data-role-menu]");
    var select = $("[data-role-select]");
    var blank = el("option", null, "Choose one");
    blank.value = "";
    select.appendChild(blank);
    W.roles.forEach(function (r) {
      var li = el("li");
      li.setAttribute("data-key", r.key);
      li.appendChild(el("b", null, r.key));
      li.appendChild(el("span", null, r.label));
      menu.appendChild(li);
      var opt = el("option", null, r.key + " · " + r.label);
      opt.value = r.label;
      select.appendChild(opt);
    });
    var keypad = $("[data-keypad]");
    var letters = { 2: "abc", 3: "def", 4: "ghi", 5: "jkl", 6: "mno", 7: "pqrs", 8: "tuv", 9: "wxyz", 0: "other" };
    var valid = W.roles.map(function (r) { return r.key; });
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"].forEach(function (k) {
      var b = el("button", "key", k);
      b.type = "button";
      b.setAttribute("data-k", k);
      if (letters[k]) b.appendChild(el("small", null, letters[k]));
      if (valid.indexOf(k) < 0 && k !== "*") b.disabled = true;
      if (k === "*") { b.setAttribute("aria-label", "Star, go back"); b.appendChild(el("small", null, "back")); }
      b.addEventListener("click", function () { press(k); });
      keypad.appendChild(b);
    });

    function press(k) {
      var key = $('.key[data-k="' + k + '"]', keypad);
      if (key) { key.classList.add("is-pressed"); setTimeout(function () { key.classList.remove("is-pressed"); }, 160); }
      if (k === "*") { go(current - 1); return; }
      var role = W.roles.filter(function (r) { return r.key === k; })[0];
      if (!role) return;
      $$("li", menu).forEach(function (li) { li.setAttribute("aria-current", li.getAttribute("data-key") === k ? "true" : "false"); });
      select.value = role.label;
      setTimeout(function () { advance(); }, 260);
    }

    function tick() {
      var s = Math.floor((Date.now() - t0) / 1000);
      timerEl.textContent = pad2(Math.floor(s / 60)) + ":" + pad2(s % 60);
    }
    function pad2(n) { return String(n).padStart(2, "0"); }

    function answer() {
      ringing.hidden = true;
      ivr.hidden = false;
      stateEl.textContent = "On the line";
      t0 = Date.now();
      tick();
      timerId = setInterval(tick, 1000);
      go(0);
    }

    function go(i) {
      if (i < 0) i = 0;
      current = i;
      steps.forEach(function (s, j) { s.classList.toggle("is-current", j === i); });
      var step = steps[i];
      var first = $("input:not([type=checkbox]), textarea", step) || $(".key:not([disabled])", step);
      if (first) setTimeout(function () { first.focus({ preventScroll: true }); }, 30);
      renderLog();
    }

    function validate(step) {
      var err = $(".field-error", step);
      var bad = "";
      $$("input, textarea, select", step).forEach(function (f) {
        if (bad) return;
        if (f.type === "checkbox") return;
        f.value = f.value.trim ? f.value.trim() : f.value;
        if (f.required && !f.value) bad = f.getAttribute("data-msg") || "This one's needed.";
        else if (f.type === "email" && f.value && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(f.value)) bad = "That email doesn't look complete.";
        else if (f.type === "tel" && f.value && f.value.replace(/\D/g, "").length < 9) bad = "Add the full number, with country code.";
        if (bad) f.setAttribute("aria-invalid", "true"); else f.removeAttribute("aria-invalid");
      });
      if (err) err.textContent = bad;
      return !bad;
    }

    function collect(step) {
      var key = step.getAttribute("data-step");
      var label = step.getAttribute("data-label");
      var val = "";
      $$("input, textarea, select", step).forEach(function (f) {
        if (f.type === "checkbox") { answers[f.name] = f.checked; return; }
        answers[f.name] = f.value;
        if (!val) val = f.value;
      });
      if (key === "phone" && answers.phone && answers.whatsapp) val += " · WhatsApp reminders on";
      answers["_" + key] = { label: label, value: val || "skipped" };
    }

    function renderLog() {
      log.textContent = "";
      steps.slice(0, current).forEach(function (s, j) {
        var a = answers["_" + s.getAttribute("data-step")];
        if (!a) return;
        var li = el("li");
        li.appendChild(el("span", null, "✓ " + a.label));
        li.appendChild(el("b", null, a.value));
        var edit = el("button", null, "change");
        edit.type = "button";
        edit.setAttribute("aria-label", "Change " + a.label);
        edit.addEventListener("click", function () { go(j); });
        li.appendChild(edit);
        log.appendChild(li);
      });
    }

    function advance() {
      var step = steps[current];
      if (!validate(step)) { var f = $("[aria-invalid]", step); if (f) f.focus(); return; }
      collect(step);
      if (current < steps.length - 1) go(current + 1);
      else submit();
    }

    function submit() {
      clearInterval(timerId);
      ivr.hidden = true;
      connecting.hidden = false;
      stateEl.textContent = "Connecting";
      var reg = {
        name: answers.name, email: answers.email, phone: answers.phone || "",
        whatsapp: !!answers.whatsapp && !!answers.phone, role: answers.role || "",
        question: answers.question || "", tz: userTZ, webinar: W.slug,
        callSeconds: Math.round((Date.now() - t0) / 1000), at: new Date().toISOString(),
      };
      reg.ext = extFor(reg.email);
      store.set("registrant", reg);
      var done = function () { location.href = "confirmed.html"; };
      if (W.registerEndpoint) {
        fetch(W.registerEndpoint, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(reg),
        }).then(function (r) { if (!r.ok) throw new Error(r.status); done(); })
          .catch(function () {
            connecting.hidden = true; ivr.hidden = false; stateEl.textContent = "Line dropped";
            var err = $(".field-error", steps[current]);
            if (err) err.textContent = "We couldn't save your seat. Check your connection and press Enter to try again.";
          });
      } else {
        setTimeout(done, 1100);
      }
    }

    // With JS the call rings first; without it the plain form is already showing.
    ringing.hidden = false;
    ivr.hidden = true;

    $("[data-answer]").addEventListener("click", answer);
    $$('a[href="#call"]').forEach(function (a) {
      a.addEventListener("click", function () {
        setTimeout(function () {
          var target = ringing.hidden ? $("input, textarea, .key", steps[current]) : $("[data-answer]");
          if (target) target.focus({ preventScroll: true });
        }, 400);
      });
    });
    form.addEventListener("submit", function (e) { e.preventDefault(); advance(); });
    $$("[data-next]", form).forEach(function (b) { b.addEventListener("click", function () { advance(); }); });
    $$("[data-skip]", form).forEach(function (b) {
      b.addEventListener("click", function () {
        var step = steps[current];
        $$("input:not([type=checkbox]), textarea", step).forEach(function (f) { f.value = ""; f.removeAttribute("required"); });
        advance();
      });
    });
    $$("[data-back]", form).forEach(function (b) { b.addEventListener("click", function () { go(current - 1); }); });

    // Physical keys mirror the keypad; # skips; Enter submits a textarea step with Cmd/Ctrl.
    document.addEventListener("keydown", function (e) {
      if (ivr.hidden) {
        if (!ringing.hidden && (e.key === "Enter" || e.key === " ") && document.activeElement === document.body) {
          e.preventDefault(); answer();
        }
        return;
      }
      var step = steps[current];
      var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (step.getAttribute("data-step") === "role" && !typing && /^[0-9*]$/.test(e.key)) {
        e.preventDefault(); press(e.key);
      }
      if (e.key === "#" && !typing && $("[data-skip]", step)) { e.preventDefault(); $("[data-skip]", step).click(); }
      if (e.key === "Enter" && e.target.tagName === "TEXTAREA" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); advance(); }
    });

    // Already registered? Say so instead of ringing again.
    var reg = store.get("registrant");
    if (reg && reg.webinar === W.slug) {
      $("[data-caller-sub]").textContent = "You're already on the list, " + reg.name.split(" ")[0] + ". Answer again to update your details.";
      var seat = $("[data-seat-link]");
      if (seat) seat.hidden = false;
    }
  }

  function extFor(s) {
    var h = 0;
    for (var i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return String(1000 + (h % 9000));
  }

  /* ---------- Confirmed: the call ticket ---------- */

  function initConfirmed() {
    if (document.body.getAttribute("data-page") !== "confirmed") return;
    var reg = store.get("registrant");
    var first = reg && reg.name ? reg.name.split(" ")[0] : "";
    $("[data-greet]").textContent = first ? "You're on the line, " + first + "." : "You're on the line.";
    $("[data-ext]").textContent = "EXT " + (reg ? reg.ext : "----");
    $("[data-tk-date]").textContent = longDate(start, userTZ);
    $("[data-tk-time]").textContent = hhmm(start, userTZ) + " to " + hhmm(end, userTZ) + " " + cityOf(userTZ);
    $("[data-tk-eat]").textContent = hhmm(start, "Africa/Nairobi") + " EAT · " + hhmm(start, "Africa/Lagos") + " WAT";
    if (reg && reg.callSeconds) {
      $("[data-call-length]").textContent = "Registration took " + reg.callSeconds + (reg.callSeconds === 1 ? " second." : " seconds.");
    }
    if (reg && reg.email) $("[data-sent-to]").textContent = reg.email;
    if (reg && reg.whatsapp) {
      $("[data-wa-note]").textContent = "Reminders will also go to WhatsApp on " + reg.phone + ".";
    }
    var q = $("[data-queued]");
    if (reg && reg.question) {
      q.hidden = false;
      $("q", q).textContent = reg.question;
    }

    // Checklist that remembers itself
    var done = store.get("checklist") || {};
    $$("[data-check]").forEach(function (c) {
      var k = c.getAttribute("data-check");
      c.checked = !!done[k];
      c.addEventListener("change", function () { done[k] = c.checked; store.set("checklist", done); });
    });

    var copy = $("[data-copy]");
    if (copy) copy.addEventListener("click", function () {
      var url = pageURL("./");
      var ok = function () { copy.textContent = "Link copied"; setTimeout(function () { copy.textContent = "Copy invite link"; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(ok, function () { prompt("Copy this link", url); });
      else prompt("Copy this link", url);
    });
  }

  /* ---------- Live room ---------- */

  function liveState() {
    var forced = new URLSearchParams(location.search).get("state");
    if (forced === "pre" || forced === "live" || forced === "ended") return forced;
    var now = Date.now();
    if (now < start.getTime() - 5 * 60000) return "pre";
    if (now < end.getTime() + 15 * 60000) return "live";
    return "ended";
  }

  function initLive() {
    if (document.body.getAttribute("data-page") !== "live") return;
    var screen = $("[data-screen]");
    var badge = $("[data-live-badge]");
    var state = liveState();
    var reg = store.get("registrant");

    function showPre() {
      badge.textContent = "Waiting room";
      badge.classList.remove("live");
      var cd = $("[data-countdown]");
      cd.hidden = false;
      var parts = { d: $("[data-cd=d]"), h: $("[data-cd=h]"), m: $("[data-cd=m]"), s: $("[data-cd=s]") };
      function step() {
        var ms = Math.max(0, start.getTime() - Date.now());
        var s = Math.floor(ms / 1000);
        parts.d.textContent = pad(Math.floor(s / 86400));
        parts.h.textContent = pad(Math.floor((s % 86400) / 3600));
        parts.m.textContent = pad(Math.floor((s % 3600) / 60));
        parts.s.textContent = pad(s % 60);
        if (ms <= 5 * 60000 && !new URLSearchParams(location.search).get("state")) location.reload();
      }
      step();
      setInterval(step, 1000);
    }
    function showLive() {
      badge.textContent = "Live";
      badge.classList.add("live");
      $("[data-countdown]").hidden = true;
      var msg = $("[data-screen-msg]");
      if (W.streamEmbedUrl && !doc.hasAttribute("data-lite")) {
        var f = el("iframe");
        f.src = W.streamEmbedUrl;
        f.title = W.title + " live stream";
        f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
        screen.textContent = "";
        screen.appendChild(f);
      } else {
        msg.hidden = false;
        $("h2", msg).textContent = W.streamEmbedUrl ? "Audio-only mode is on" : "The stream connects here";
        $("p", msg).textContent = W.streamEmbedUrl
          ? "Lite line is on, so we're not loading video. Dial " + W.dialIn + " to listen, or switch Lite line off."
          : "Set streamEmbedUrl in assets/config.js to show the live video. Until then, dial " + W.dialIn + " for audio.";
      }
    }
    function showEnded() {
      badge.textContent = "Ended";
      badge.classList.remove("live");
      $("[data-countdown]").hidden = true;
      var msg = $("[data-screen-msg]");
      msg.hidden = false;
      $("h2", msg).textContent = "That's the call.";
      $("p", msg).innerHTML = "";
      $("p", msg).appendChild(document.createTextNode("The replay, transcript and slides are ready. "));
      var a = el("a", null, "Watch or listen to the replay");
      a.href = "replay.html";
      $("p", msg).appendChild(a);
    }
    if (state === "pre") showPre(); else if (state === "live") showLive(); else showEnded();

    $("[data-stage-when]").textContent = shortDate(start, userTZ) + " · " + hhmm(start, userTZ) + " " + cityOf(userTZ);

    // Speaker test: a two-tone ringback, generated, zero bytes downloaded.
    var test = $("[data-sound-test]");
    if (test) test.addEventListener("click", function () {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { test.textContent = "No audio support"; return; }
      var ctx = new AC();
      var g = ctx.createGain();
      g.gain.value = 0.0001;
      g.connect(ctx.destination);
      [440, 480].forEach(function (f) {
        var o = ctx.createOscillator();
        o.frequency.value = f; o.connect(g); o.start(); o.stop(ctx.currentTime + 2.2);
      });
      var t = ctx.currentTime;
      g.gain.exponentialRampToValueAtTime(0.12, t + 0.05);
      g.gain.setValueAtTime(0.12, t + 0.9);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 1.0);
      g.gain.setValueAtTime(0.0001, t + 1.2);
      g.gain.exponentialRampToValueAtTime(0.12, t + 1.25);
      g.gain.setValueAtTime(0.12, t + 2.1);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 2.2);
      test.setAttribute("aria-pressed", "true");
      test.textContent = "Ringing…";
      setTimeout(function () { test.textContent = "Heard it? You're set"; ctx.close(); }, 2300);
    });

    // Q&A as a call queue: most-wanted questions get answered first.
    var qList = $("[data-queue]");
    var questions = store.get("queue") || [
      { id: "s1", text: "Can the AI assistant answer in Swahili as well as English?", who: "Sample · Contact centre lead, Nairobi", votes: 14 },
      { id: "s2", text: "How do you handle a WhatsApp chat that turns into a voice call?", who: "Sample · Support manager, Lagos", votes: 9 },
      { id: "s3", text: "What bandwidth does one agent actually need for clear calls?", who: "Sample · IT lead, Kampala", votes: 7 },
    ];
    if (reg && reg.question && !questions.some(function (q) { return q.id === "mine-reg"; })) {
      questions.push({ id: "mine-reg", text: reg.question, who: "You · sent when you registered", votes: 1, mine: true, voted: true });
    }
    function drawQueue() {
      questions.sort(function (a, b) { return b.votes - a.votes; });
      qList.textContent = "";
      questions.forEach(function (q, i) {
        var li = el("li");
        if (q.mine) li.classList.add("mine");
        li.appendChild(el("span", "pos", "#" + (i + 1)));
        var body = el("div");
        body.appendChild(el("div", null, q.text));
        body.appendChild(el("div", "who", q.who));
        li.appendChild(body);
        var v = el("button", "vote", "▲ " + q.votes);
        v.type = "button";
        v.setAttribute("aria-pressed", q.voted ? "true" : "false");
        v.setAttribute("aria-label", (q.voted ? "Remove vote, " : "Vote up, ") + q.votes + " votes");
        v.addEventListener("click", function () {
          q.voted = !q.voted; q.votes += q.voted ? 1 : -1; store.set("queue", questions); drawQueue();
        });
        li.appendChild(v);
        qList.appendChild(li);
      });
      $("[data-queue-count]").textContent = questions.length + " in queue";
    }
    drawQueue();
    $("[data-ask]").addEventListener("submit", function (e) {
      e.preventDefault();
      var input = $("input", e.target);
      var text = input.value.trim();
      if (!text) return;
      questions.push({ id: "q" + Date.now(), text: text, who: "You · just now", votes: 1, mine: true, voted: true });
      store.set("queue", questions);
      input.value = "";
      drawQueue();
    });

    document.addEventListener("lite", function () { if (liveState() === "live") location.reload(); });
  }

  /* ---------- Replay ---------- */

  function initReplay() {
    if (document.body.getAttribute("data-page") !== "replay") return;
    var total = W.durationMin * 60;
    var pos = 0, playing = false, timer = 0;
    var scrub = $("[data-scrub]");
    var starts = chapterStarts().map(function (m) { return m * 60; });
    var n = 120;
    var heights = barHeights(n, 1337);
    var bars = heights.map(function (h, i) {
      var b = el("i", "b");
      b.style.height = Math.round(h * 100) + "%";
      var t = (i / n) * total;
      if (starts.some(function (s) { return s > 0 && Math.abs(s - t) < total / n / 2; })) b.classList.add("chap");
      scrub.appendChild(b);
      return b;
    });
    var timeEl = $("[data-pos]");
    var playBtn = $("[data-play]");
    var items = [];

    function fmtSec(s) { s = Math.floor(s); return pad(Math.floor(s / 60)) + ":" + pad(s % 60); }
    function draw() {
      var k = Math.round((pos / total) * n);
      bars.forEach(function (b, i) { b.classList.toggle("played", i < k); });
      timeEl.textContent = fmtSec(pos) + " / " + fmtSec(total);
      scrub.setAttribute("aria-valuenow", String(Math.floor(pos)));
      scrub.setAttribute("aria-valuetext", fmtSec(pos));
      var ch = 0;
      starts.forEach(function (s, i) { if (pos >= s) ch = i; });
      items.forEach(function (b, i) { b.setAttribute("aria-current", i === ch ? "true" : "false"); });
      $("[data-now-chapter]").textContent = W.agenda[ch].title;
    }
    function seek(s) { pos = Math.max(0, Math.min(total, s)); draw(); }
    function toggle() {
      playing = !playing;
      playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");
      $("[data-icon-play]", playBtn).hidden = playing;
      $("[data-icon-pause]", playBtn).hidden = !playing;
      clearInterval(timer);
      if (playing) timer = setInterval(function () { seek(pos + 10); if (pos >= total) toggle(); }, 250);
    }
    playBtn.addEventListener("click", toggle);
    scrub.addEventListener("click", function (e) {
      var r = scrub.getBoundingClientRect();
      seek(((e.clientX - r.left) / r.width) * total);
    });
    scrub.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") { seek(pos + 15); e.preventDefault(); }
      if (e.key === "ArrowLeft") { seek(pos - 15); e.preventDefault(); }
      if (e.key === "Home") { seek(0); e.preventDefault(); }
      if (e.key === "End") { seek(total); e.preventDefault(); }
    });
    scrub.setAttribute("aria-valuemax", String(total));

    var list = $("[data-transcript]");
    W.agenda.forEach(function (c, i) {
      var li = el("li");
      var b = el("button");
      b.type = "button";
      b.appendChild(el("span", "clock", fmtSec(starts[i])));
      var d = el("span");
      d.appendChild(el("span", "chap-title", c.title));
      d.appendChild(document.createTextNode(c.body + " "));
      if (c.speaker != null) d.appendChild(el("span", "who", W.speakers[c.speaker].name));
      b.appendChild(d);
      b.addEventListener("click", function () { seek(starts[i]); });
      li.appendChild(b);
      list.appendChild(li);
      items.push(b);
    });

    // Format: audio-only by default on Lite line, and the sizes are shown up front.
    $("[data-size-audio]").textContent = W.replayAudioSizeMB + " MB";
    $("[data-size-video]").textContent = W.replayVideoSizeMB + " MB";
    var radios = $$("input[name=format]");
    function syncFormat() {
      var audio = $("input[value=audio]").checked;
      $("[data-format-label]").textContent = audio ? "Audio only" : "Video";
      $("[data-replay-msg]").textContent = W.replayEmbedUrl
        ? ""
        : (audio ? "Audio replay: " + W.replayAudioSizeMB + " MB for the full hour." : "Video replay: " + W.replayVideoSizeMB + " MB for the full hour.") +
          " Set replayEmbedUrl in assets/config.js to load the real recording.";
    }
    radios.forEach(function (r) { r.addEventListener("change", syncFormat); });
    if (doc.hasAttribute("data-lite")) $("input[value=audio]").checked = true;
    document.addEventListener("lite", function (e) { if (e.detail) { $("input[value=audio]").checked = true; syncFormat(); } });
    syncFormat();
    draw();
  }

  /* ---------- Boot ---------- */

  initLite();
  renderText();
  renderZones();
  renderOutcomes();
  renderSpeakers();
  renderFAQ();
  initWave();
  initCalendarButtons();
  initPhoneLinks();
  initRegister();
  initConfirmed();
  initLive();
  initReplay();
  initMeter();
})();
