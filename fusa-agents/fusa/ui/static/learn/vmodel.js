// The deck spent 36 slides revealing this diagram one box at a time. It is one component:
// pass the phase a module sits in, and everything up to there is lit.
export const PHASES = ["item", "hara", "fsc", "tsc", "sw", "hw",
                       "integration", "validation", "assessment"];

// Laid out as the V it is: the left arm descends, hardware and software sit at the base,
// the right arm rises. The shape is the teaching, so it is not a list in a box.
const BOXES = [
  {id: "item",        label: "Item definition",       x: 8,   y: 10},
  {id: "hara",        label: "Hazard analysis",       x: 44,  y: 48},
  {id: "fsc",         label: "Functional safety concept", x: 80,  y: 86},
  {id: "tsc",         label: "Technical safety concept",  x: 116, y: 124},
  {id: "hw",          label: "Hardware safety",       x: 152, y: 162},
  {id: "sw",          label: "Software safety",       x: 152, y: 196},
  {id: "integration", label: "Integration & testing", x: 296, y: 124},
  {id: "validation",  label: "Validation",            x: 332, y: 86},
  {id: "assessment",  label: "Assessment",            x: 368, y: 48},
];

const W = 150, H = 26;
const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function vmodelSvg(reveal = "all", alt = "") {
  const at = PHASES.indexOf(reveal);
  const lit = new Set(reveal === "all" || at === -1 ? PHASES : PHASES.slice(0, at + 1));
  const boxes = BOXES.map(b => {
    const on = lit.has(b.id);
    return `<g opacity="${on ? 1 : 0.3}">
      <rect x="${b.x}" y="${b.y}" width="${W}" height="${H}" rx="5"
            fill="${on ? "var(--panel2)" : "transparent"}"
            stroke="${on ? "var(--accent)" : "var(--line)"}" stroke-width="1"/>
      <text x="${b.x + W / 2}" y="${b.y + 17}" text-anchor="middle" font-size="9.5"
            font-family="ui-monospace, Menlo, monospace"
            fill="${on ? "var(--text)" : "var(--dim)"}">${esc(b.label)}</text></g>`;
  }).join("");
  return `<figure style="margin:0">
    <svg viewBox="0 0 526 236" width="100%" role="img" aria-label="${esc(alt)}"
         style="max-width:100%">${boxes}</svg>
    <figcaption style="color:var(--dim);font-size:11px;margin-top:8px;line-height:1.6">
      ${esc(alt)}</figcaption>
  </figure>`;
}
