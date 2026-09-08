// The HARA method walked one step at a time. This file is the mechanism only: the cases come
// from `content-sample/scenarios/hara.json` through the server, so a team's own worked examples
// replace them without touching any JavaScript.
//
// The distinction the sequence exists to make concrete — and the one most often missed — is
// that a hazard is the item misbehaving and cannot be rated, while a hazardous event is that
// hazard in a situation and is the only thing that can. The ASIL then comes from the server's
// lookup over the engineer's own transcribed table, never from anything computed here.
import { api, banner } from "../app.js";
import { esc } from "../esc.js";

// The columns of input/hazards.csv, in its order. A finished exercise is meant to paste
// straight into the real chain's input table, so a test holds these two lists together.
export const COLUMNS = ["id", "function", "malfunction", "hazardous_event", "situation",
                        "severity", "exposure", "controllability", "rationale", "asil"];

export const GUIDEWORDS = ["too late", "too early", "omission", "commission",
                           "too high", "too low", "reverse", "other"];

const SCALES = {severity: ["S0", "S1", "S2", "S3"],
                exposure: ["E0", "E1", "E2", "E3", "E4"],
                controllability: ["C0", "C1", "C2", "C3"]};

export const STEPS = [
  {key: "item", kind: "read", title: "The item",
   ask: `Read what the item does and where its authority stops. Every line below is derived
         from this paragraph and from nothing else.`},
  {key: "function", kind: "choose", title: "An activity or output",
   ask: `Pick something the item does to the vehicle. Housekeeping it does for the workshop
         cannot hurt anyone by itself, so it generates no hazard.`},
  {key: "guideword", kind: "guideword", title: "A guideword",
   ask: `Apply a guideword to that output. The list exists so the set of malfunctions is
         generated systematically rather than remembered — a real analysis walks all eight.`},
  {key: "malfunction", kind: "text", title: "The hazard",
   ask: `Write the output misbehaving in that way, at vehicle level. This is the hazard. It
         names no road, no speed and no traffic, so on its own it cannot be rated.`},
  {key: "situation", kind: "choose", title: "The situation",
   ask: `Choose an operating situation the vehicle really spends time in. Exposure is a
         statement about the situation, so one nobody drives in rates nothing.`},
  {key: "hazardous_event", kind: "text", title: "The hazardous event",
   ask: `Now pair the hazard with the situation, in one sentence that ends in harm to people.
         This pair is what gets rated — the hazard alone never is.`},
  {key: "rating", kind: "rating", title: "Severity, exposure, controllability",
   ask: `Rate the event you just wrote. Severity is how badly the harm hurts, exposure how much
         of the time the vehicle is in that situation, controllability whether the people
         involved can act in time.`},
  {key: "rationale", kind: "text", title: "The rationale",
   ask: `One clause per class, in the order they were rated. A reviewer who disagrees with the
         ASIL argues with this sentence, so it is the most re-read cell in the table.`},
  {key: "asil", kind: "asil", title: "The ASIL",
   ask: `Not a judgement and not a formula: a lookup in the S×E×C table your project
         transcribed from its licensed copy of the standard.`},
  {key: "safety_goal", kind: "text", title: "The safety goal",
   ask: `State the vehicle-level property to preserve, inheriting the ASIL of the event it
         mitigates. It names no solution — how to achieve it is a later argument.`},
  {key: "row", kind: "row", title: "Your row",
   ask: `The exercise as the chain reads it. Paste it into input/hazards.csv and the same
         agents that produce the real HARA will produce yours.`},
];

const MODES = {always: "worked — the answer is shown at every step",
               submit: "guided — the answer appears when you check",
               never: "unassisted — no answer key"};

const stepOf = key => STEPS.find(s => s.key === key);
const NEEDS_ANSWER = new Set(["choose", "guideword", "text", "rating"]);

