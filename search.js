(function () {
  "use strict";

  var FIELD_NAMES = ["author", "label", "repo", "is", "kind"];

  function parseQuery(raw) {
    var source = raw == null ? "" : String(raw);
    var fields = { author: "", label: "", repo: "", is: "", kind: "" };
    var tokens = [];
    var parts = source.trim() ? source.trim().split(/\s+/) : [];
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i];
      var lower = part.toLowerCase();
      var number = /^#(\d+)$/.exec(part);
      if (number) {
        fields.number = number[1];
        continue;
      }
      var consumed = false;
      for (var f = 0; f < FIELD_NAMES.length; f++) {
        var key = FIELD_NAMES[f];
        var prefix = key + ":";
        if (lower.indexOf(prefix) === 0) {
          fields[key] = lower.slice(prefix.length);
          consumed = true;
          break;
        }
      }
      if (!consumed) tokens.push(lower);
    }
    return { raw: source, tokens: tokens, fields: fields };
  }

  function isBlank(parsed) {
    if (parsed.tokens.length) return false;
    var fields = parsed.fields;
    return !fields.author && !fields.label && !fields.repo && !fields.is && !fields.kind &&
      (fields.number == null || fields.number === "");
  }

  function tsOf(doc) {
    if (!doc || typeof doc !== "object") return 0;
    var ts = Number(doc.ts);
    return Number.isFinite(ts) ? ts : 0;
  }

  function haystack(doc) {
    var d = doc && typeof doc === "object" ? doc : {};
    var labels = "";
    if (Array.isArray(d.labels)) labels = d.labels.join(" ");
    else if (d.labels != null) labels = String(d.labels);
    return [d.title, d.text, d.author, d.repo, labels, d.number == null ? "" : String(d.number), d.state, d.kind]
      .map(function (part) { return part == null ? "" : String(part); })
      .join(" ")
      .toLowerCase();
  }

  function hasSub(value, needle) {
    return String(value == null ? "" : value).toLowerCase().indexOf(needle) !== -1;
  }

  function labelHit(doc, needle) {
    var labels = doc && Array.isArray(doc.labels) ? doc.labels : [];
    for (var i = 0; i < labels.length; i++) {
      if (hasSub(labels[i], needle)) return true;
    }
    return false;
  }

  function matchesIs(doc, value) {
    var d = doc && typeof doc === "object" ? doc : {};
    var state = String(d.state || "").toLowerCase().trim();
    var queue = String(d.queue || "").toLowerCase().trim();
    var review = String(d.review || "").toLowerCase().trim();
    var ci = String(d.ci || "").toLowerCase().trim();
    if (value === "open" || value === "closed") return state === value;
    if (value === "draft") return state === "draft" || queue === "draft";
    if (value === "approved") return review === "approved" || queue === "approved";
    if (value === "failing") return ci === "failing";
    if (value === "unassigned") return d.unassigned === true;
    if (value === "new") return d.new === true;
    return false;
  }

  function matches(doc, parsed) {
    var d = doc && typeof doc === "object" ? doc : {};
    var fields = parsed.fields;
    if (fields.author && !hasSub(d.author, fields.author)) return false;
    if (fields.repo && !hasSub(d.repo, fields.repo)) return false;
    if (fields.kind && !hasSub(d.kind, fields.kind)) return false;
    if (fields.label && !labelHit(d, fields.label)) return false;
    if (fields.number != null && fields.number !== "" && String(d.number) !== fields.number) return false;
    if (fields.is && !matchesIs(d, fields.is)) return false;
    var blob = haystack(d);
    for (var i = 0; i < parsed.tokens.length; i++) {
      if (blob.indexOf(parsed.tokens[i]) === -1) return false;
    }
    return true;
  }

  function escapeReg(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function wholeWord(title, token) {
    return new RegExp("(^|[^a-z0-9])" + escapeReg(token) + "($|[^a-z0-9])").test(title);
  }

  function tokenFieldHit(doc, token) {
    var d = doc && typeof doc === "object" ? doc : {};
    if (hasSub(d.author, token) || hasSub(d.repo, token) || hasSub(d.kind, token)) return true;
    return labelHit(d, token);
  }

  function scoreDoc(doc, parsed) {
    var d = doc && typeof doc === "object" ? doc : {};
    var score = 0;
    var fields = parsed.fields;
    if (fields.number) score += 100;
    if (fields.author) score += 20;
    if (fields.label) score += 20;
    if (fields.repo) score += 20;
    if (fields.kind) score += 20;
    var title = String(d.title || "").toLowerCase().trim();
    var number = d.number == null ? "" : String(d.number).toLowerCase();
    for (var i = 0; i < parsed.tokens.length; i++) {
      var token = parsed.tokens[i];
      if (number && token === number) score += 100;
      else if (title.indexOf(token) === 0) score += 40;
      else if (wholeWord(title, token)) score += 24;
      else if (tokenFieldHit(d, token)) score += 20;
      else score += 8;
    }
    var ts = tsOf(d);
    score += Math.min(5, Math.max(0, ts) / 1e12);
    return score;
  }

  function searchDocs(docs, rawQuery, limit) {
    var list = Array.isArray(docs) ? docs : [];
    var cap = limit == null ? 40 : Number(limit);
    var size = Math.max(0, Number.isFinite(cap) ? cap : 40);
    var parsed = parseQuery(rawQuery);
    if (isBlank(parsed)) {
      var ordered = list.map(function (doc, idx) {
        return { doc: doc, idx: idx, ts: tsOf(doc) };
      });
      ordered.sort(function (a, b) { return b.ts - a.ts || a.idx - b.idx; });
      return {
        total: list.length,
        hits: ordered.slice(0, size).map(function (row) { return { doc: row.doc, score: 0 }; }),
      };
    }
    var hits = [];
    for (var i = 0; i < list.length; i++) {
      if (!matches(list[i], parsed)) continue;
      hits.push({
        doc: list[i],
        score: scoreDoc(list[i], parsed),
        ts: tsOf(list[i]),
        idx: i,
      });
    }
    hits.sort(function (a, b) { return b.score - a.score || b.ts - a.ts || a.idx - b.idx; });
    return {
      total: hits.length,
      hits: hits.slice(0, size).map(function (row) { return { doc: row.doc, score: row.score }; }),
    };
  }

  var api = { parseQuery: parseQuery, searchDocs: searchDocs };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.NousSearch = api;
})();
