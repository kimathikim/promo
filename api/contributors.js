// Contributors for the "Built by" section, pulled from the GitHub API.
//
//   GET /api/contributors -> { creator, contributors: [...], source }
//
// Cached at the CDN for an hour, so the page stays well inside GitHub's
// anonymous rate limit (60 requests/hour). Set GITHUB_TOKEN in Vercel for a
// higher limit. If GitHub is unreachable we still return the creator.

const REPO = process.env.PROMO_REPO || "kimathikim/promo";
const CREATOR = process.env.PROMO_CREATOR || "kimathikim";

// Shown when GitHub can't be reached; refreshed from the API when it can.
const CREATOR_FALLBACK = {
  login: "kimathikim",
  name: "Brian Kimathi",
  avatar_url: "https://avatars.githubusercontent.com/u/90571049?v=4",
  html_url: "https://github.com/kimathikim",
  location: "Nairobi, Kenya",
  company: "@ALX_Africa @telvoip.io",
  twitter_username: "b_kimathi",
  bio: "",
};

const LOGIN_RE = /^[A-Za-z0-9-]{1,39}(\[bot\])?$/;
const safeUrl = (u, prefix) => (typeof u === "string" && u.startsWith(prefix) ? u : "");
const str = (v, max) => (typeof v === "string" ? v.slice(0, max) : "");

async function gh(path) {
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "promo-leaderboard" };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const res = await fetch(`https://api.github.com${path}`, { headers });
  if (!res.ok) throw new Error(`github ${res.status}`);
  return res.json();
}

function cleanContributor(c) {
  if (!c || !LOGIN_RE.test(c.login || "")) return null;
  return {
    login: c.login,
    avatar_url: safeUrl(c.avatar_url, "https://avatars.githubusercontent.com/"),
    html_url: safeUrl(c.html_url, "https://github.com/"),
    contributions: Number(c.contributions) || 0,
    bot: c.type === "Bot" || /\[bot\]$/.test(c.login),
  };
}

function cleanCreator(u) {
  return {
    login: LOGIN_RE.test(u.login || "") ? u.login : CREATOR_FALLBACK.login,
    name: str(u.name, 80) || u.login,
    avatar_url: safeUrl(u.avatar_url, "https://avatars.githubusercontent.com/") || CREATOR_FALLBACK.avatar_url,
    html_url: safeUrl(u.html_url, "https://github.com/") || CREATOR_FALLBACK.html_url,
    location: str(u.location, 80),
    company: str(u.company, 80),
    twitter_username: /^[A-Za-z0-9_]{1,15}$/.test(u.twitter_username || "") ? u.twitter_username : "",
    bio: str(u.bio, 200),
  };
}

let memo = null; // warm-instance cache
const TTL = 3600 * 1000;

async function load() {
  if (memo && Date.now() - memo.at < TTL) return memo.data;
  const [list, user] = await Promise.allSettled([
    gh(`/repos/${REPO}/contributors?per_page=100`),
    gh(`/users/${CREATOR}`),
  ]);
  const contributors = list.status === "fulfilled" && Array.isArray(list.value)
    ? list.value.map(cleanContributor).filter(Boolean) : [];
  const creator = cleanCreator(user.status === "fulfilled" ? { ...CREATOR_FALLBACK, ...user.value } : CREATOR_FALLBACK);
  const mine = contributors.find((c) => c.login.toLowerCase() === creator.login.toLowerCase());
  creator.contributions = mine ? mine.contributions : 0;
  const data = {
    creator,
    contributors: contributors.filter((c) => c.login.toLowerCase() !== creator.login.toLowerCase()),
    source: list.status === "fulfilled" ? "github" : "fallback",
  };
  if (data.source === "github") memo = { at: Date.now(), data };
  return data;
}

module.exports = async function handler(req, res) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Access-Control-Allow-Origin", "*");
  try {
    const data = await load();
    res.setHeader("Cache-Control", data.source === "github"
      ? "public, s-maxage=3600, stale-while-revalidate=86400"
      : "public, s-maxage=60");
    res.statusCode = 200;
    res.end(JSON.stringify(data));
  } catch {
    res.statusCode = 200;
    res.setHeader("Cache-Control", "public, s-maxage=60");
    res.end(JSON.stringify({ creator: { ...cleanCreator(CREATOR_FALLBACK), contributions: 0 }, contributors: [], source: "fallback" }));
  }
};
