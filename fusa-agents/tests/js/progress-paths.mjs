import { installDom } from "./dom.mjs";
const LEARN = process.argv[2];                       // path to static/learn
const els = installDom(["#search", "#banner", "#learn-nav", "#learn-crumb",
                        "#learn-progress", "#learn-main"]);
let fetchPlan = [];
globalThis.fetch = () => {
  const next = fetchPlan.shift() ?? {ok: true, body: {}};
  return Promise.resolve({
    ok: next.ok, status: next.status ?? (next.ok ? 200 : 500),
    headers: {get: () => null},
    json: () => Promise.resolve(next.body),
    text: () => Promise.resolve(typeof next.body === "string" ? next.body : JSON.stringify(next.body)),
  });
};
// app.js runs load() at import time — give it a good first pair
fetchPlan = [{ok: true, body: {groups: [], modules: [], paths: [], glossary: {},
                               content_errors: [], pass_mark: 0.8}},
             {ok: true, body: {modules: {}, pass_mark: 0.8}}];
const app = await import(`${LEARN}/app.js`);
const { saveProgress } = await import(`${LEARN}/progress.js`);
await new Promise(r => setTimeout(r, 20));

const results = {};
// 1. happy path returns the record
fetchPlan = [{ok: true, body: {best: 0.9, status: "passed"}}];
results.saved = await saveProgress("concept.hara", {score: 0.9});

// 2. a failed save reaches the banner instead of vanishing
els["#banner"].textContent = "";
fetchPlan = [{ok: false, status: 500, body: {detail: "disk full"}}];
results.failed_returns = await saveProgress("concept.hara", {score: 0.9});
results.failed_banner = els["#banner"].textContent;

// 3. a non-JSON error body (an HTML 500 page) still produces a readable message
els["#banner"].textContent = "";
fetchPlan = [{ok: false, status: 500, body: "<html>Internal Server Error</html>"}];
await saveProgress("concept.hara", {score: 0.1});
results.html_error_banner = els["#banner"].textContent;

console.log(JSON.stringify(results, null, 2));
