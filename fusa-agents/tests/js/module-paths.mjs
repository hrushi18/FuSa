// Runs renderModule for real, so "a tool card launches a tool" is proven by executing the
// renderer rather than grepping module.js for a substring that could sit in a dead branch.
import { installDom } from "./dom.mjs";
const LEARN = process.argv[2];
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
// app.js runs load() at import time — give it a good first pair, same as progress-paths.mjs.
fetchPlan = [{ok: true, body: {groups: [], modules: [], paths: [], glossary: {},
                               content_errors: [], pass_mark: 0.8}},
             {ok: true, body: {modules: {}, pass_mark: 0.8}}];
await import(`${LEARN}/app.js`);
const { renderModule } = await import(`${LEARN}/module.js`);
await new Promise(r => setTimeout(r, 20));

function makeHost() {
  return {
    innerHTML: "",
    querySelector: () => ({onclick: null, querySelectorAll: () => []}),
    querySelectorAll: () => [],
  };
}

const mod = {
  id: "concept.hara", title: "Hazard Analysis", clauses: [],
  cards: [{type: "tool", tool: "hara", title: "Build this hazard as a row",
           body: "Open the HARA Builder and finish the row."}],
};
const host = makeHost();
renderModule(mod, host);

console.log(JSON.stringify({html: host.innerHTML}));
