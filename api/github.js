const REPO = "NousResearch/hermes-agent";
const TTL_MS = 5 * 60 * 1000;
const cache = new Map();

function send(res, status, body) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("X-Content-Type-Options", "nosniff");
  if (status === 200) res.setHeader("Cache-Control", "public, max-age=60, s-maxage=300");
  else res.setHeader("Cache-Control", "no-store");
  res.status(status).json(body);
}

function slimItem(item) {
  return {
    title: item.title || "",
    number: item.number,
    body: item.body || "",
    body_html: item.body_html || "",
    html_url: item.html_url || "",
    comments: item.comments || 0,
    user: { login: (item.user && item.user.login) || "" },
  };
}

function slimComment(comment) {
  return {
    body: comment.body || "",
    body_html: comment.body_html || "",
    created_at: comment.created_at || "",
    user: { login: (comment.user && comment.user.login) || "" },
  };
}

async function githubGet(path) {
  const headers = {
    Accept: "application/vnd.github.full+json",
    "User-Agent": "nous-space",
  };
  const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN || "";
  if (token) headers.Authorization = "Bearer " + token;
  const response = await fetch("https://api.github.com" + path, { headers: headers });
  if (!response.ok) {
    const error = new Error("github " + response.status);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

module.exports = async function handler(req, res) {
  try {
    if (req.method !== "GET") return send(res, 405, { error: "method" });
    const kind = req.query.kind === "issue" ? "issue" : "pr";
    const number = String(req.query.number || "");
    if (!/^\d{1,8}$/.test(number)) return send(res, 400, { error: "bad number" });
    const key = kind + ":" + number;
    const hit = cache.get(key);
    if (hit && hit.exp > Date.now()) return send(res, 200, hit.body);
    const itemPath = "/repos/" + REPO + (kind === "issue" ? "/issues/" : "/pulls/") + number;
    const item = await githubGet(itemPath);
    const count = Number(item && item.comments) || 0;
    const page = Math.max(1, Math.ceil(count / 100));
    let comments = [];
    let commentsOk = true;
    try {
      const loaded = await githubGet(
        "/repos/" + REPO + "/issues/" + number + "/comments?per_page=100&page=" + page
      );
      comments = Array.isArray(loaded) ? loaded : [];
    } catch (err) {
      commentsOk = false;
    }
    const body = {
      item: slimItem(item || {}),
      comments: comments.map(slimComment),
      truncated: page > 1,
    };
    if (commentsOk) cache.set(key, { exp: Date.now() + TTL_MS, body: body });
    return send(res, 200, body);
  } catch (err) {
    const status = err && err.status === 404 ? 404 : 502;
    return send(res, status, { error: "unavailable" });
  }
};
