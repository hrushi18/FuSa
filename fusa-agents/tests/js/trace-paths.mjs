// Drives the Traceability Lab under node, over a case the server really built. The scoring is
// the part worth executing rather than grepping: three independent judgements is the whole
// design, and a scorer that quietly collapsed them into one number would still contain every
// string a structural test looks for.
import { readFileSync } from "node:fs";
import { installDom } from "./dom.mjs";

const LEARN = process.argv[2];                       // path to static/learn
const CASE = JSON.parse(readFileSync(process.argv[3], "utf8"));   // a case from trace_case()

installDom(["#search", "#banner", "#learn-nav", "#learn-crumb", "#learn-progress", "#learn-main"]);
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
fetchPlan = [{ok: true, body: {groups: [], modules: [], paths: [], glossary: {},
                               content_errors: [], pass_mark: 0.8}},
             {ok: true, body: {modules: {}, pass_mark: 0.8}}];
await import(`${LEARN}/app.js`);
const trace = await import(`${LEARN}/tools/trace.js`);
await new Promise(r => setTimeout(r, 20));

const key = Object.fromEntries(trace.PARTS.map(p => [p, CASE.questions[p].answer]));
const wrong = p => (CASE.questions[p].answer + 1) % CASE.questions[p].options.length;

const results = {parts: trace.PARTS};

results.all_right = trace.scoreTrace(CASE, key);
results.all_wrong = trace.scoreTrace(CASE,
  Object.fromEntries(trace.PARTS.map(p => [p, wrong(p)])));
// The case the rubric exists for: the break found, its owner mistaken.
results.partly = trace.scoreTrace(CASE, {...key, phase: wrong("phase")});
results.unanswered = trace.scoreTrace(CASE, {link: key.link});

// A wrong part must carry both reasons: why the pick was wrong and what was right.
results.partly_phase = results.partly.parts.find(p => p.key === "phase");

// ---- the two states the view can be in --------------------------------------
function fakeHost() {
  return {innerHTML: "", querySelector: () => ({onclick: null, value: "0", disabled: false}),
          querySelectorAll: () => []};
}

const ready = fakeHost();
fetchPlan = [{ok: true, body: CASE}];
trace.renderTrace(ready);
await new Promise(r => setTimeout(r, 20));
results.ready_html = ready.innerHTML;

const empty = fakeHost();
fetchPlan = [{ok: true, body: {ready: false, seed: 1, reason: "SADS has not been produced yet",
                               missing: ["SADS", "TSR"]}}];
trace.renderTrace(empty);
await new Promise(r => setTimeout(r, 20));
results.empty_html = empty.innerHTML;

// Every value the server sends is spliced into markup, so one hostile goal text is enough to
// tell whether it goes through esc() or not.
const hostile = fakeHost();
fetchPlan = [{ok: true, body: {...CASE,
  goal: {...CASE.goal, text: '<script>alert("x")</script>'}}}];
trace.renderTrace(hostile);
await new Promise(r => setTimeout(r, 20));
results.hostile_html = hostile.innerHTML;

console.log(JSON.stringify(results, null, 2));