// A cell only needs quoting when it carries a delimiter, and the rationale column routinely
// does. Doubling the quote is the CSV escape Python's own reader expects.
const csvCell = v => (/[",\n]/.test(v) ? `"${String(v).replace(/"/g, '""')}"` : String(v));

/** One learner's walk through one scenario, with no DOM in it — so the sequence and the row it
 *  produces can be driven and checked without a browser. */
export function createSession(scenario) {
  const answers = {};
  let at = 0, asil = null;

  const filled = key => {
    const v = answers[key];
    if (stepOf(key).kind === "rating") {
      return Boolean(v && v.severity && v.exposure && v.controllability);
    }
    return typeof v === "string" ? v.trim() !== "" : v != null;
  };

  const session = {
    scenario,
    steps: STEPS,
    get at() { return at; },
    step: () => STEPS[at],
    value: key => answers[key],
    filled,
    /** The model answer in the form the learner would have given it, or null when this case
     *  ships no key at all. */
    modelAnswer(key) {
      const step = scenario.steps?.[key];
      if (!step || !("answer" in step)) return null;
      return stepOf(key).kind === "choose" ? step.options[step.answer] : step.answer;
    },
    why: key => scenario.steps?.[key]?.why || "",
    options: key => scenario.steps?.[key]?.options || [],
    set(key, value) { answers[key] = value; return session; },
    canAdvance: () => !NEEDS_ANSWER.has(STEPS[at].kind) || filled(STEPS[at].key),
    next() { if (at < STEPS.length - 1 && session.canAdvance()) at += 1; return session; },
    prev() { if (at > 0) at -= 1; return session; },
    goto(i) { at = Math.max(0, Math.min(STEPS.length - 1, i)); return session; },
    done: () => STEPS[at].kind === "row",

    asil: () => asil,
    /** The one answer this tool is not allowed to work out for itself. */
    async lookupAsil() {
      const r = answers.rating || {};
      const q = new URLSearchParams({s: r.severity || "", e: r.exposure || "",
                                     c: r.controllability || ""});
      asil = await api(`/api/learn/asil?${q}`);
      return asil;
    },

    row() {
      const r = answers.rating || {};
      const cells = {
        id: scenario.hazard_id, function: answers.function, malfunction: answers.malfunction,
        hazardous_event: answers.hazardous_event, situation: answers.situation,
        severity: r.severity, exposure: r.exposure, controllability: r.controllability,
        rationale: answers.rationale,
        // Left blank when the project's table has no value for these classes. The chain then
        // marks the row PENDING itself, which is the honest outcome; a letter invented here
        // would travel all the way down the chain with nothing able to notice.
        asil: asil?.asil,
      };
      return Object.fromEntries(COLUMNS.map(c => [c, String(cells[c] ?? "")]));
    },
    csv() {
      const row = session.row();
      return COLUMNS.map(c => csvCell(row[c])).join(",");
    },
  };
  return session;
}

export function renderHara(host) {
  let session = null, pending = null;
  const checked = new Set();          // steps whose answer the learner has asked to see

  const head = `<h2 style="font-size:16px;margin:0 0 4px">HARA Builder</h2>
    <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
      Item to safety goal, one step at a time. The rating comes from your project's S×E×C
      table, and the finished row pastes into <code>input/hazards.csv</code>.</p>`;

  const pickScenario = (scenarios) => {
    host.innerHTML = head + scenarios.map((s, i) => `
      <div class="card">
        <span class="kind">${esc(MODES[s.reveal] || s.reveal)}</span>
        <h3>${esc(s.title)}</h3>
        <p>${esc(s.item)}</p>
        <div class="pager" style="margin-top:14px">
          <button data-s="${i}">Start</button>
          <span class="dots">row <code>${esc(s.hazard_id)}</code></span>
        </div>
      </div>`).join("");
    host.querySelectorAll("button[data-s]").forEach(el => {
      el.onclick = () => {
        session = createSession(scenarios[Number(el.dataset.s)]);
        checked.clear();
        draw();
      };
    });
  };

  const revealed = key => session.scenario.reveal === "always"
                       || (session.scenario.reveal === "submit" && checked.has(key));

  const answerHtml = (key) => {
    const model = session.modelAnswer(key);
    if (model === null || !revealed(key)) return "";
    const shown = stepOf(key).kind === "rating"
      ? `${model.severity} · ${model.exposure} · ${model.controllability}` : model;
    return `<div class="model">
      <span class="kind">one worked answer</span>
      <p>${esc(shown)}</p>
      ${session.why(key) ? `<div class="why-line">${esc(session.why(key))}</div>` : ""}</div>`;
  };

  // The point of the whole sequence, put side by side the moment both halves exist.
  const pairHtml = () => {
    const hazard = session.value("malfunction"), event = session.value("hazardous_event");
    if (!hazard || !event) return "";
    return `<div class="pair">
      <p><b>Hazard</b> — ${esc(hazard)}<br><span class="hint">the item misbehaving; no
        situation in it, so nothing to rate</span></p>
      <p><b>Hazardous event</b> — ${esc(event)}<br><span class="hint">the hazard in a
        situation; this is what carries S, E and C</span></p></div>`;
  };

  const asilHtml = () => {
    const r = session.asil();
    if (pending || !r) return `<p class="hint">asking the server…</p>`;
    if (r.asil === null) {
      return `<div class="unfilled">
        <b>${esc(r.key)} is not transcribed yet.</b>
        <p>This project ships the determination table empty — its values are normative content
        from the standard, so they come from your own licensed copy. ${r.filled} of ${r.total}
        combinations are filled in <code>${esc(r.file)}</code>.</p>
        <p>Your row keeps its <code>asil</code> cell empty, exactly as the chain does: it marks
        the hazard <code>[PENDING]</code> rather than guessing, and so does this tool.</p></div>`;
    }
    return `<div class="asil-answer">
      <span class="asil-badge" style="color:var(--asil-${esc(String(r.asil).toLowerCase())});
            border-color:var(--asil-${esc(String(r.asil).toLowerCase())})">${esc(r.asil)}</span>
      <span class="asil-why">${esc(r.why)}</span></div>`;
  };

  const rowHtml = () => {
    const row = session.row();
    const missing = COLUMNS.filter(c => c !== "asil" && !row[c]);
    return `<pre class="rowout">${esc(COLUMNS.join(","))}\n${esc(session.csv())}</pre>
      <div class="pager">
        <button id="copy">Copy this row</button>
        <span class="dots" id="copied">${missing.length
          ? `${missing.length} cell(s) still empty: ${esc(missing.join(", "))}`
          : "paste it under the header in input/hazards.csv"}</span>
      </div>
      ${session.value("safety_goal") ? `<p class="hint">Its safety goal —
        ${esc(session.value("safety_goal"))} — belongs in
        <code>input/safety-goals.csv</code>, keyed by <code>${esc(row.id)}</code>.</p>` : ""}`;
  };

  const inputHtml = (step) => {
    const key = step.key, value = session.value(key);
    if (step.kind === "choose" || step.kind === "guideword") {
      const options = step.kind === "guideword" ? GUIDEWORDS : session.options(key);
      const wrap = step.kind === "guideword" ? "words" : "";
      return `<div class="${wrap}">${options.map(o =>
        `<button class="opt ${value === o ? "picked" : ""}" data-o="${esc(o)}">${esc(o)}</button>`
        ).join("")}</div>`;
    }
    if (step.kind === "text") {
      return `<textarea class="write" id="write" rows="3"
                placeholder="in your own words">${esc(value || "")}</textarea>`;
    }
    if (step.kind === "rating") {
      const r = value || {};
      return `<div class="tool">${Object.entries(SCALES).map(([field, classes]) => `
        <div class="scale">
          <label for="sc-${field}">${esc(field)}</label>
          <select id="sc-${field}" data-f="${field}">
            <option value="" ${r[field] ? "" : "selected"}>—</option>
            ${classes.map(cl =>
              `<option ${r[field] === cl ? "selected" : ""}>${cl}</option>`).join("")}
          </select></div>`).join("")}</div>`;
    }
    if (step.kind === "asil") return asilHtml();
    if (step.kind === "row") return rowHtml();
    return "";
  };

  const draw = () => {
    const step = session.step();
    const n = session.at;
    if (step.kind === "asil") ensureAsil();
    // A worked case is meant to be read through, so its answer starts in the box — still
    // editable, because arguing with a worked answer is most of what the reading is for.
    if (session.scenario.reveal === "always" && session.value(step.key) === undefined
        && session.modelAnswer(step.key) !== null) {
      session.set(step.key, session.modelAnswer(step.key));
    }
    const canCheck = session.scenario.reveal === "submit"
                     && session.modelAnswer(step.key) !== null && !checked.has(step.key);
    host.innerHTML = head + `
      <div class="pager">
        <button id="pick">← other cases</button>
        <span class="dots">${esc(session.scenario.title)} ·
          ${esc(MODES[session.scenario.reveal] || session.scenario.reveal)}</span>
      </div>
      <div class="card item"><span class="kind">the item</span>
        <p>${esc(session.scenario.item)}</p></div>
      <div class="card">
        <span class="kind">step ${n + 1} of ${STEPS.length} · ${esc(step.title)}</span>
        <p>${esc(step.ask.replace(/\s+/g, " "))}</p>
        <div class="answer">${inputHtml(step)}</div>
        ${step.key === "hazardous_event" || step.kind === "rating" ? pairHtml() : ""}
        ${answerHtml(step.key)}
      </div>
      <div class="pager">
        <button id="back" ${n === 0 ? "disabled" : ""}>Back</button>
        <button id="next" ${n === STEPS.length - 1 || !session.canAdvance() ? "disabled" : ""}>
          Next</button>
        ${canCheck ? `<button id="check">Check my answer</button>` : ""}
        <span class="dots">${esc(step.title)}</span>
      </div>`;
    wire(step);
  };

  const wire = (step) => {
    host.querySelector("#pick").onclick = () => start();
    host.querySelector("#back").onclick = () => { session.prev(); draw(); };
    host.querySelector("#next").onclick = () => { session.next(); draw(); };
    const check = host.querySelector("#check");
    if (check) check.onclick = () => { checked.add(step.key); draw(); };
    host.querySelectorAll(".opt").forEach(el => {
      el.onclick = () => { session.set(step.key, el.dataset.o); draw(); };
    });
    const write = host.querySelector("#write");
    if (write) {
      // No redraw on every keystroke: it would take the caret with it.
      write.oninput = () => {
        session.set(step.key, write.value);
        host.querySelector("#next").disabled = !session.canAdvance();
      };
    }
    host.querySelectorAll("select[data-f]").forEach(el => {
      el.onchange = () => {
        session.set("rating", {...(session.value("rating") || {}), [el.dataset.f]: el.value});
        draw();
      };
    });
    const copy = host.querySelector("#copy");
    if (copy) {
      copy.onclick = () => {
        const said = m => { host.querySelector("#copied").textContent = m; };
        globalThis.navigator?.clipboard?.writeText(session.csv())
          .then(() => said("copied — paste it under the header in input/hazards.csv"),
                () => said("copy is blocked here — select the row above instead"))
          ?? said("copy is blocked here — select the row above instead");
      };
    }
  };

  const ensureAsil = () => {
    const r = session.value("rating") || {};
    const want = `${r.severity}-${r.exposure}-${r.controllability}`;
    if (session.asil()?.key === want || pending === want) return;
    pending = want;
    session.lookupAsil()
      .then(() => { pending = null; draw(); })
      .catch(err => { pending = null; banner(`the rating could not be looked up — ${err.message}`); });
  };

  const start = () => {
    session = null;
    host.innerHTML = head + `<p class="hint">loading the cases…</p>`;
    api("/api/learn/scenarios/hara").then(r => {
      if (r.errors?.length) banner(`${r.errors.length} scenario problem(s): ${r.errors[0]}`);
      if (!r.scenarios.length) {
        host.innerHTML = head + `<p class="hint">No cases are installed. They are content:
          add one to <code>scenarios/hara.json</code> in your content directory.</p>`;
        return;
      }
      pickScenario(r.scenarios);
    }).catch(err => {
      host.innerHTML = head + `<p class="hint">the cases could not be loaded</p>`;
      banner(`the HARA builder could not load its cases — ${err.message}`);
    });
  };

  start();
}
