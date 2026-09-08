// Three selects and one lookup. The answer is not computed here and must never be: the
// determination table is normative content this project does not ship, so the server reads the
// engineer's own transcription. An unfilled cell says so — a guess would be wrong all the way
// down the chain with nothing downstream able to notice.
import { banner } from "../app.js";
import { esc } from "../esc.js";

const SCALES = {
  s: {label: "Severity", classes: ["S0", "S1", "S2", "S3"],
      hint: "how badly the harm hurts, if it happens"},
  e: {label: "Exposure", classes: ["E0", "E1", "E2", "E3", "E4"],
      hint: "how much of the time the vehicle is in that situation"},
  c: {label: "Controllability", classes: ["C0", "C1", "C2", "C3"],
      hint: "whether a driver can act in time to avoid it"},
};
const ALLOWED = ["QM", "A", "B", "C", "D"];
const ASIL_VAR = a => `var(--asil-${String(a).toLowerCase()})`;

export function renderAsil(host) {
  const pick = {s: "S3", e: "E4", c: "C3"};

  const draw = (result) => {
    host.innerHTML = `
      <h2 style="font-size:16px;margin:0 0 4px">ASIL Calculator</h2>
      <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
        Reads the S×E×C table in your project. It is not a formula.</p>
      <div class="tool">
        ${Object.entries(SCALES).map(([k, sc]) => `
          <div class="scale">
            <label for="sc-${k}">${esc(sc.label)}</label>
            <select id="sc-${k}" data-k="${k}">${sc.classes.map(cl =>
              `<option ${pick[k] === cl ? "selected" : ""}>${cl}</option>`).join("")}</select>
            <span class="hint">${esc(sc.hint)}</span>
          </div>`).join("")}
      </div>
      <div class="verdict" id="asil-out">${result ? verdictHtml(result) : "…"}</div>`;
    host.querySelectorAll("select[data-k]").forEach(el => {
      el.onchange = () => { pick[el.dataset.k] = el.value; go(); };
    });
  };

  const verdictHtml = r => {
    if (r.asil === null) {
      return `<div class="unfilled">
        <b>${esc(r.key)} is not transcribed yet.</b>
        <p>This project ships the determination table empty — its values are normative content
        from the standard, so they come from your own licensed copy. ${r.filled} of ${r.total}
        combinations are filled in <code>${esc(r.file)}</code>.</p>
        <p>Until this cell is filled the chain leaves the hazard
        <code>[PENDING]</code> rather than guessing, and so does this calculator.</p>
        <div class="fill-now">
          <label for="asil-fill">Transcribe ${esc(r.key)} from your copy:</label>
          <select id="asil-fill">${ALLOWED.map(a => `<option>${a}</option>`).join("")}</select>
          <button id="asil-save">Save to ${esc(r.file)}</button>
        </div></div>`;
    }
    return `<div class="asil-answer">
      <span class="asil-badge" style="color:${ASIL_VAR(r.asil)};border-color:${ASIL_VAR(r.asil)}">
        ${esc(r.asil)}</span>
      <span class="asil-why">${esc(r.why)}</span></div>
      <p class="hint">Same lookup <code>sys-hara</code> performs for a hazard rated
      ${esc(r.key.replace(/-/g, " / "))}.</p>`;
  };

  const go = () => {
    const q = new URLSearchParams(pick).toString();
    fetch(`/api/learn/asil?${q}`)
      .then(r => r.ok ? r.json() : r.json().then(b => Promise.reject(new Error(b.detail))))
      .then(r => { host.querySelector("#asil-out").innerHTML = verdictHtml(r); bindFill(r); })
      .catch(err => banner(`the calculator could not answer — ${err.message}`));
  };

  // Writing the cell is only half of it: the answer shown afterwards is re-read from the table,
  // never echoed from the input, so what the learner sees is what the chain will see.
  const bindFill = r => {
    if (r.asil !== null) return;
    const save = host.querySelector("#asil-save");
    if (!save) return;
    save.onclick = () => {
      const value = host.querySelector("#asil-fill").value;
      return fetch("/api/asil-table", {
        method: "POST", headers: {"content-type": "application/json"},
        body: JSON.stringify({values: {[r.key]: value}}),
      }).then(res => res.ok ? res.json()
                            : res.json().then(b => Promise.reject(new Error(b.detail))))
        .then(go)
        .catch(err => banner(`${r.key} was not saved — ${err.message}`));
    };
  };

  draw(null);
  go();
}
