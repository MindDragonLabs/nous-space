const session = require("./session");

const HOSTS = new Set([
  "https://nous.minddragonlabs.com",
  "https://nous-space.vercel.app",
]);

function send(res, status, body, extraHeaders) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  if (extraHeaders) {
    Object.keys(extraHeaders).forEach(function (key) { res.setHeader(key, extraHeaders[key]); });
  }
  res.status(status).json(body);
}

function cleanName(name, max) {
  const value = String(name || "").replace(/\s+/g, " ").trim();
  const limit = max || 40;
  if (value.length < 2 || value.length > limit) return null;
  if (/https?:|www\.|@/i.test(value)) return null;
  if (!/^[\p{L}\p{N} .'_-]+$/u.test(value)) return null;
  return value;
}

function displayName(profile) {
  const fromName = cleanName(profile.name, 40);
  if (fromName) return fromName;
  return "Google user";
}

async function verifyGoogle(credential) {
  const clientId = process.env.GOOGLE_CLIENT_ID || "";
  if (!clientId || typeof credential !== "string" || credential.length < 20 || credential.length > 4000) return null;
  const response = await fetch("https://oauth2.googleapis.com/tokeninfo?id_token=" + encodeURIComponent(credential));
  if (!response.ok) return null;
  const data = await response.json();
  if (data.aud !== clientId) return null;
  if (data.email_verified !== "true" && data.email_verified !== true) return null;
  if (data.iss !== "accounts.google.com" && data.iss !== "https://accounts.google.com") return null;
  const exp = Number(data.exp) * 1000;
  if (!Number.isFinite(exp) || exp < Date.now()) return null;
  if (!data.sub) return null;
  const name = displayName(data);
  if (!name) return null;
  return { sub: String(data.sub), email: String(data.email || ""), name: name };
}

module.exports = async function handler(req, res) {
  try {
    const origin = String(req.headers.origin || "");
    if (req.method === "GET") {
      const user = session.sessionFromReq(req);
      return send(res, 200, {
        user: user ? { name: user.name } : null,
        clientId: process.env.GOOGLE_CLIENT_ID || "",
      });
    }
    if (!HOSTS.has(origin)) return send(res, 403, { error: "forbidden" });
    if (req.method === "DELETE") {
      return send(res, 200, { user: null }, { "Set-Cookie": session.clearCookie() });
    }
    if (req.method !== "POST") return send(res, 405, { error: "method" });
    const user = await verifyGoogle((req.body || {}).credential);
    if (!user) return send(res, 401, { error: "sign in failed" });
    return send(res, 200, { user: { name: user.name } }, { "Set-Cookie": session.sessionCookie(user) });
  } catch (err) {
    return send(res, 500, { error: "unavailable" });
  }
};
