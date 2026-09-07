// Shared HTML-escaping. Every caller splices output into both text nodes and quoted
// attributes (e.g. aria-label="${esc(alt)}"), so quotes must escape too, not just & < >.
export const esc = s => String(s ?? "")
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;")
  .replace(/'/g, "&#39;");
