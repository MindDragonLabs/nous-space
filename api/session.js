const crypto = require("crypto");

const SESSION_MS = 14 * 24 * 60 * 60 * 1000;

function secret() {
  const value = process.env.FORUM_SECRET || "";
  if (value.length < 16) {
    const error = new Error("missing secret");
    error.status = 500;
    throw error;
  }
  return value;
}

function sign(payload) {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const mac = crypto.createHmac("sha256", secret()).update(body).digest("base64url");
  return body + "." + mac;
}

function verify(token) {
  if (typeof token !== "string") return null;
  const dot = token.indexOf(".");
  if (dot < 1) return null;
  const body = token.slice(0, dot);
  const mac = token.slice(dot + 1);
  const expected = crypto.createHmac("sha256", secret()).update(body).digest("base64url");
  const left = Buffer.from(mac);
  const right = Buffer.from(expected);
  if (left.length !== right.length || !crypto.timingSafeEqual(left, right)) return null;
  try {
    return JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
  } catch (err) {
    return null;
  }
}

function readCookie(req, name) {
  const raw = String(req.headers.cookie || "");
  const parts = raw.split(";").map(function (part) { return part.trim(); });
  const hit = parts.find(function (part) { return part.startsWith(name + "="); });
  if (!hit) return "";
  try {
    return decodeURIComponent(hit.slice(name.length + 1));
  } catch (err) {
    return "";
  }
}

function sessionFromReq(req) {
  const payload = verify(readCookie(req, "nous_session"));
  if (!payload || typeof payload.e !== "number" || payload.e < Date.now()) return null;
  if (!payload.sub || !payload.name) return null;
  return { sub: String(payload.sub), name: String(payload.name), email: String(payload.email || "") };
}

function sessionCookie(user) {
  const now = Date.now();
  const token = sign({
    sub: user.sub,
    name: user.name,
    email: user.email || "",
    i: now,
    e: now + SESSION_MS,
  });
  return "nous_session=" + token + "; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=" + Math.floor(SESSION_MS / 1000);
}

function clearCookie() {
  return "nous_session=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0";
}

module.exports = {
  sign: sign,
  verify: verify,
  sessionFromReq: sessionFromReq,
  sessionCookie: sessionCookie,
  clearCookie: clearCookie,
};
