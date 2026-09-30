// Local stand-in for Vercel: serves public/ and the squad API with the same
// rewrites as vercel.json, storing data in memory.   node scripts/dev.js [port]
const http = require("http");
const fs = require("fs");
const path = require("path");
const handler = require("../api/squad.js");

const PUBLIC = path.join(__dirname, "..", "public");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon" };
const port = Number(process.argv[2] || 3000);
// apply the same security headers as production
const HEADERS = require("../vercel.json").headers.flatMap((h) => h.headers);

http.createServer((req, res) => {
  for (const { key, value } of HEADERS) res.setHeader(key, value);
  const url = new URL(req.url, "http://localhost");
  let m = url.pathname.match(/^\/r\/([^/]+)\/api(?:\/([^/]+))?\/?$/);
  if (m) {
    url.pathname = "/api/squad";
    url.searchParams.set("room", m[1]);
    if (m[2]) url.searchParams.set("action", m[2]);
    req.url = url.pathname + url.search;
  }
  if (url.pathname === "/api/squad") return handler(req, res);
  let file = /^\/r\/[^/]+\/?$/.test(url.pathname) || url.pathname === "/" ? "/index.html" : url.pathname;
  file = path.join(PUBLIC, path.normalize(file).replace(/^(\.\.[/\\])+/, ""));
  fs.readFile(file, (err, data) => {
    if (err) { res.statusCode = 404; return res.end("not found"); }
    res.setHeader("Content-Type", TYPES[path.extname(file)] || "application/octet-stream");
    res.end(data);
  });
}).listen(port, () => console.log(`promo leaderboard on http://localhost:${port}`));
