// The one seam between the UI and progress storage (spec §6). Nothing else posts progress, so
// swapping the file-backed store for another one is a change here and nowhere else — and a save
// that fails is reported once, in the banner, instead of being dropped twice in silence.
import { api, banner, setProgress } from "./app.js";

export function saveProgress(moduleId, update) {
  return api("/api/learn/progress", {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({module_id: moduleId, ...update}),
  }).then(rec => {
    setProgress(moduleId, rec);
    return rec;
  }).catch(err => {
    banner(`progress not saved — ${err.message}`);
    return null;
  });
}
