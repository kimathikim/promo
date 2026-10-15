# The "Product as the Page" standard

**Rule zero:** a Telvoip marketing page never just describes the product. It *is* the product, scaled down to the job of the page. Visitors use Telvoip before they know they're being sold to.

The webinar follows the brand tagline as a three-act journey shown in the header of every page:

| Act | Page | The product pattern it borrows |
|---|---|---|
| 01 **Connect** | `index.html` | Unified inbox, Customer 360°, AI QA, omnichannel rail |
| (handoff) | `confirmed.html` | A support ticket resolved on first contact, with CSAT |
| 02 **Engage** | `live.html` | Agent console: run order, stage, Q&A as an omnichannel queue |
| 03 **Resolve** | `replay.html` | AI QA report: engagement curve, key moments, AI summary |

## The six patterns

### 1. The switchboard (hero)
Six channel nodes (Voice, WhatsApp, Email, Messenger, Instagram, Webchat) send live pulses into one orange "1 dashboard" node, which feeds "Resolved". A counter shows how many conversations were unified since you arrived, and a ticker names each one by industry (never by a real customer). It turns "6+ channels, one login" into something you can see. It pauses offscreen and under Data saver.

### 2. Register by conversation
There's no form. A chat with the Telvoip Live desk asks seven questions: name, email, company, role, channels, WhatsApp number and a question. Quick-reply chips are used for choices, with validation inline in the chat. A handle-time clock runs in the thread header.

### 3. Your own Customer 360°
As you answer, a profile panel fills in (avatar, email, company, role, channels, mobile, local time, source) with a highlight on each new field. Visitors see the 360° view through their own data.

### 4. AI QA on your own conversation
When the chat closes, the panel scores it: sentiment, customer effort (a plain heuristic: seconds per reply), first-contact resolution and handle time. It's Telvoip's "Call Recording & AI QA" feature, applied to the visitor.

### 5. A routed agenda (IVR)
"Who's calling? Press 1–4." Picking a role routes the agenda: matching segments light up orange, others dim, and you get "Your must-watch: … (35 of 60 min)". Your role from registration routes it automatically next time.

### 6. Proof as before → after meters
The client list from the eFlyer runs as a marquee. The blog's anonymised outcomes animate as before/after bars, with a line saying where they come from. Testimonials are real quotes from telvoip.io only. Nothing is made up; sample Q&A items are labelled "Sample".

## Brand tokens

| Token | Value | Use |
|---|---|---|
| `--orange` | `#FF5C00` | Primary actions, "1 dashboard", highlights. Text on orange is ink `#1A0B24`, not white (contrast). |
| `--purple` | `#6C0096` | Secondary: chat bubbles, act labels, the Upsell card, the quote |
| `--sky` | `#99D3FF` | Accent: the Advocate card, AI labels, selected format |
| `--plum-950` | `#0F0016` | "Night" surfaces: hero, live room, report |
| `--paper` | `#FBF8F4` | Light sections |

- **Type:** Bricolage Grotesque (display, 800, tight tracking), system sans for body, system mono for times, IDs and labels.
- **Shapes:** product-UI cards (18–28px radii), pills for actions and chips, a dashed timeline for ticket history.
- **Motion:** only where the product moves: pulses on the switchboard, typing dots, field highlights, filling meters, reactions. All of it is off under Data saver or `prefers-reduced-motion`.
- **Dark mode:** light sections follow the system setting; night sections stay dark.

## Always on

- A way in on every channel: WhatsApp keyword, toll-free 0800 230 094, SMS (when configured), email.
- Times shown for Nairobi, Lagos, Johannesburg and Accra, plus the visitor's own zone.
- Data saver toggle and a footer meter showing what the page cost in KB.
- Works at 390px wide with no sideways scroll; the chat falls back to a plain form without JavaScript.

## Checklist for the next page in this standard

- [ ] Which Telvoip feature does this page *perform*, not describe?
- [ ] Is every claim traceable to Telvoip's own material?
- [ ] Can someone take part from a phone, on any channel?
- [ ] Does it work in Data saver and without JavaScript?
