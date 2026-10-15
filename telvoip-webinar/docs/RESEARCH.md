# Research: what Telvoip is, and what the pages are built from

## Sources actually used

| Source | What it gave us |
|---|---|
| **Telvoip eFlyer** (Google Slides by sheila@telvoip.io, Aug 2026) | Tagline "Connect. Engage. Resolve. All from one platform.", "One unified dashboard. Every customer conversation.", stats (6+ channels, 360° view, 1 dashboard), the full feature list, six "why Telvoip" pillars, industries, the client list, contacts (0800 230 094, info@ / sales@telvoip.io, 4th Floor Jahazi, Nairobi), the Book a Free Demo link |
| **Brandfetch listing for telvoip.io** | Brand colours: Blaze Orange `#FF5C00`, Purple `#6C0096`, Anakiwa sky `#99D3FF` (the listing is unclaimed, so confirm with marketing) |
| **telvoip.io, "Customer Experience as a Revenue Engine"** (Phelix, Aug 2025) | Webinar thesis: "every customer interaction is a revenue moment"; the retain / upsell / advocate ROI triad; CSAT and NPS as revenue predictors; African SMEs underserved by CX tools |
| **telvoip.io blog case write-ups** | Anonymised outcomes: e-commerce wait 3 min → under 90 s with FCR +35%; Kenyan telecom 5 min → under 2 min; South African fintech peak wait −50%; Kenyan logistics +30% calls on −20% staffing; remittance response −35% |
| **telvoip.io transport & logistics page** | Testimonial from Shanya Jodie |
| **telvoip.io customer support page** | 5.0 average rating (self-reported on the site) |
| **telvoip.io homepage (search index)** | "Unify Your Customer Interactions Across Every Channel" |
| **telvoip-engineering/telvoip-webphone-react** | The product's own call UI patterns (incoming call banner, dial pad, wrap-up card, transfer). It inherits colours from the host app, so it carries no brand palette of its own. |

### Gaps

- **Whitepapers and customer-stories pages:** search found no public whitepaper or dedicated customer-stories page on telvoip.io, and none in Drive. This environment's network policy blocks telvoip.io, so the live site couldn't be opened directly. If those pages exist, add `telvoip.io` to the environment's allowed domains (or share the files) and the copy and proof sections can be matched to them.
- **Logo:** the official logo file wasn't available. The pages use a placeholder orange mark plus a "Telvoip" wordmark; drop the real SVG into `assets/` and the header.
- **Fonts:** not published anywhere I could reach. The pages use Bricolage Grotesque as the display face until the brand font is confirmed.

## What competitors do (the pattern to break)

RingCentral, Aircall, Dialpad and Talkdesk webinar pages (and the 2026 "best webinar page" roundups) all follow one template: a headline with a form beside it, one time zone, "What you'll learn" bullets, headshots, a logo strip, and a bare "thanks" page. The form never looks like the product being sold, even when the product is a contact centre.

## The opportunity

Telvoip sells **one inbox for every conversation**. So the pages are built from the product itself:

1. You register **inside a working slice of the Telvoip inbox**, by chatting rather than filling in a form.
2. Your **Customer 360°** profile fills in live as you answer.
3. **AI QA** scores the registration conversation when it closes.
4. Every channel on the rail works (WhatsApp, voice on the toll-free line, SMS, email), because "6+ channels, one login" is the pitch.
5. The pages follow the tagline: **Connect** (register) → **Engage** (live room) → **Resolve** (replay as an AI QA report).
