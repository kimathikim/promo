# The "On the Line" standard

Telvoip sells conversations, so the webinar pages are designed as one. Each page is a step in a phone call: **ring → answer → connected → live → replay**. Six rules make up the standard. Each one answers a gap from [RESEARCH.md](RESEARCH.md), and each can be reused beyond webinars (product launches, events, demos).

## 1. Registration is a call, not a form

The page rings. Visitors **answer** to register, and an IVR asks one question at a time. Answered questions fold into a call log ("✓ Email · amina@…  change") so nothing is lost. A call timer runs, and the confirmation page tells people how long registration took.

- One question per screen, in plain words ("Who's on the line?").
- Enter continues, `#` skips optional steps, and `*` goes back.
- Multiple-choice questions use a **real keypad**. Number keys on a keyboard press the same buttons, and options are numbered like a phone menu.
- Without JavaScript it's a plain form with every field visible (progressive enhancement).

*Replaces:* the 6-field form on the right of the hero.

## 2. Every page shows what it cost you

A **data meter** in the footer shows how much data the visit used, measured with the browser's Performance API, against a typical 2 MB page. Each "way in" lists its cost up front: video ~400 MB/hr, dial-in no data, WhatsApp a few KB, audio replay ~28 MB.

**Lite line** is a switch on every page. It turns off animation, decoration and video and leaves the text: the waveform becomes a chapter list and the replay defaults to audio. It turns itself on when the browser reports Save-Data or a 2G connection.

*Replaces:* pages that assume fibre and never say what they cost to load.

## 3. Always a phone-first way in

Every page offers a way in that needs no laptop: register by WhatsApp keyword, dial in for audio only, get reminders on WhatsApp, and share by WhatsApp link. Your seat number is an **extension** (EXT 6568) you quote when you dial in.

## 4. Time is local and multi-zone

Start times show in a row for Nairobi, Lagos, Johannesburg and Accra, plus the visitor's own zone if it's different, highlighted. The agenda and the ticket also show times in the visitor's zone. Speakers show their **current local time** and whether they're in working hours, like a contact card.

## 5. The agenda is a waveform

The hour is drawn as an audio waveform, and each segment's width is its length in minutes. Hover or tab through it to see each part. The replay page reuses the same waveform as its scrubber, with chapter marks in amber. Bar heights are seeded so every visitor sees the same shape.

*Replaces:* "What you'll learn" bullets.

## 6. Every step after registering gets the same design care

- **Confirmed:** a call ticket (extension, date, your time and EAT/WAT, dial-in), an .ics file with a 15-minute alarm, Google Calendar, WhatsApp share, your queued question, and a checklist this browser remembers.
- **Live room:** a countdown, a **speaker test** that plays a ringback tone generated in the browser (nothing downloaded), and Q&A as a **call queue** ranked by votes. Questions sent while registering appear in it.
- **Replay:** choose audio or video with the size shown, a waveform scrubber, and chapters you can click.

## Visual language

| Token | Value | Use |
|---|---|---|
| `--line` | `#0f1915` | "On the line" surfaces: phone, ticket, stage, waveform |
| `--paper` | `#f5f2eb` | Page background (warm, not white) |
| `--signal` | `#16b873` | Answer, connected, primary action |
| `--ring` | `#ff5b35` | Ringing and live only |
| `--amber` | `#e9a825` | Waveform highlight and chapters |

- **Type:** system sans for words and system mono for numbers, times and labels. No web fonts, so no font download.
- **Shape:** large radii for "device" surfaces (28px), pill buttons, and dashed perforations for anything you keep, like the ticket.
- **Motion:** used only where a call would move: the ring pulse, the answer nudge, the connecting bars. All of it is off under Lite line or `prefers-reduced-motion`.
- **Dark mode:** follows the system setting; the tokens swap.
- **No fabricated social proof:** no logo strips or testimonials until real ones exist. Sample Q&A items are labelled "Sample".

## Checklist for a new page in this standard

- [ ] Can someone take part with only a phone?
- [ ] Does it show what it costs in data, and does Lite line still read well?
- [ ] Is every time in the visitor's zone plus EAT/WAT?
- [ ] Does any multiple-choice question use the keypad?
- [ ] Does it work without JavaScript?
- [ ] Does it fit at 390px wide with no sideways scroll?
