import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { parseQuery, searchDocs } = require("./search.js");

test("empty query returns all up to limit, newest first", () => {
  const docs = [
    { title: "a", ts: 1 },
    { title: "b", ts: 3 },
    { title: "c" },
    { title: "d", ts: 2, extra: 1 },
  ];
  const limited = searchDocs(docs, "   ", 2);
  assert.equal(limited.total, 4);
  assert.equal(limited.hits.length, 2);
  assert.equal(limited.hits[0].doc.title, "b");
  assert.equal(limited.hits[0].score, 0);
  assert.equal(limited.hits[1].doc.title, "d");
  assert.equal(limited.hits[1].doc.extra, 1);

  const all = searchDocs(docs, "");
  assert.equal(all.total, 4);
  assert.equal(all.hits.length, 4);
  assert.deepEqual(all.hits.map((hit) => hit.doc.title), ["b", "d", "a", "c"]);
});

test("AND tokens", () => {
  const docs = [
    { title: "Alpha", text: "beta gamma", ts: 1 },
    { title: "Alpha only", text: "", ts: 2 },
    { title: "Gamma", text: "beta", ts: 3 },
  ];
  const res = searchDocs(docs, "Alpha BETA");
  assert.equal(res.total, 1);
  assert.equal(res.hits[0].doc.title, "Alpha");
});

test("author: field is a case-insensitive substring and not a text token", () => {
  const parsed = parseQuery("author:Ali orphan");
  assert.equal(parsed.fields.author, "ali");
  assert.deepEqual(parsed.tokens, ["orphan"]);
  const docs = [
    { title: "Fix", author: "Alice", text: "bob mentioned", ts: 1 },
    { title: "Other", author: "Bob", text: "ali is here", ts: 2 },
  ];
  const res = searchDocs(docs, "author:ali");
  assert.equal(res.total, 1);
  assert.equal(res.hits[0].doc.author, "Alice");
});

test("#number exact", () => {
  const parsed = parseQuery("see #123");
  assert.equal(parsed.fields.number, "123");
  assert.deepEqual(parsed.tokens, ["see"]);
  const docs = [
    { title: "Issue 12", number: 12, ts: 1 },
    { title: "Issue 123", number: 123, ts: 5 },
    { title: "mentions #123", number: 9, text: "123", ts: 9 },
  ];
  const res = searchDocs(docs, "#123");
  assert.equal(res.total, 1);
  assert.equal(res.hits[0].doc.number, 123);
});

test("is:draft matches state or queue", () => {
  const docs = [
    { title: "A", state: "open", queue: "draft", ts: 1 },
    { title: "B", state: "draft", ts: 2 },
    { title: "C", state: "open", queue: "needs-review", ts: 3 },
  ];
  const res = searchDocs(docs, "is:Draft");
  assert.equal(res.total, 2);
  assert.deepEqual(res.hits.map((hit) => hit.doc.title).sort(), ["A", "B"]);
});

test("ranking title-prefix above body-only", () => {
  const docs = [
    { title: "notes", text: "parser lives here", ts: 9e12, kind: "issue" },
    { title: "parser internals", text: "unrelated", ts: 1, kind: "issue" },
  ];
  const res = searchDocs(docs, "parser");
  assert.equal(res.total, 2);
  assert.equal(res.hits[0].doc.title, "parser internals");
  assert.ok(res.hits[0].score > res.hits[1].score);
});

test("no match returns total 0", () => {
  const res = searchDocs([{ title: "hello", text: "world", ts: 1 }], "zzzz-not-here");
  assert.equal(res.total, 0);
  assert.deepEqual(res.hits, []);
});
