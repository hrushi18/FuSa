// Drives the HARA builder's session the way the view does — step by step, over a real shipped
// scenario — and prints what the walk produced. The row it ends with is the whole point of the
// tool, so it is built here by advancing through the sequence rather than by calling one
// function, and the ASIL is whatever the scripted server said and nothing else.
import { readFileSync } from "node:fs";
import { installDom } from "./dom.mjs";

const LEARN = process.argv[2];                       // path to static/learn
const SCENARIOS = process.argv[3];                   // path to content-sample/scenarios/hara.json
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
await import(`${LEARN}/app.js`);
const hara = await import(`${LEARN}/tools/hara.js`);
await new Promise(r => setTimeout(r, 20));

const scenarios = JSON.parse(readFileSync(SCENARIOS, "utf8"));
const worked = scenarios.find(s => s.reveal === "always");
const unassisted = scenarios.find(s => s.reveal === "never");

// A learner's own words, not the answer key: the tool must build a row out of whatever it is
// given. The rationale carries a comma and a quote, which is what CSV escaping is for.
const typed = {
  guideword: hara.GUIDEWORDS[0],
  malfunction: "the assist torque is applied in the wrong direction",
  hazardous_event: "the vehicle crosses into the next lane and is struck",
  rating: {severity: "S1", exposure: "E1", controllability: "C1"},
  rationale: 'S1 "minor" harm, E1 rarely, C1 the driver corrects it',
  safety_goal: "The unit shall not reverse the assist torque.",
};

async function walk(scenario, asilBody) {
  const session = hara.createSession(scenario);
  const answers = {...typed,
                   function: scenario.steps.function.options[0],
                   situation: scenario.steps.situation.options[0]};
  const seen = [], refused = [];
  for (;;) {
    const step = session.step();
    seen.push(step.key);
    if (step.kind === "asil") {
      fetchPlan = [{ok: true, body: asilBody}];
      await session.lookupAsil();
    } else if (step.key in answers) {
      session.next();                       // an unanswered step must not let the learner past
      if (session.step().key === step.key) refused.push(step.key);
      session.set(step.key, answers[step.key]);
    }
    if (session.done()) break;
    const before = session.at;
    session.next();
    if (session.at === before) throw new Error(`the walk is stuck on ${step.key}`);
  }
  return {session, seen, refused};
}

const results = {};
const looked_up = await walk(worked, {asil: "D", why: "S1-E1-C1 from the S×E×C table",
                                      key: "S1-E1-C1", filled: 36, total: 36});
results.steps = looked_up.seen;
results.refused_until_answered = looked_up.refused;
results.row_keys = Object.keys(looked_up.session.row());
results.row = looked_up.session.row();
results.csv = looked_up.session.csv();

const untranscribed = await walk(worked, {asil: null, why: "S1-E1-C1", key: "S1-E1-C1",
                                          filled: 0, total: 36});
results.untranscribed_asil_cell = untranscribed.session.row().asil;

// The unassisted case: the browser has no key to leak, because none was sent.
const blind = hara.createSession(unassisted);
results.unassisted_model_answers = hara.STEPS
  .map(s => blind.modelAnswer(s.key)).filter(a => a !== null);
results.worked_model_answer = hara.createSession(worked).modelAnswer("guideword");

console.log(JSON.stringify(results, null, 2));
