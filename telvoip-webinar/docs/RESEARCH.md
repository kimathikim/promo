# Research: Telvoip and how competitors build webinar pages

## What Telvoip does

From Telvoip's own site, blog and app listings (vendor claims, not independently verified):

- **Who:** Telvoip Limited, a Nairobi company (James Gichuru Road). It describes itself as a cloud-native VoIP and contact-centre provider built for African businesses.
- **Product:** a cloud contact centre. Voice, WhatsApp Business API, SMS, email, live chat and social channels (Facebook, Instagram, X) in one agent inbox. AI chatbots and voice assistants backed by a knowledge base, with handoff to a human that keeps the conversation history. Reports and analytics, CRM integration, an open API and outbound campaigns.
- **Africa-specific:** local DID numbers in Kenya, Nigeria, South Africa and Uganda; SIP through Safaricom, Airtel and Telkom in Kenya; M-Pesa and Airtel Money workflows; a platform tuned for low bandwidth. A regional-readiness page lists entities in Uganda, Cameroon, Ghana and Zambia, some pending regulatory approval.
- **Apps:** an iOS and Android softphone (calls from a Telvoip number, live minutes balance) and the Telvoip Dialer Chrome extension (click-to-call from Zoho, HubSpot and others).
- **Pricing (dated, inconsistent on the site):** from about $5 a month (Basic) up to $30–$80 per agent for the Advanced, Professional and Enterprise plans.
- **Competitors Telvoip itself names:** 3CX and Mteja.io. Globally, the category is RingCentral, Aircall, Dialpad, Talkdesk and Genesys.

Sources: telvoip.io (home, omnichannel-contact-centre, customer-support, regional-readiness, the 3CX and Mteja comparison posts), the Google Play and Chrome Web Store listings, and Africa's Talking's partner blog for Mteja.

> This session's network couldn't load telvoip.io directly, only search results about it. Check brand colours, logo and copy against the live site before launch.

## What competitors' webinar pages look like

The webinar registration pages from RingCentral, Aircall, Dialpad, Talkdesk and Genesys, and the pages that 2026 "best webinar landing page" roundups hold up as examples, all follow one template:

| Pattern | What everyone does |
|---|---|
| Hero | Headline on the left, a 4–8 field form on the right, a gradient or stock-photo background |
| Time | One line: "Nov 12, 2:00 PM ET", often in US time zones only |
| Agenda | 3–5 bullets under "What you'll learn" |
| Speakers | Square headshot, name, job title |
| Social proof | A row of customer logos |
| After registering | A "Thanks, you're registered" page with an add-to-calendar button and nothing else |
| Live | A hand-off to Zoom, ON24 or a RingCentral Webinar room the brand doesn't control |
| Replay | The same form again, then a video embed |

RingCentral's own webinar product lets hosts add a logo, colours and custom questions, so its customers end up with the same branded-form layout.

## Gaps that apply to Telvoip's audience

1. **Data cost is never considered.** The typical page weighs about 2 MB, plus hundreds of MB for live video, and no competitor page shows that cost to visitors. For an audience paying for mobile data across Kenya, Nigeria, Uganda and Ghana, this matters most.
2. **There is no way to register by phone.** These companies sell phone and messaging products, yet their only way in is a desktop web form.
3. **Time zones are an afterthought.** US times, or a single zone, for an audience spread across EAT, WAT, CAT and GMT.
4. **The form is the brand's least on-brand moment.** It's the same generic fields whatever the product.
5. **The pages after registering are dead ends.** The confirmation, live and replay pages get no design attention.
6. **The agenda is a list.** It doesn't show how long each part runs or when it happens in your day.

Those six gaps shaped the design standard in [DESIGN-STANDARD.md](DESIGN-STANDARD.md).
