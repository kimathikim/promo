# Telvoip Live: webinar pages

A landing page and its follow-on pages for Telvoip webinars, built on the [On the Line design standard](docs/DESIGN-STANDARD.md). See also the [research and competitor comparison](docs/RESEARCH.md).

| Page | File | What it is |
|---|---|---|
| Landing | `index.html` | The webinar rings; answer to register through a one-question-at-a-time IVR with a keypad |
| Confirmed | `confirmed.html` | Call ticket with extension, calendar files, WhatsApp share, pre-call checklist |
| Live room | `live.html` | Countdown, speaker test, stream embed, Q&A call queue. `?state=pre\|live\|ended` previews each state |
| Replay | `replay.html` | Audio/video choice with sizes, waveform scrubber, chapter list |

No build step and no dependencies: plain HTML, CSS and JS. About 45 KB per page and no web fonts.

## Run it

```sh
cd telvoip-webinar
python3 -m http.server 8080   # then open http://localhost:8080
```

## Run the next webinar

All content is in **`assets/config.js`**: title, start time (UTC), zones, agenda, speakers, outcomes, FAQ, dial-in, WhatsApp number, stream and replay URLs. Values marked `TODO` are placeholders to confirm before launch:

- `startUTC`, the speakers, `dialIn` and `whatsappNumber`
- `registerEndpoint`: the URL the form POSTs to, as JSON (CRM or marketing automation). While it's empty, registrations are kept only in the visitor's browser (demo mode).
- `streamEmbedUrl` and `replayEmbedUrl`

## Deploy

The folder is self-contained, so it can go on any static host (Vercel, Netlify, S3, Cloudflare Pages). Set the host's output or root directory to `telvoip-webinar`. It's listed in the repo's `.vercelignore` so it doesn't ship with the promo leaderboard.
