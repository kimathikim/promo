# Telvoip Live: webinar pages

**Connect. Engage. Resolve.** A webinar journey built from Telvoip's own product patterns. See the [design standard](docs/DESIGN-STANDARD.md) and the [research and sources](docs/RESEARCH.md).

| Act | File | What it is |
|---|---|---|
| 01 Connect | `index.html` | Live switchboard hero; register by chatting in a mock Telvoip inbox while your Customer 360° builds and AI QA scores the chat; routed agenda; client proof |
| Ticket | `confirmed.html` | Your registration as a resolved ticket: ID, timeline, CSAT, calendar, WhatsApp share, checklist |
| 02 Engage | `live.html` | Agent-console live room: run order, countdown/stream, speaker test, reactions, omnichannel Q&A queue. `?state=pre\|live\|ended` previews each state |
| 03 Resolve | `replay.html` | Replay as an AI QA report: engagement curve scrubber, key moments, AI summary, audio/video sizes, Book a demo |

Plain HTML/CSS/JS, no build step. The display font comes from Google Fonts; everything else is local.

## Run

```sh
cd telvoip-webinar && python3 -m http.server 8080
```

## Configure

All content lives in `assets/config.js`. Confirm the `TODO`s before launch: the date, the speakers, the WhatsApp number, the SMS number, `registerEndpoint` (where registrations POST as JSON; empty means demo mode, kept in the browser only), and the stream and replay URLs. Also swap in the official logo SVG (the header `.glyph` and `assets/mark.svg`) and confirm the brand colours and font with marketing.
