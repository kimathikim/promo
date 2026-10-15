/*
 * Telvoip Live: every piece of webinar content lives here.
 * Change this file to run the next webinar; the four pages read from it.
 *
 * Sources for the copy (see docs/RESEARCH.md):
 *  - Telvoip eFlyer (Aug 2026): tagline, channels, pillars, client list, contacts
 *  - "Customer Experience as a Revenue Engine" (telvoip.io, Aug 2025): topic, ROI triad
 *  - telvoip.io blog case write-ups: anonymised customer outcomes
 *  - telvoip.io transport & logistics page: testimonial
 *
 * Anything marked TODO is a placeholder that must be confirmed before launch.
 */
window.WEBINAR = {
  brand: "Telvoip",
  series: "Telvoip Live",
  tagline: ["Connect.", "Engage.", "Resolve."],
  slug: "every-conversation-is-revenue",

  title: "Every conversation is revenue.",
  shortTitle: "Every Conversation Is Revenue",
  subtitle:
    "How African businesses turn calls, WhatsApps, emails and DMs into retention, upsell and referrals, run live on one Telvoip dashboard.",

  startUTC: "2026-11-12T08:00:00Z", // TODO confirm: Thu 12 Nov 2026, 11:00 EAT
  durationMin: 60,

  zones: [
    { city: "Nairobi", tz: "Africa/Nairobi" },
    { city: "Lagos", tz: "Africa/Lagos" },
    { city: "Johannesburg", tz: "Africa/Johannesburg" },
    { city: "Accra", tz: "Africa/Accra" },
  ],

  // Where the registration POSTs (JSON). Empty = front-end demo mode.
  registerEndpoint: "", // TODO: CRM / marketing automation webhook

  // Real Telvoip contacts (eFlyer).
  tollFree: "0800 230 094",
  email: "info@telvoip.io",
  salesEmail: "sales@telvoip.io",
  address: "4th Floor, Jahazi, Nairobi, Kenya",
  demoUrl: "http://calendar.app.google/8Xpic4cdsHNmQdDK8",
  site: "https://www.telvoip.io",

  whatsappNumber: "254700000000", // TODO real WhatsApp Business number, digits only
  smsNumber: "", // TODO short code or number for SMS sign-up
  keyword: "LIVE",

  streamEmbedUrl: "", // TODO
  replayEmbedUrl: "", // TODO
  replayAudioSizeMB: 28,
  replayVideoSizeMB: 410,

  // The six channels from the eFlyer. Used by the switchboard and the inbox rail.
  channels: [
    { id: "voice", label: "Voice", color: "#FF5C00" },
    { id: "whatsapp", label: "WhatsApp", color: "#25D366" },
    { id: "email", label: "Email", color: "#99D3FF" },
    { id: "messenger", label: "Messenger", color: "#B18CFF" },
    { id: "instagram", label: "Instagram", color: "#FF7AB6" },
    { id: "webchat", label: "Webchat", color: "#FFD08A" },
  ],

  // Switchboard traffic: industries from the eFlyer, no real customer conversations.
  traffic: [
    { ch: "voice", text: "Microfinance · loan balance query" },
    { ch: "whatsapp", text: "Pharmacy · is my order ready?" },
    { ch: "email", text: "Travel · change my booking" },
    { ch: "webchat", text: "Retail · size exchange" },
    { ch: "messenger", text: "Hospitality · table for six" },
    { ch: "instagram", text: "Florist · bulk order quote" },
    { ch: "voice", text: "Ride-hailing · driver ETA" },
    { ch: "whatsapp", text: "Fintech · M-Pesa reversal" },
    { ch: "email", text: "Logistics · proof of delivery" },
    { ch: "voice", text: "Healthcare · appointment slot" },
  ],

  // The ROI triad from "Customer Experience as a Revenue Engine".
  outcomes: [
    {
      word: "Retain",
      title: "Stop losing customers in the gaps between channels",
      body: "Watch one customer move from a call to WhatsApp to email without repeating themselves, and see what that does to churn.",
    },
    {
      word: "Upsell",
      title: "Turn a support call into the next sale",
      body: "Use the 360° customer view and AI summaries to spot the moment a question becomes a buying signal.",
    },
    {
      word: "Advocate",
      title: "Make CSAT and NPS predict revenue",
      body: "Score every interaction with AI QA, and treat satisfaction as an early warning system, not a vanity number.",
    },
  ],

  // Who's calling? Roles route the agenda.
  roles: [
    { id: "cx", label: "Contact centre / support lead" },
    { id: "sales", label: "Sales or collections lead" },
    { id: "exec", label: "Founder or executive" },
    { id: "it", label: "IT or telecoms" },
  ],

  // Agenda as an IVR journey. `for` lists the roles each segment is built for.
  agenda: [
    { min: 5, title: "Dial tone", body: "Why customer experience is a revenue line, not a cost centre.", for: ["exec", "cx", "sales"] },
    { min: 15, title: "One dashboard, live", body: "A real shift across voice, WhatsApp, email and social, from one login.", speaker: 0, for: ["cx", "it"] },
    { min: 15, title: "Revenue moments", body: "Spotting upsell and retention signals with the 360° view and AI summaries.", speaker: 1, for: ["sales", "exec"] },
    { min: 10, title: "AI QA", body: "Transcribe, score sentiment and auto-evaluate every interaction.", speaker: 1, for: ["cx", "exec"] },
    { min: 15, title: "Open line", body: "Your questions, answered live. Questions sent at registration go first.", speaker: 2, for: ["cx", "sales", "exec", "it"] },
  ],

  // TODO: real speakers.
  speakers: [
    { name: "Speaker One", role: "Head of Product, Telvoip", city: "Nairobi", tz: "Africa/Nairobi", skills: ["Omnichannel", "IVR"] },
    { name: "Speaker Two", role: "AI & Insights Lead, Telvoip", city: "Nairobi", tz: "Africa/Nairobi", skills: ["AI QA", "Analytics"] },
    { name: "Guest Speaker", role: "Customer Experience Director", city: "Lagos", tz: "Africa/Lagos", skills: ["CX strategy"] },
  ],

  // "Trusted by leading businesses across industries" (eFlyer).
  clients: [
    "Choice Microfinance Bank", "Omega Blooms", "Oracom Web Services", "Pharmily", "EnovePay Technologies",
    "Sunshine Travels & Tours", "Wasili Cabs", "BuySimu Technologies", "MPost Global", "Expertech Electricals",
  ],

  // Outcomes as published in Telvoip's blog case write-ups (customers not named there).
  // `from`/`to` drive the before/after meter; `unit` is shown on both.
  results: [
    { who: "E-commerce", metric: "Average wait", from: 180, to: 90, unit: "sec", note: "and first-call resolution up 35%, after skills-based routing" },
    { who: "Telecom · Kenya", metric: "Response time", from: 300, to: 120, unit: "sec", note: "after centralising every channel" },
    { who: "Fintech · South Africa", metric: "Peak wait", from: 100, to: 50, unit: "%", note: "halved with real-time routing and analytics" },
    { who: "Logistics · Kenya", metric: "Calls handled", from: 100, to: 130, unit: "%", note: "30% more calls on 20% lower staffing cost" },
    { who: "Remittance", metric: "Response time", from: 100, to: 65, unit: "%", note: "35% faster by unifying calls, SMS and WhatsApp" },
  ],

  testimonial: {
    quote: "Choosing Telvoip for our call centre needs has been one of the best decisions we've made. Their services have revolutionised the way we interact with our customers.",
    name: "Shanya Jodie",
    source: "telvoip.io",
  },

  faq: [
    { q: "Is it free?", a: "Yes. Registration and the replay are free." },
    { q: "Do I need to be a Telvoip customer?", a: "No. It's for anyone whose business talks to customers, whatever system you use today. As the eFlyer says: any industry, any size." },
    { q: "I'm on a weak connection. Can I still take part?", a: "Yes. Switch on Data saver (top right) for a lighter page, call " + "0800 230 094" + " to listen, or take the audio replay, a fraction of the size of the video." },
    { q: "Will there be a recording?", a: "Everyone who registers gets the replay, an AI summary and the slides within 24 hours." },
    { q: "Can I see Telvoip on my own use case?", a: "Yes. Book a free demo after the session and we'll set it up around your channels and team." },
  ],
};
