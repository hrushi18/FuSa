// The nav IS the V-model: groups in lifecycle order, so a practitioner needs no legend.
import { state } from "./app.js";
import { esc } from "./esc.js";

export const STATUS_ICON = {
  not_started: "○", in_progress: "◐", passed: "✓", needs_review: "⚑",
};

const statusOf = id => state.progress[id]?.status || "not_started";
const modulesOf = gid => state.modules.filter(m => m.group === gid);

// Fixed, not content-driven: these are code, not course material, so they don't come from
// the server's module list and carry no completion ring. Exported so the router can name a
// tool by its real title rather than keeping a second, driftable copy of this list.
export const TOOLS = [
  {id: "asil",  title: "ASIL Calculator"},
  {id: "hara",  title: "HARA Builder"},
  {id: "trace", title: "Traceability Lab"},
];

export function drawNav(onSelect, filter = "") {
  const q = filter.trim().toLowerCase();
  const nav = document.getElementById("learn-nav");
  const toolsHtml = `<div class="grp open" data-g="tools">
      <div class="g-top" tabindex="0" role="button" aria-expanded="true">
        <span class="g-caret">▸</span>
        <span class="g-title">Tools</span>
        <span class="ring">—</span>
      </div>
      <div class="g-mods">${TOOLS.map(t => `
        <div class="mod ${state.current === `tool:${t.id}` ? "on" : ""}" data-t="${esc(t.id)}"
             tabindex="0" role="button">
          <span class="ico">▹</span>
          <span>${esc(t.title)}</span></div>`).join("")}
      </div></div>`;
  nav.innerHTML = toolsHtml + state.groups.map(g => {
    const mods = modulesOf(g.id).filter(m => !q || m.title.toLowerCase().includes(q));
    if (q && !mods.length) return "";
    const done = modulesOf(g.id).filter(m => statusOf(m.id) === "passed").length;
    const total = modulesOf(g.id).length;
    const open = q || state.openGroups.has(g.id);
    return `<div class="grp ${open ? "open" : ""}" data-g="${esc(g.id)}">
      <div class="g-top" tabindex="0" role="button" aria-expanded="${open}">
        <span class="g-caret">▸</span>
        <span class="g-title">${esc(g.order)} · ${esc(g.title)}</span>
        <span class="ring">${total ? `${done}/${total}` : "—"}</span>
      </div>
      <div class="g-mods">${mods.map(m => {
        const st = statusOf(m.id);
        return `<div class="mod ${state.current === m.id ? "on" : ""}" data-m="${esc(m.id)}"
                     tabindex="0" role="button" title="${esc(st.replace("_", " "))}">
          <span class="ico st-${st}">${STATUS_ICON[st]}</span>
          <span>${esc(m.title)}</span></div>`;
      }).join("") || `<div class="mod" style="color:var(--dim);cursor:default">no modules yet</div>`}
      </div></div>`;
  }).join("");

  nav.querySelectorAll(".g-top").forEach(el => {
    const gid = el.parentElement.dataset.g;
    const toggle = () => {
      state.openGroups.has(gid) ? state.openGroups.delete(gid) : state.openGroups.add(gid);
      drawNav(onSelect, filter);
    };
    el.onclick = toggle;
    el.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
  });
  nav.querySelectorAll(".mod[data-m]").forEach(el => {
    const go = () => onSelect(el.dataset.m);
    el.onclick = go;
    el.onkeydown = e => { if (e.key === "Enter") go(); };
  });
  nav.querySelectorAll(".mod[data-t]").forEach(el => {
    const go = () => { location.hash = "#/tool/" + el.dataset.t; };
    el.onclick = go;
    el.onkeydown = e => { if (e.key === "Enter") go(); };
  });
}
