/*
 * Telvoip Live: every piece of webinar content lives here.
 * Change this file to run the next webinar; the four pages read from it.
 *
 * Anything marked TODO is a placeholder that must be confirmed before launch.
 */
window.WEBINAR = {
  brand: "Telvoip",
  series: "Telvoip Live",
  slug: "ringing-to-resolved",

  title: "From Ringing to Resolved",
  subtitle:
    "How African support and sales teams run one inbox for voice, WhatsApp, SMS and email, and let AI pick up the calls nobody is free to answer.",

  // Start time in UTC. The pages render it in each visitor's zone and in the
  // four zones our customers work in.
  startUTC: "2026-11-12T08:00:00Z", // TODO confirm: Thu 12 Nov 2026, 11:00 EAT
  durationMin: 60,

  // Zones shown on every time readout, in display order.
  zones: [
    { city: "Nairobi", tz: "Africa/Nairobi" },
    { city: "Lagos", tz: "Africa/Lagos" },
    { city: "Johannesburg", tz: "Africa/Johannesburg" },
    { city: "Accra", tz: "Africa/Accra" },
  ],

  // Where the registration form POSTs (JSON). Leave empty to run the pages
  // as a front-end demo: the registrant is kept in this browser only.
  registerEndpoint: "", // TODO: CRM / marketing automation webhook

  // Phone-first ways in, for people who'd rather not fill a form.
  dialIn: "+254 800 230 094", // TODO confirm audio-only bridge number
  whatsappNumber: "254700000000", // TODO real WhatsApp Business number, digits only
  whatsappKeyword: "LIVE",

  // Stream and replay. Empty values show a styled placeholder.
  streamEmbedUrl: "", // TODO e.g. YouTube/Vimeo/Zoom embed URL for the live room
  replayEmbedUrl: "", // TODO
  replayAudioSizeMB: 28,
  replayVideoSizeMB: 410,

  // What attendees leave with. Rendered as an IVR menu.
  outcomes: [
    {
      key: "1",
      title: "One inbox, every channel",
      body: "See how a single agent view handles a call, a WhatsApp thread and an email from the same customer without losing context.",
    },
    {
      key: "2",
      title: "AI that answers after hours",
      body: "Watch a voice assistant pick up at 21:00, answer from your knowledge base, and hand a real problem to a human with the full history.",
    },
    {
      key: "3",
      title: "Payments inside the conversation",
      body: "Walk through an M-Pesa and Airtel Money workflow that confirms a payment while the customer is still on the line.",
    },
    {
      key: "4",
      title: "Calls that hold on a weak network",
      body: "What actually keeps call quality up on low bandwidth, and how local numbers in Kenya, Nigeria, South Africa and Uganda change pick-up rates.",
    },
  ],

  // Agenda. Minutes must add up to durationMin. Each chapter becomes a
  // segment of the waveform timeline.
  agenda: [
    { min: 5, title: "Dial tone", body: "Why customers stop picking up, and what they do instead." },
    { min: 15, title: "One inbox, live", body: "A real agent shift across voice, WhatsApp, SMS and email.", speaker: 0 },
    { min: 15, title: "After-hours AI", body: "Voice assistant + knowledge base + clean human handoff.", speaker: 1 },
    { min: 10, title: "Pay on the call", body: "Mobile-money confirmation without leaving the conversation.", speaker: 0 },
    { min: 15, title: "Open line", body: "Your questions, answered live. Sent ones go first.", speaker: 2 },
  ],

  // TODO: real speakers. Initials are generated from the name.
  speakers: [
    { name: "Speaker One", role: "Head of Product, Telvoip", city: "Nairobi", tz: "Africa/Nairobi" },
    { name: "Speaker Two", role: "AI & Voice Lead, Telvoip", city: "Nairobi", tz: "Africa/Nairobi" },
    { name: "Guest Speaker", role: "Customer Experience Director", city: "Lagos", tz: "Africa/Lagos" },
  ],

  // Role question, answered with the keypad.
  roles: [
    { key: "1", label: "I run a contact centre or support team" },
    { key: "2", label: "I lead a sales team" },
    { key: "3", label: "I work in IT or telecoms" },
    { key: "4", label: "I'm a founder or executive" },
    { key: "0", label: "Something else" },
  ],

  faq: [
    {
      q: "Is it free?",
      a: "Yes. Registration is free and the replay is free.",
    },
    {
      q: "I have a weak connection. Can I still attend?",
      a: "Yes. Switch on Lite line (top right) for a text-only page, dial in for audio only, or take the audio replay, which is a fraction of the size of the video.",
    },
    {
      q: "Will there be a recording?",
      a: "Everyone who registers gets the replay, the transcript and the slides within 24 hours.",
    },
    {
      q: "Do I need to be a Telvoip customer?",
      a: "No. The session is for anyone running customer conversations in Africa, whatever system they use today.",
    },
  ],
};
