const crypto = require("crypto");
const { get, list, put } = require("@vercel/blob");
const session = require("./session");

const HOSTS = new Set([
  "https://nous.minddragonlabs.com",
  "https://nous-space.vercel.app",
]);
const MAX_LEN = 1000;
const MIN_WAIT_MS = 4000;
const TOKEN_TTL_MS = 2 * 60 * 60 * 1000;
const HOUR_LIMIT = 5;

function secret() {
  const value = process.env.FORUM_SECRET || "";
  if (value.length < 16) {
    const error = new Error("missing secret");
    error.status = 500;
    throw error;
  }
  return value;
}

function send(res, status, body) {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.status(status).json(body);
}

function clientIp(req) {
  const forwarded = String(req.headers["x-forwarded-for"] || "");
  return forwarded.split(",")[0].trim() || "0";
}

function ipHash(ip) {
  return crypto.createHmac("sha256", secret()).update(ip).digest("hex").slice(0, 24);
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

function cleanName(name) {
  const value = String(name || "").replace(/\s+/g, " ").trim();
  if (value.length < 2 || value.length > 24) return null;
  if (/https?:|www\.|@/i.test(value)) return null;
  if (!/^[\p{L}\p{N} .'_-]+$/u.test(value)) return null;
  return value;
}

function cleanText(text) {
  const value = String(text || "").replace(/\r\n/g, "\n").trim();
  if (value.length < 2 || value.length > MAX_LEN) return null;
  if (/[<>]/.test(value)) return null;
  if ((value.match(/https?:\/\//gi) || []).length > 2) return null;
  if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(value)) return null;
  return value;
}

function threadKey(kind, number) {
  if (kind !== "pr" && kind !== "issue") return null;
  if (!/^\d{1,8}$/.test(String(number))) return null;
  return { kind: kind, number: String(number) };
}

async function readJson(pathname) {
  try {
    const result = await get(pathname, { access: "private", useCache: false });
    if (!result || result.statusCode !== 200 || !result.stream) return null;
    const chunks = [];
    for await (const chunk of result.stream) chunks.push(Buffer.from(chunk));
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch (err) {
    return null;
  }
}

async function commentsFor(kind, number) {
  const prefix = "forum/v1/" + kind + "/" + number + "/";
  const blobs = [];
  let cursor;
  for (let page = 0; page < 8; page += 1) {
    const found = await list({ prefix: prefix, limit: 100, cursor: cursor });
    blobs.push.apply(blobs, found.blobs || []);
    if (!found.hasMore || !found.cursor) break;
    cursor = found.cursor;
  }
  const rows = [];
  for (let i = 0; i < blobs.length; i += 8) {
    const chunk = blobs.slice(i, i + 8);
    const loaded = await Promise.all(chunk.map(function (blob) { return readJson(blob.pathname); }));
    loaded.forEach(function (data) {
      if (data && data.text && data.name && data.id) rows.push(data);
    });
  }
  rows.sort(function (a, b) { return String(a.created).localeCompare(String(b.created)); });
  return rows.slice(-400).map(function (row) {
    return { id: row.id, name: row.name, text: row.text, created: row.created };
  });
}

async function underLimit(ip, account) {
  const hour = Math.floor(Date.now() / 3600000);
  const who = account ? "acct-" + ipHash(account) : ipHash(ip);
  const pathname = "forum-rl/v1/" + who + "/" + hour + ".json";
  const current = await readJson(pathname);
  const count = current && current.count ? Number(current.count) : 0;
  if (count >= HOUR_LIMIT) return false;
  await put(pathname, JSON.stringify({ count: count + 1 }), {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json",
  });
  return true;
}

module.exports = async function handler(req, res) {
  try {
    if (req.method === "GET") {
      const thread = threadKey(req.query.kind, req.query.number);
      if (!thread) {
        // Thread index for the forum page: every thread lives in the single
        // "general" category for now, both issues and pull requests.
        const blobs = [];
        let cursor;
        for (let page = 0; page < 20; page += 1) {
          const found = await list({ prefix: "forum/v1/", limit: 100, cursor: cursor });
          blobs.push.apply(blobs, found.blobs || []);
          if (!found.hasMore || !found.cursor) break;
          cursor = found.cursor;
        }
        const byThread = {};
        for (const blob of blobs) {
          const match = /^forum\/v1\/(pr|issue)\/(\d+)\//.exec(String(blob.pathname || ""));
          if (!match) continue;
          const key = match[1] + ":" + match[2];
          const row = byThread[key] || (byThread[key] = {
            category: "general",
            kind: match[1],
            number: Number(match[2]),
            comments: 0,
            last: "",
          });
          row.comments += 1;
          const modified = String(blob.uploadedAt || "");
          if (modified > row.last) row.last = modified;
        }
        const threads = Object.keys(byThread)
          .map((key) => byThread[key])
          .sort((a, b) => String(b.last).localeCompare(String(a.last)));
        return send(res, 200, { category: "general", threads: threads });
      }
      const now = Date.now();
      const token = sign({ k: thread.kind, n: thread.number, i: now, e: now + TOKEN_TTL_MS });
      const comments = await commentsFor(thread.kind, thread.number);
      return send(res, 200, { comments: comments, token: token });
    }
    if (req.method !== "POST") return send(res, 405, { error: "method" });
    const origin = String(req.headers.origin || "");
    if (!HOSTS.has(origin)) return send(res, 403, { error: "forbidden" });
    const body = req.body || {};
    if (body.company) return send(res, 400, { error: "rejected" });
    const user = session.sessionFromReq(req);
    if (!user) return send(res, 401, { error: "sign in" });
    const thread = threadKey(body.kind, body.number);
    const name = user.name;
    const text = cleanText(body.text);
    const token = verify(body.token);
    if (!thread || !name || !text || !token) return send(res, 400, { error: "rejected" });
    if (token.k !== thread.kind || String(token.n) !== thread.number) return send(res, 400, { error: "rejected" });
    const now = Date.now();
    if (typeof token.i !== "number" || typeof token.e !== "number") return send(res, 400, { error: "rejected" });
    if (now < token.i + MIN_WAIT_MS || now > token.e) return send(res, 400, { error: "slow down" });
    if (!(await underLimit(clientIp(req), user.sub))) return send(res, 429, { error: "too many comments" });
    const existing = await commentsFor(thread.kind, thread.number);
    if (existing.some(function (comment) { return comment.text === text && comment.name === name; })) {
      return send(res, 400, { error: "duplicate" });
    }
    const id = crypto.randomBytes(8).toString("hex");
    const created = new Date().toISOString();
    const comment = {
      id: id,
      kind: thread.kind,
      number: Number(thread.number),
      name: name,
      text: text,
      created: created,
      sub: user.sub,
    };
    await put(
      "forum/v1/" + thread.kind + "/" + thread.number + "/" + Date.now() + "-" + id + ".json",
      JSON.stringify(comment),
      {
        access: "private",
        addRandomSuffix: false,
        contentType: "application/json",
      }
    );
    return send(res, 201, { comment: { id: id, name: name, text: text, created: created } });
  } catch (err) {
    return send(res, 500, { error: "unavailable" });
  }
};
