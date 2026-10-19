// rubrica console: one page, no framework, no build step.
//
// Every piece of run data is inserted with textContent, never innerHTML: the
// strings come from model-written artifacts and logs, and this page holds the
// token that can start a dispatch.
"use strict";

const TOKEN = document.querySelector('meta[name="rubrica-token"]').content;
const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, body, signal) {
  const opts = body === undefined
    ? { headers: {} }
    : { method: "POST", headers: { "Content-Type": "application/json", "X-Rubrica-Token": TOKEN },
        body: JSON.stringify(body) };
  const res = await fetch(path, { ...opts, cache: "no-store", signal });
  let data = null;
  try { data = await res.json(); } catch (_) { /* not JSON */ }
  if (res.status === 403 && body !== undefined && data && /token/.test(data.error || "")) {
    // The console was restarted and minted a new token; this tab holds the old
    // one. Reloading fetches the page that carries the new token. Nothing was run.
    toast("The console was restarted. Reloading this page — nothing was started.", true);
    setTimeout(() => location.reload(), 1500);
    throw new Error("the console was restarted; reloading");
  }
  if (!res.ok) throw new Error((data && data.error) || `${res.status} ${res.statusText}`);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, err ? 8000 : 3500);
}

function size(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}
function money(x) { return x ? `$${Number(x).toFixed(2)}` : "$0.00"; }
function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${(s / 3600).toFixed(1)}h ago`;
}
function took(job) {
  if (!job.started) return "";
  const end = job.ended || Date.now() / 1000;
  const s = Math.round(end - job.started);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}
function put(el, ...children) { el.replaceChildren(...children.flat().filter((c) => c !== null && c !== undefined && c !== false)); }
function pill(status, extra = "") { return h("span", { class: `pill s-${status} ${extra}` }, status); }

// -- settings (per browser) --------------------------------------------------

const settings = {
  load(defaults) {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem("rubrica-console") || "{}"); } catch (_) {}
    return { model: defaults.model, effort: defaults.effort, budget: "", ...saved };
  },
  save(s) { try { localStorage.setItem("rubrica-console", JSON.stringify(s)); } catch (_) {} },
};

// -- modal -------------------------------------------------------------------

function openModal(title, body, onClose) {
  $("#modal-title").textContent = title;
  const box = $("#modal-body");
  put(box, body);
  $("#modal").hidden = false;
  const close = () => { $("#modal").hidden = true; put(box, ); if (onClose) onClose(); };
  $("#modal-close").onclick = close;
  $("#modal").onclick = (e) => { if (e.target.id === "modal") close(); };
  return close;
}

function confirmDialog(title, lines, okLabel = "Start") {
  return new Promise((resolve) => {
    let answered = false;
    const close = openModal(title, h("div", {},
      ...lines.map((l) => (l instanceof Node ? l : h("p", {}, l))),
      h("div", { class: "row" },
        h("button", { class: "primary", onclick: () => { answered = true; close(); resolve(true); } }, okLabel),
        h("button", { onclick: () => { answered = true; close(); resolve(false); } }, "Cancel"))),
      () => { if (!answered) resolve(false); });
  });
}

// -- file picker -------------------------------------------------------------

function pickOne({ mode, start }) {
  // mode "dir": choose one folder; mode "files": choose one or more files; "file": one file.
  return new Promise((resolve) => {
    let chosen = new Set();
    let current = start;
    let done = false;
    const list = h("div", { class: "picker-list" });
    const where = h("div", { class: "mono muted" });
    const footer = h("div", { class: "row" });
    const body = h("div", {}, where, list, h("p", { class: "muted" },
      mode === "dir" ? "Open a folder, then choose it." : "Click files to select them."), footer);
    const close = openModal(mode === "dir" ? "Choose a folder" : "Choose files", body,
      () => { if (!done) resolve(null); });
    const finish = (value) => { done = true; close(); resolve(value); };
    async function load(path) {
      try {
        const data = await api(`/api/fs?path=${encodeURIComponent(path || "")}`);
        current = data.path;
        where.textContent = data.path;
        put(list, );
        if (data.parent) list.append(h("div", { onclick: () => load(data.parent) }, "⬆", ".."));
        for (const e of data.entries) {
          if (!e.dir && mode === "dir") continue;
          const row = h("div", { class: chosen.has(e.path) ? "sel" : "" }, e.dir ? "📁" : "📄", e.name,
            e.dir ? "" : h("span", { class: "muted" }, ` ${Math.ceil(e.size / 1024)} KB`));
          row.onclick = () => {
            if (e.dir) return load(e.path);
            if (mode === "file") return finish([e.path]);
            if (chosen.has(e.path)) chosen.delete(e.path); else chosen.add(e.path);
            row.classList.toggle("sel");
            renderFooter();
          };
          list.append(row);
        }
        renderFooter();
      } catch (err) { toast(err.message, true); }
    }
    function renderFooter() {
      put(footer, 
        mode === "dir"
          ? h("button", { class: "primary", onclick: () => finish([current]) }, "Choose this folder")
          : mode === "files"
            ? h("button", { class: "primary", disabled: chosen.size === 0,
                onclick: () => finish([...chosen]) }, `Add ${chosen.size} file(s)`)
            : null);
    }
    load(start);
  });
}


// -- selection picker ----------------------------------------------------------
//
// Checkboxes over a folder tree. A decision is kept per path: `inc` (included)
// or `exc` (excluded). A path's state is the decision of its nearest decided
// ancestor-or-self; undecided means out. So checking a folder takes everything
// under it, and unchecking something inside it carves that out. The result is
// { include: [paths], exclude: [paths] }, which the caller turns into intake's
// files or survey's roots and --exclude globs.

const sep = "/";
const parentOf = (p) => p.slice(0, p.lastIndexOf(sep)) || sep;
const isUnder = (p, dir) => p !== dir && p.startsWith(dir.endsWith(sep) ? dir : dir + sep);

function pickSelection({ mode, start, initial }) {
  // mode: "survey" (folders are roots; files only as exclusions) or "intake" (anything).
  return new Promise((resolve) => {
    const decided = new Map(); // path -> { state: "inc"|"exc", dir: bool }
    for (const p of (initial && initial.include) || []) decided.set(p, { state: "inc", dir: !!(initial.dirs || {})[p] });
    for (const p of (initial && initial.exclude) || []) decided.set(p, { state: "exc", dir: !!(initial.dirs || {})[p] });
    let listing = null;
    let filter = "";
    let done = false;

    const pathBox = h("input", { class: "mono", style: "flex:1", spellcheck: "false" });
    const filterBox = h("input", { placeholder: "filter this folder", size: 18 });
    const crumbs = h("div", { class: "crumbs mono" });
    const list = h("div", { class: "picker-list" });
    const summary = h("div", { class: "pick-summary" });
    const count = h("div", { class: "muted" });
    const useBtn = h("button", { class: "primary" }, "Use this selection");
    const help = mode === "survey"
      ? "Check folders to read as corpus roots. Inside a checked folder, uncheck anything to leave it out (it becomes an --exclude pattern)."
      : "Check files or folders. A checked folder brings every file inside it; uncheck anything inside to leave it out.";
    const body = h("div", {},
      h("div", { class: "row" }, pathBox, h("button", { onclick: () => load(pathBox.value.trim()) }, "Go")),
      crumbs,
      h("div", { class: "row", style: "margin:6px 0" }, filterBox,
        h("button", { onclick: () => bulk(true) }, "Select all here"),
        h("button", { onclick: () => bulk(false) }, "Clear here"),
        h("div", { class: "spacer" }),
        h("button", { class: "ghost", onclick: () => { decided.clear(); redraw(); } }, "Clear all")),
      list,
      h("p", { class: "muted" }, help),
      h("h3", {}, "Selection"), summary, count,
      h("div", { class: "row", style: "margin-top:10px" }, useBtn));
    const close = openModal(mode === "survey" ? "Choose corpus folders" : "Choose input files and folders", body,
      () => { if (countAbort) countAbort.abort(); clearTimeout(countTimer); if (!done) resolve(null); });
    useBtn.onclick = () => {
      done = true;
      const include = [], exclude = [], dirs = {};
      for (const [p, d] of decided) { (d.state === "inc" ? include : exclude).push(p); if (d.dir) dirs[p] = true; }
      close();
      resolve({ include: include.sort(), exclude: exclude.sort(), dirs });
    };
    filterBox.oninput = () => { filter = filterBox.value.toLowerCase(); drawList(); };

    function nearest(path) {
      // The decision that governs `path`: its own, else its nearest decided ancestor's.
      let best = null;
      for (const [p, d] of decided) {
        if ((p === path || isUnder(path, p)) && (!best || p.length > best[0].length)) best = [p, d];
      }
      return best;
    }
    const stateOf = (path) => { const n = nearest(path); return n ? n[1].state : "out"; };
    const mixed = (dir) => {
      const own = stateOf(dir);
      for (const [p, d] of decided) if (isUnder(p, dir) && (d.state === "inc") !== (own === "inc")) return true;
      return false;
    };
    function blocked(entry) {
      // What survey cannot express; say why rather than silently doing something else.
      if (mode !== "survey") return null;
      const ancestors = [...decided].filter(([p]) => isUnder(entry.path, p));
      if (ancestors.some(([, d]) => d.state === "exc") && stateOf(entry.path) !== "inc") {
        return "inside a folder you left out: survey cannot take something back in";
      }
      if (!entry.dir && !ancestors.some(([, d]) => d.state === "inc")) {
        return "survey reads folders: check the folder this file is in, or hand-pick files instead";
      }
      return null;
    }
    function toggle(entry) {
      const path = entry.path;
      const current = stateOf(path);
      // Clear any decisions below this path: the new decision covers them.
      for (const p of [...decided.keys()]) if (isUnder(p, path)) decided.delete(p);
      const own = decided.get(path);
      if (current === "inc") {
        if (own && own.state === "inc") decided.delete(path); else decided.set(path, { state: "exc", dir: entry.dir });
      } else if (own && own.state === "exc") {
        decided.delete(path);
        if (stateOf(path) !== "inc") decided.set(path, { state: "inc", dir: entry.dir });
      } else {
        decided.set(path, { state: "inc", dir: entry.dir });
      }
      // Tidy: an exclusion with nothing included above it means nothing.
      for (const [p, d] of [...decided]) if (d.state === "exc" && stateOf(parentOf(p)) !== "inc" && ![...decided].some(([q, e]) => e.state === "inc" && isUnder(p, q))) decided.delete(p);
      redraw();
    }
    function bulk(on) {
      if (!listing) return;
      for (const e of visible()) {
        if (blocked(e) && on) continue;
        const inNow = stateOf(e.path) === "inc";
        if (on !== inNow) toggle(e);
      }
    }
    const visible = () => listing.entries.filter((e) => !filter || e.name.toLowerCase().includes(filter));

    function drawList() {
      if (!listing) return;
      const rows = [];
      if (listing.parent) rows.push(h("div", { class: "pick-row", onclick: () => load(listing.parent) }, h("span", { class: "pick-box" }), "⬆", h("span", {}, "..")));
      for (const e of visible()) {
        const st = stateOf(e.path);
        const why = blocked(e);
        const box = h("input", { type: "checkbox", title: why || "" });
        box.checked = st === "inc";
        box.indeterminate = e.dir && mixed(e.path);
        box.disabled = !!why && st !== "inc";
        box.onclick = (ev) => { ev.stopPropagation(); toggle(e); };
        const name = h("span", { class: st === "exc" ? "struck" : "" }, e.name);
        const row = h("div", { class: `pick-row ${st === "inc" ? "sel" : ""}`, title: why || "" },
          h("span", { class: "pick-box" }, box), e.dir ? "📁" : "📄", name,
          e.dir ? h("span", { class: "muted" }, "›") : h("span", { class: "muted" }, ` ${Math.max(1, Math.ceil(e.size / 1024))} KB`));
        row.onclick = () => (e.dir ? load(e.path) : (!box.disabled && toggle(e)));
        rows.push(row);
      }
      if (!visible().length) rows.push(h("div", { class: "muted pad" }, filter ? "Nothing matches the filter." : "This folder is empty."));
      put(list, rows);
    }
    let countTimer = null;
    let countAbort = null;
    function redraw() {
      drawList();
      const inc = [...decided].filter(([, d]) => d.state === "inc");
      const exc = [...decided].filter(([, d]) => d.state === "exc");
      const chip = ([p, d]) => h("span", { class: `chip ${d.state === "exc" ? "chip-exc" : ""}` }, (d.state === "exc" ? "− " : "+ ") + p + (d.dir ? "/" : ""),
        h("button", { title: "undo", onclick: () => { decided.delete(p); redraw(); } }, "✕"));
      put(summary, inc.length ? h("div", { class: "chips" }, ...inc.map(chip), ...exc.map(chip)) : h("p", { class: "muted" }, "Nothing selected yet."));
      useBtn.disabled = !inc.length;
      clearTimeout(countTimer);
      count.textContent = inc.length ? "Counting…" : "";
      if (!inc.length) return;
      countTimer = setTimeout(async () => {
        // A newer selection cancels the count still running for the older one,
        // rather than leaving the server walking folders nobody is waiting for.
        if (countAbort) countAbort.abort();
        countAbort = new AbortController();
        try {
          const r = await api("/api/fs/expand", { include: inc.map(([p]) => p), exclude: exc.map(([p]) => p) }, countAbort.signal);
          const mb = size(r.bytes);
          const n = r.partial ? `at least ${r.total} file(s), ${mb} (stopped counting: this is a large selection)` : `${r.total} file(s), ${mb}`;
          count.textContent = mode === "survey"
            ? `${n} under the chosen folders, before survey's own filters (VCS, vendored, lock and gitignored files).`
            : `${n}${r.truncated || r.partial ? " — too many to hand-pick; survey a corpus instead" : ""}. Each file is one extract dispatch.`;
        } catch (err) { if (err.name !== "AbortError") count.textContent = err.message; }
      }, 250);
    }
    async function load(path) {
      try {
        listing = await api(`/api/fs?path=${encodeURIComponent(path || "")}`);
        pathBox.value = listing.path;
        // From the picker's root down: anything above it would only be refused.
        const rootParts = STATE.root.split(sep).filter(Boolean);
        const parts = listing.path.split(sep).filter(Boolean);
        const first = Math.max(0, rootParts.length - 1);
        put(crumbs, ...parts.slice(first).map((part, j) => {
          const i = first + j;
          const target = sep + parts.slice(0, i + 1).join(sep);
          return [h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); load(target); } }, part), i < parts.length - 1 ? " / " : ""];
        }));
        filter = ""; filterBox.value = "";
        redraw();
      } catch (err) { toast(err.message, true); }
    }
    load(start);
  });
}

// What a survey selection means for `rubrica survey`: each included folder is a
// --corpus root, and each excluded path a glob relative to its root. survey
// matches a glob against each file's path relative to *every* root, and a glob
// with no "/" also against the bare file name, so both caveats are returned for
// the form to show rather than hidden.
function surveyArgs(sel) {
  const roots = sel.include.filter((p) => sel.dirs[p]);
  const globs = [];
  const warnings = [];
  for (const p of sel.exclude) {
    const root = roots.filter((r) => isUnder(p, r)).sort((a, b) => b.length - a.length)[0];
    if (!root) continue;
    const rel = p.slice(root.length + 1);
    const glob = sel.dirs[p] ? `${rel}/*` : rel;
    globs.push(glob);
    if (!glob.includes("/")) warnings.push(`“${glob}” has no folder in it, so survey also leaves out every file named ${glob} in any subfolder.`);
  }
  if (roots.length > 1 && globs.length) warnings.push("Exclusions apply under every corpus folder, not only the one you unchecked them in.");
  return { roots, globs, warnings };
}

// -- routing -----------------------------------------------------------------

let STATE = null;
let poller = null;

function route() {
  clearTimeout(poller);
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (parts[0] === "run" && parts[1]) return runPage(parts[1], parts.slice(2).join("/"));
  if (parts[0] === "new") return newRunPage(parts[1] || null);
  if (parts[0] === "settings") return settingsPage();
  return homePage();
}
window.addEventListener("hashchange", route);

async function loadState() {
  STATE = await api("/api/state");
  put($("#top-status"), h("a", {
    class: `access ${STATE.prompt_ready ? "" : "off"}`, href: "#/settings",
    title: STATE.prompt_ready ? `Model access is set up · up to ${STATE.max_parallel} dispatches at once` : STATE.prompt_reason,
  }, h("i"), STATE.prompt_ready ? "Model access ready" : "Model access not set up"));
  return STATE;
}

function navOn(which) {
  for (const id of ["nav-runs", "nav-settings"]) $(`#${id}`).classList.toggle("on", id === which);
}

// -- home --------------------------------------------------------------------

async function homePage() {
  put($("#top-run"));
  navOn("nav-runs");
  const app = $("#app");
  try { await loadState(); } catch (err) { put(app, h("div", { class: "banner err" }, err.message)); return; }
  const card = (r) => {
    if (r.error) return h("div", { class: "card" }, h("div", { class: "title" }, r.name), h("div", { class: "s-failed" }, r.error));
    const status = r.running ? h("span", { class: "pill s-running" }, h("span", { class: "spinner" }), "running")
      : r.failed ? h("span", { class: "pill s-failed" }, "needs attention")
      : r.next_kind === "gate" ? h("span", { class: "pill s-gate" }, "waiting for you")
      : r.next === "complete" ? h("span", { class: "pill s-done" }, "complete") : h("span", { class: "pill s-ready" }, "ready");
    return h("a", { class: "card", href: `#/run/${encodeURIComponent(r.name)}` },
      h("div", { class: "row" }, h("div", { style: "min-width:0;flex:1" },
        h("div", { class: "title truncate" }, r.target || r.name),
        h("div", { class: "id truncate" }, r.target ? r.name : "")), status),
      h("div", { class: "segbar", title: r.phases.map((p) => `${p.phase}: ${p.done}/${p.total}`).join("\n") },
        ...r.phases.map((p) => h("span", {}, h("i", { style: `width:${(100 * p.done / Math.max(1, p.total)).toFixed(0)}%` })))),
      h("div", { class: "next truncate" }, r.running ? h("span", {}, "Running ", h("b", {}, r.running))
        : r.next === "complete" ? "Every step is done" : h("span", {}, "Next: ", h("b", {}, r.next))),
      h("div", { class: "foot" },
        r.mode ? h("span", { class: "chip-k" }, r.mode === "survey" ? "survey" : "hand-picked") : null,
        r.interface ? h("span", { class: "chip-k", title: r.interface }, r.interface) : null,
        h("span", { class: "spacer" }), h("span", {}, `${r.done}/${r.total} steps`), h("span", {}, "·"), h("span", {}, money(r.cost))));
  };
  put(app,
    !STATE.prompt_ready ? h("div", { class: "banner warn" }, h("strong", {}, "Model stages cannot run yet."),
      h("span", {}, STATE.prompt_reason + ". Code steps and gates still work."), h("span", { class: "spacer" }),
      h("a", { class: "button small", href: "#/settings" }, "Open Settings")) : null,
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Runs"), h("div", { class: "sub mono" }, STATE.runs_dir)),
      h("div", { class: "spacer" }), h("a", { class: "button primary", href: "#/new" }, "+ New run")),
    STATE.runs.length
      ? h("div", { class: "cards" }, ...STATE.runs.map(card),
          h("a", { class: "card new", href: "#/new" }, h("span", { class: "plus" }, "+"), "New run"))
      : h("div", { class: "panel empty" }, h("h2", {}, "No runs yet"),
          h("p", {}, "Pick a corpus or a few input files to start one. Creating a run calls no model."),
          h("a", { class: "button primary", href: "#/new" }, "+ New run")));
  poller = setTimeout(homePage, 5000);
}

// -- new run -----------------------------------------------------------------

const DRAFT_KEY = "rubrica-console-new-run";

async function newRunPage(fromRun) {
  put($("#top-run"));
  navOn("nav-runs");
  await loadState();
  // Where the form starts: a run's own record when asked to repeat one, else the
  // draft this browser kept, so leaving the page never loses a selection.
  let initial = null;
  if (fromRun) {
    try { initial = specToForm(await api(`/api/runs/${encodeURIComponent(fromRun)}/spec`)); }
    catch (err) { toast(err.message, true); }
  } else {
    try { initial = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch (_) { initial = null; }
  }
  const app = $("#app");
  const f = {};
  const field = (key, label, input, help) => h("div", {}, h("label", { for: key }, label), input, help ? h("div", { class: "muted" }, help) : null);
  f.mode = h("select", { id: "mode" }, h("option", { value: "survey" }, "Survey a corpus (folders → triage → gate 0)"),
    h("option", { value: "intake" }, "Hand-pick input files (skips triage and gate 0)"));
  f.target_name = h("input", { id: "target_name", placeholder: "e.g. autotrade" });
  f.target_interface = h("input", { id: "target_interface", list: "ifaces", placeholder: "mcp, http, http-sse, a2a…" });
  f.objective = h("select", { id: "objective" }, h("option", { value: "breadth" }, "breadth"), h("option", { value: "depth" }, "depth"));
  f.objective_note = h("input", { id: "objective_note" });
  f.scope_note = h("input", { id: "scope_note" });
  f.exclude = h("textarea", { id: "exclude", placeholder: "one glob per line, e.g. **/node_modules/**" });
  f.max_rounds = h("input", { id: "max_rounds", type: "number", min: 1, placeholder: "default" });
  f.max_scenarios = h("input", { id: "max_scenarios", type: "number", min: 1, placeholder: "default" });
  // One selection per mode, so switching modes does not lose either.
  const sel = { survey: null, intake: null, ...((initial && initial.sel) || {}) };
  const FIELDS = ["mode", "target_name", "target_interface", "objective", "objective_note", "scope_note", "exclude", "max_rounds", "max_scenarios"];
  for (const k of FIELDS) if (initial && initial.fields && initial.fields[k] != null) f[k].value = initial.fields[k];
  const saveDraft = () => {
    const fields = {};
    for (const k of FIELDS) fields[k] = f[k].value;
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ fields, sel })); } catch (_) {}
  };
  for (const k of FIELDS) f[k].addEventListener("input", saveDraft);
  const intakeFiles = { list: [], total: 0, partial: false };
  const chips = h("div", {});
  const pickerGlobs = h("div", {});
  let renderChipsHook = null;
  const renderChipsBase = async () => {
    const mode = f.mode.value;
    const cur = sel[mode];
    if (!cur || !cur.include.length) { put(chips, h("p", { class: "muted" }, "Nothing chosen yet.")); put(pickerGlobs); return; }
    if (mode === "survey") {
      const { roots, globs, warnings } = surveyArgs(cur);
      put(chips, h("div", { class: "chips" }, ...roots.map((r) => h("span", { class: "chip" }, "+ " + r + "/"))));
      put(pickerGlobs, globs.length ? h("div", {}, h("div", { class: "muted" }, "Left out (passed as --exclude):"),
        h("div", { class: "chips" }, ...globs.map((g) => h("span", { class: "chip chip-exc" }, "− " + g))),
        ...warnings.map((w) => h("div", { class: "notes" }, w))) : null);
    } else {
      put(chips, h("p", { class: "muted" }, "Counting…"));
      try {
        const r = await api("/api/fs/expand", { include: cur.include, exclude: cur.exclude });
        intakeFiles.list = r.files; intakeFiles.total = r.total; intakeFiles.partial = r.partial;
        const shown = r.files.slice(0, 12);
        put(chips, h("div", {}, h("div", {}, h("strong", {}, `${r.partial ? "at least " : ""}${r.total} file(s)`), h("span", { class: "muted" }, ` — each is one extract dispatch${r.truncated || r.partial ? "; too many to hand-pick, survey a corpus instead" : ""}`)),
          h("div", { class: "chips" }, ...shown.map((p) => h("span", { class: "chip" }, p))),
          r.total > shown.length ? h("details", {}, h("summary", {}, `and ${r.total - shown.length} more`), h("pre", { class: "box" }, r.files.slice(12).join("\n"))) : null));
      } catch (err) { put(chips, h("p", { class: "s-failed" }, err.message)); }
      put(pickerGlobs);
    }
  };
  const renderChips = () => (renderChipsHook ? renderChipsHook() : renderChipsBase());
  const addBtn = h("button", { onclick: async () => {
    const mode = f.mode.value;
    const got = await pickSelection({ mode, start: STATE.root, initial: sel[mode] });
    if (got) { sel[mode] = got; saveDraft(); renderChips(); }
  } }, "Choose…");
  const clearBtn = h("button", { class: "ghost", onclick: () => { sel[f.mode.value] = null; saveDraft(); renderChips(); } }, "Clear");
  const surveyOnly = h("div", {},
    field("objective", "Objective", f.objective, "breadth: cover many capabilities; depth: probe fewer deeply"),
    h("div", { class: "grid2" }, field("objective_note", "Objective note", f.objective_note), field("scope_note", "Scope note", f.scope_note)),
    pickerGlobs,
    field("exclude", "More exclusions", f.exclude, "glob patterns, one per line, matched against each file's path inside a corpus folder"));
  const sourceLabel = h("label", { style: "margin-top:18px" });
  const syncMode = () => {
    const survey = f.mode.value === "survey";
    surveyOnly.hidden = !survey;
    sourceLabel.textContent = survey ? "Corpus folders" : "Input files";
    renderChips();
  };
  f.mode.onchange = () => { saveDraft(); syncMode(); };
  const submit = h("button", { class: "primary", onclick: async () => {
    const survey = f.mode.value === "survey";
    const spec = { mode: f.mode.value };
    for (const k of ["target_name", "target_interface", "objective", "objective_note", "scope_note", "max_rounds", "max_scenarios"]) spec[k] = f[k].value.trim();
    spec.exclude = f.exclude.value.split("\n").map((s) => s.trim()).filter(Boolean);
    const cur = sel[f.mode.value];
    // Kept with the run, so "New run from these inputs" restores this exactly.
    spec.selection = cur;
    spec.extra_exclude = spec.exclude.slice();
    if (survey) {
      const { roots, globs } = surveyArgs(cur || { include: [], exclude: [], dirs: {} });
      spec.corpus = roots;
      spec.exclude = [...new Set([...globs, ...spec.exclude])];
    } else {
      if (intakeFiles.partial || intakeFiles.total > intakeFiles.list.length) { submit.disabled = false; return toast("Too many files to hand-pick; survey a corpus instead", true); }
      spec.inputs = intakeFiles.list;
    }
    submit.disabled = true;
    try {
      const res = await api("/api/runs", spec);
      try { localStorage.removeItem(DRAFT_KEY); } catch (_) {}
      toast(`Created ${res.name}`);
      location.hash = `#/run/${encodeURIComponent(res.name)}`;
    } catch (err) { toast(err.message, true); submit.disabled = false; }
  } }, "Create run");
  // The mode as two choices side by side rather than a dropdown: it decides what
  // the rest of the form means, so both options and their consequence stay visible.
  const segBtn = (value, title, sub) => h("button", { type: "button", "data-mode": value, onclick: () => {
    f.mode.value = value; f.mode.dispatchEvent(new Event("change"));
  } }, h("strong", {}, title), h("small", {}, sub));
  const seg = h("div", { class: "seg" },
    segBtn("survey", "Survey a corpus", "Pick folders. Triage chooses what to read; you approve it at gate 0."),
    segBtn("intake", "Hand-pick files", "Pick exactly the files to read. Skips triage and gate 0."));
  const summaryBox = h("div", {});
  const renderSummary = () => {
    const cur = sel[f.mode.value];
    const survey = f.mode.value === "survey";
    const n = survey ? (cur ? surveyArgs(cur).roots.length : 0) : intakeFiles.total;
    put(summaryBox,
      h("div", { class: "num" }, survey ? `${n}` : `${intakeFiles.partial ? "≥" : ""}${n}`),
      h("div", { class: "muted" }, survey ? `corpus folder${n === 1 ? "" : "s"}` : `input file${n === 1 ? "" : "s"} · ${n} extract dispatch${n === 1 ? "" : "es"}`),
      h("p", { class: "muted", style: "margin-top:12px" }, `Created in ${STATE.runs_dir}. Creating a run calls no model.`));
    for (const b of seg.querySelectorAll("button")) b.classList.toggle("on", b.dataset.mode === f.mode.value);
  };
  renderChipsHook = async () => { await renderChipsBase(); renderSummary(); };
  put(app,
    h("div", { class: "page-head" }, h("div", {}, h("div", { class: "crumbs muted" }, h("a", { href: "#/" }, "Runs"), " / new"),
      h("h1", {}, fromRun ? `New run from ${fromRun}` : "New run"))),
    fromRun && initial && initial.derived ? h("div", { class: "banner" },
      "These inputs were read back from the run itself, which records what was passed, not the picker selection: folders and files are listed whole, and exclusions are in the box below.") : null,
    h("datalist", { id: "ifaces" }, ...["mcp", "http", "http-sse", "a2a"].map((v) => h("option", { value: v }))),
    h("div", { class: "form-grid" },
      h("div", {},
        h("div", { class: "panel form-sec" }, h("h2", {}, "1 · What to read"), h("p", { class: "lead" }, "Nothing outside what you choose here is ever read by the run."),
          seg, h("div", { style: "display:none" }, f.mode),
          sourceLabel, chips, h("div", { class: "row" }, addBtn, clearBtn),
          surveyOnly),
        h("div", { class: "panel form-sec" }, h("h2", {}, "2 · The target"), h("p", { class: "lead" }, "What the suite will test."),
          h("div", { class: "grid2" }, field("target_name", "Name", f.target_name), field("target_interface", "Interface", f.target_interface, "Free text: how the target is spoken to."))),
        h("div", { class: "panel form-sec" }, h("h2", {}, "3 · Limits"), h("p", { class: "lead" }, "Leave blank for the defaults. They can be raised later with set-limit."),
          h("div", { class: "grid2" }, field("max_rounds", "Max rounds", f.max_rounds), field("max_scenarios", "Max scenarios", f.max_scenarios)))),
      h("div", { class: "panel side-sum" }, h("h3", { style: "margin-top:0" }, "Summary"), summaryBox,
        h("div", { style: "margin-top:12px" }, submit))));
  submit.classList.add("big");
  submit.style.width = "100%";
  submit.style.justifyContent = "center";
  syncMode();
}

function specToForm(spec) {
  const fields = {};
  for (const k of ["mode", "target_name", "target_interface", "objective", "objective_note", "scope_note", "max_rounds", "max_scenarios"]) {
    if (spec[k] != null) fields[k] = String(spec[k]);
  }
  const sel = {};
  if (spec.selection && spec.selection.include) {
    sel[spec.mode] = spec.selection;
    fields.exclude = (spec.extra_exclude || []).join("\n");
  } else if (spec.mode === "survey") {
    const dirs = {};
    for (const p of spec.corpus || []) dirs[p] = true;
    sel.survey = { include: spec.corpus || [], exclude: [], dirs };
    fields.exclude = (spec.exclude || []).join("\n");
  } else {
    sel.intake = { include: spec.inputs || [], exclude: [], dirs: {} };
  }
  return { fields, sel, derived: spec.source === "derived" };
}

// -- settings ----------------------------------------------------------------

async function settingsPage() {
  put($("#top-run"));
  navOn("nav-settings");
  await loadState();
  const app = $("#app");
  let view;
  try { view = await api("/api/credentials"); } catch (err) { return put(app, h("div", { class: "banner err" }, err.message)); }
  const baseUrl = h("input", { value: view.base_url, size: 60, placeholder: "https://… (blank: the default Anthropic API)" });
  const kind = h("select", {}, h("option", { value: "auth_token", selected: view.auth_kind === "auth_token" }, "Auth token (Authorization: Bearer) — ANTHROPIC_AUTH_TOKEN"),
    h("option", { value: "api_key", selected: view.auth_kind === "api_key" }, "API key (x-api-key) — ANTHROPIC_API_KEY"));
  const secret = h("input", { type: "password", size: 50, autocomplete: "off", placeholder: view.secret_hint ? `set (${view.secret_hint}) — leave blank to keep` : "paste the token or key" });
  const headerRows = h("div", {});
  const addHeader = (name = "", hint = "") => {
    const n = h("input", { value: name, placeholder: "Header-Name", size: 24 });
    const v = h("input", { type: "password", size: 40, autocomplete: "off", placeholder: hint ? `set (${hint}) — leave blank to keep` : "value" });
    const row = h("div", { class: "row", style: "margin:4px 0" }, n, v, h("button", { class: "ghost", onclick: () => row.remove() }, "✕"));
    row._get = () => ({ name: n.value.trim(), value: v.value });
    headerRows.append(row);
  };
  for (const hd of view.headers) addHeader(hd.name, hd.hint);
  const model = h("input", { value: (RUN.settings && RUN.settings.model) || STATE.defaults.model, size: 28 });
  const result = h("div", {});
  const status = view.configured
    ? h("div", { class: "banner ok" }, h("span", { class: "s-done" }, "●"), `Set: ${view.auth_kind === "auth_token" ? "auth token" : "API key"} ${view.secret_hint}`, view.base_url ? ` via ${view.base_url}` : " to the default Anthropic API",
      view.headers.length ? `, with header(s) ${view.headers.map((x) => x.name).join(", ")}` : "", ".")
    : h("div", { class: "banner warn" }, "Not set up: no stage can be dispatched until the console has its own model access.");
  const save = async () => {
    try {
      await api("/api/credentials", { base_url: baseUrl.value.trim(), auth_kind: kind.value, secret: secret.value, headers: [...headerRows.children].map((r) => r._get()).filter((x) => x.name) });
      toast("Saved"); settingsPage();
    } catch (err) { toast(err.message, true); }
  };
  put(app, h("div", { class: "page-head" }, h("h1", {}, "Settings")), h("div", { class: "panel form-sec", style: "max-width:860px" },
    h("h2", {}, "Model access"),
    h("p", {}, "Dispatches use these credentials and nothing else — not the shell the console was started from, and not Claude Code's own settings. They stay on this machine; the page never receives a secret back, only its last four characters."),
    view.error ? h("div", { class: "banner err" }, view.error) : status,
    view.insecure ? h("div", { class: "banner err" }, `${view.path} can be read by other users. Run: chmod 600 "${view.path}"`) : null,
    h("label", {}, "Base URL"), baseUrl,
    h("label", {}, "Kind of secret"), kind,
    h("label", {}, "Secret"), secret,
    h("label", {}, "Extra headers"), h("div", { class: "muted" }, "Some gateways need one, such as x-context-guru-token."), headerRows,
    h("button", { class: "ghost", onclick: () => addHeader() }, "+ Add header"),
    h("div", { class: "row", style: "margin-top:14px" },
      h("button", { class: "primary", onclick: save }, "Save"),
      h("button", { onclick: async () => {
        if (!(await confirmDialog("Copy from Claude Code", [h("p", {}, "Copies the base URL, token or key, and extra headers from ~/.claude/settings.json into the console's own file. The values are read on the server and never pass through this page.")], "Copy"))) return;
        try { await api("/api/credentials/import", {}); toast("Copied from ~/.claude/settings.json"); settingsPage(); } catch (err) { toast(err.message, true); }
      } }, "Copy from Claude Code settings"),
      h("button", { class: "danger", disabled: !view.configured, onclick: async () => {
        if (!(await confirmDialog("Remove credentials", [h("p", {}, `Deletes ${view.path}. No stage can be dispatched until they are set again.`)], "Remove"))) return;
        try { await api("/api/credentials/clear", {}); toast("Removed"); settingsPage(); } catch (err) { toast(err.message, true); }
      } }, "Remove")),
    h("h3", { style: "margin-top:28px" }, "Test"),
    h("p", { class: "muted" }, "One tiny real call through the same path a dispatch takes (claude -p, an isolated config, these credentials, no tools). Measured at about $0.002."),
    h("div", { class: "row" }, h("span", {}, "model"), model, h("button", { disabled: !view.configured, onclick: async (ev) => {
      ev.target.disabled = true; put(result, h("p", { class: "muted" }, "Calling…"));
      try {
        const r = await api("/api/credentials/test", { model: model.value.trim() });
        put(result, h("div", { class: `banner ${r.ok ? "" : "err"}` }, r.ok ? "✓ " : "✗ ", r.message, r.cost != null ? ` (${money(r.cost)})` : ""));
      } catch (err) { put(result, h("div", { class: "banner err" }, err.message)); }
      ev.target.disabled = false;
    } }, "Test connection")),
    result,
    h("p", { class: "muted mono" }, view.path)));
}

// -- run page ----------------------------------------------------------------

const RUN = { name: null, data: null, selected: null, settings: null, staticFor: null, dynamic: null };

const OP_TEXT = {
  dispatch: (op) => `scripts/dispatch-stage.sh ${op.stage} RUN`,
  fanout: (op) => op.ids.length ? `scripts/dispatch-stage.sh ${op.stage} RUN <id>   × ${op.ids.length} still to do, at most 3 at once`
    : `scripts/dispatch-stage.sh ${op.stage} RUN <id>   (nothing left to dispatch)`,
  cli: (op) => `rubrica ${op.args.join(" ")} --run RUN`,
  validate: (op) => `rubrica validate --stage ${op.stage} --run RUN`,
  "check-refs": () => "rubrica check-refs --run RUN",
  record: (op) => `rubrica record-stage --stage ${op.stage} --model MODEL --effort EFFORT --skill rb-${op.stage}/SKILL.md`,
  "synthesise-interfaces": () => "rubrica synthesise-interfaces --run RUN  (then validate only if it printed a path), check-refs",
  "propose-batches": (op) => `rubrica propose-batches --run RUN --round ${op.round}  (then validate, or record “no closable holes”)`,
  "score-seal": (op) => `rubrica score-seal --run RUN --round ${op.round}; validate; check-refs; decide "round ${op.round}: <verdict>"`,
  followup: (op) => `re-seed once: ${op.reseed.length} × (instantiate with RUBRICA_RESEED=1, then challenge); rejects: ${op.reject.length} → score with RUBRICA_REJECT, propose-seal, score-seal`,
  smoke: () => "rubrica smoke --run RUN --agents ROSTER",
  "approve-gate": () => 'rubrica decide --note "human gate N (console): YOUR NOTE"',
  "approve-gate-0": () => 'rubrica intake --run RUN; record-stage for the triage passes; rubrica decide --note "human gate 0 (console): YOUR NOTE"',
};

function dispatchCount(step) {
  if (!step.calls_model) return 0;
  return step.recipe.reduce((n, op) => n + (op.op === "fanout" ? op.ids.length : op.op === "dispatch" ? 1
    : op.op === "followup" ? 2 * op.reseed.length + (op.reject.length ? 1 : 0) : 0), 0);
}

function averageCost() {
  let cost = 0, n = 0;
  for (const j of RUN.data.jobs) for (const m of j.members) if (m.cost) { cost += m.cost; n += 1; }
  return n ? cost / n : null;
}

async function runPage(name, stepId) {
  if (RUN.name !== name) { RUN.name = name; RUN.selected = null; RUN.staticFor = null; RUN.data = null; }
  if (stepId) RUN.selected = stepId;
  if (!STATE) await loadState();
  RUN.settings = settings.load(STATE.defaults);
  await refreshRun(true);
}

async function refreshRun(first = false) {
  clearTimeout(poller);
  try {
    RUN.data = await api(`/api/runs/${encodeURIComponent(RUN.name)}`);
  } catch (err) {
    put($("#app"), h("div", { class: "banner err" }, err.message), h("a", { href: "#/" }, "← Runs"));
    return;
  }
  if (first || !$("#run-layout")) buildRunShell();
  navOn(null);
  renderRunHead();
  renderNext();
  renderSteps();
  renderDetail();
  if (RUN.focusDetail) focusDetail();
  poller = setTimeout(refreshRun, RUN.data.active ? 1500 : 4000);
}

function buildRunShell() {
  put($("#app"),
    h("div", { id: "run-head" }),
    h("div", { id: "next-card" }),
    h("div", { class: "layout", id: "run-layout" },
      h("div", { class: "panel steps", id: "steps" }),
      h("div", { id: "detail" }, h("div", { class: "panel", id: "detail-static" }), h("div", { id: "detail-dynamic" }))));
  RUN.staticFor = null;
}

function editDispatchSettings() {
  const s = RUN.settings;
  const model = h("input", { value: s.model, style: "width:100%" });
  const effort = h("select", { style: "width:100%" }, ...STATE.efforts.map((e) => h("option", { value: e, selected: e === s.effort }, e)));
  const budget = h("input", { value: s.budget, placeholder: "no cap", type: "number", min: 0, step: "0.5", style: "width:100%" });
  const close = openModal("Dispatch settings", h("div", {},
    h("p", { class: "muted" }, "Passed to every model dispatch this browser starts, and recorded with record-stage."),
    h("div", { class: "grid2" },
      h("div", {}, h("label", {}, "Model"), model, h("div", { class: "help" }, "RUBRICA_MODEL — the id your gateway accepts")),
      h("div", {}, h("label", {}, "Effort"), effort, h("div", { class: "help" }, "RUBRICA_EFFORT"))),
    h("label", {}, "Cap per dispatch ($)"), budget, h("div", { class: "help" }, "RUBRICA_BUDGET — blank means no cap; the cost is reported either way"),
    h("div", { class: "row", style: "margin-top:16px" }, h("button", { class: "primary", onclick: () => {
      RUN.settings = { model: model.value.trim(), effort: effort.value, budget: budget.value.trim() };
      settings.save(RUN.settings); close(); renderRunHead(); RUN.staticFor = null; renderDetail();
    } }, "Save"), h("button", { onclick: () => close() }, "Cancel"))));
}

function renderRunHead() {
  const d = RUN.data;
  const s = RUN.settings;
  const base = `/runs/${encodeURIComponent(d.name)}`;
  const done = d.steps.filter((x) => x.status === "done").length;
  const curPhase = (d.steps.find((x) => x.id === d.next) || {}).phase;
  put($("#top-run"));
  put($("#run-head"), h("div", { class: "run-head" },
    h("div", { style: "min-width:0" },
      h("div", { class: "crumbs" }, h("a", { href: "#/" }, "Runs"), " / ", h("span", { class: "mono" }, d.name)),
      h("h1", { class: "truncate" }, d.target || d.name),
      h("div", { class: "meta" },
        d.mode ? h("span", { class: "chip-k" }, d.mode === "survey" ? "survey" : "hand-picked") : null,
        d.interface ? h("span", { class: "chip-k", title: d.interface }, d.interface) : null,
        h("span", {}, `${done} of ${d.steps.length} steps done`), h("span", { class: "faint" }, "·"),
        h("span", {}, `${money(d.cost)} spent from this console`))),
    h("div", { class: "tools" },
      h("button", { title: "Model, effort and cap for dispatches", onclick: editDispatchSettings },
        "⚙ ", h("span", { class: "mono" }, s.model), h("span", { class: "faint" }, `· ${s.effort}${s.budget ? ` · $${s.budget} cap` : ""}`)),
      h("a", { class: "button", href: `${base}/`, target: "_blank" }, "Summary ↗"),
      h("a", { class: "button", href: `${base}/target-brief.html`, target: "_blank" }, "Target brief ↗"),
      h("a", { class: "button", href: `#/new/${encodeURIComponent(d.name)}`, title: "Start a new run with the same inputs and settings" }, "↻ New run from these inputs"),
      h("button", { class: "danger", disabled: !!d.active, title: d.active ? "Cancel the running job first" : "Delete this run's folder for good",
        onclick: () => deleteRun(d.name, d.root) }, "Delete run")),
    h("div", { class: "phasebar" }, ...d.phases.map((p) => h("div", { class: `ph ${p.phase === curPhase ? "cur" : ""}`, title: `${p.phase}: ${p.done}/${p.total}` },
      h("div", { class: "lbl" }, h("b", { class: "truncate" }, p.phase), h("span", {}, `${p.done}/${p.total}`)),
      h("div", { class: "bar" }, h("i", { style: `width:${(100 * p.done / Math.max(1, p.total)).toFixed(0)}%` })))))));
}

async function deleteRun(name, root) {
  // The name must be typed: the folder holds model output that cost money, and
  // nothing brings it back.
  const typed = h("input", { class: "mono", placeholder: name, autocomplete: "off", spellcheck: "false" });
  const ok = await confirmDialog("Delete this run?", [
    h("p", {}, "This deletes the run's folder and everything in it, plus the console's own logs for it. It cannot be undone."),
    h("p", { class: "mono muted" }, root),
    h("label", {}, "Type the run's name to confirm"), typed,
  ], "Delete for good");
  if (!ok) return;
  try {
    await api(`/api/runs/${encodeURIComponent(name)}/delete`, { confirm: typed.value.trim() });
    toast("Run deleted");
    location.hash = "#/";
  } catch (e) { toast(e.message, true); }
}

function renderNext() {
  const d = RUN.data;
  const box = $("#next-card");
  // The step a card points at is usually the one already selected, so changing
  // the hash alone showed nothing new; bring its panel into view as well.
  const goto = (id) => () => {
    const hash = `#/run/${encodeURIComponent(d.name)}/${encodeURIComponent(id)}`;
    RUN.focusDetail = true;
    if (location.hash === hash) focusDetail();
    else location.hash = hash;
  };
  if (d.active) {
    const a = d.active;
    const running = a.members.filter((m) => m.status === "running").length;
    const finished = a.members.filter((m) => ["succeeded", "halted", "cancelled"].includes(m.status)).length;
    const last = a.entries.length ? a.entries[a.entries.length - 1].label : "";
    return put(box, h("div", { class: "next-card live" }, h("span", { class: "spinner s-running" }),
      h("div", { class: "what" }, h("div", { class: "k s-running" }, a.chain ? "Running to the next gate" : "Running"),
        h("div", { class: "t truncate" }, a.chain ? (last.replace(/^step: /, "") || a.title) : a.title),
        h("div", { class: "d" }, [a.members.length ? `${finished}/${a.members.length} dispatches finished, ${running} running` : null, took(a), money(a.cost)].filter(Boolean).join(" · "))),
      a.members.length ? h("div", { class: "bar live", style: "width:160px" }, h("i", { style: `width:${(100 * finished / a.members.length).toFixed(0)}%` })) : null,
      h("button", { onclick: goto(a.chain ? (RUN.selected || d.next) : a.step) }, "Show"),
      h("button", { class: "danger", onclick: async () => { try { await api(`/api/jobs/${a.id}/cancel`, {}); toast("Cancelling…"); } catch (e) { toast(e.message, true); } } }, "Cancel")));
  }
  const nxt = d.steps.find((x) => x.id === d.next);
  if (!nxt) return put(box, h("div", { class: "next-card done" }, h("span", { class: "s-done", style: "font-size:18px" }, "✓"),
    h("div", { class: "what" }, h("div", { class: "k" }, "Complete"), h("div", { class: "t" }, "Every step of this run is done"))));
  const failed = nxt.status === "failed";
  const gate = nxt.kind === "gate";
  const needsInput = nxt.id === "smoke";
  const cut = (nxt.unfinished || []).length;
  put(box, h("div", { class: `next-card ${failed ? "failed" : gate ? "gate" : ""}` },
    h("div", { class: "what" },
      h("div", { class: `k ${failed ? "s-failed" : gate ? "s-gate" : "s-ready"}` }, failed ? "Needs attention" : gate ? "Waiting for you" : cut ? "Interrupted — nothing is lost" : "Next step"),
      h("div", { class: "t truncate" }, nxt.title),
      h("div", { class: "d" }, failed ? "A check reported findings: repair, accept or re-run them."
        : cut ? `${cut === 1 && !nxt.unfinished[0] ? "Its dispatch" : `${cut} dispatch(es)`} did not finish, probably a lost connection. Resume runs only ${cut === 1 ? "that one" : "those"}.`
        : gate ? "Read the brief, then approve (a note is optional)."
        : needsInput ? "Needs an agents roster file — choose one on the step."
        : nxt.calls_model ? "Calls a model." : "Code only — no model.")),
    h("button", { class: needsInput ? "primary big" : "", onclick: goto(nxt.id) }, gate || failed || needsInput ? "Open" : "Details"),
    cut && !failed ? h("button", { class: "primary big", onclick: () => runStep(nxt), disabled: !STATE.prompt_ready,
      title: !STATE.prompt_ready ? STATE.prompt_reason : "" }, `Resume ▸`) : null,
    !gate && !failed && !needsInput ? h("button", { class: cut ? "big" : "primary big", onclick: runToGate, disabled: nxt.calls_model && !STATE.prompt_ready,
      title: nxt.calls_model && !STATE.prompt_ready ? STATE.prompt_reason : "" }, "Run to next gate ▸") : null));
}

const PHASES_OPEN = {};

function renderSteps() {
  const d = RUN.data;
  const box = $("#steps");
  const scroll = box.scrollTop;
  if (!RUN.selected) RUN.selected = (d.active && !d.active.chain && d.active.step) || d.next || d.steps[d.steps.length - 1].id;
  const sel = d.steps.find((x) => x.id === RUN.selected);
  const icon = (s) => s.status === "done" ? "✓" : s.status === "failed" ? "!" : s.kind === "gate" ? "◆" : s.status === "running" ? "" : "";
  const out = [];
  const byPhase = [];
  for (const s of d.steps) {
    if (!byPhase.length || byPhase[byPhase.length - 1].phase !== s.phase) byPhase.push({ phase: s.phase, steps: [] });
    byPhase[byPhase.length - 1].steps.push(s);
  }
  for (const grp of byPhase) {
    const ndone = grp.steps.filter((x) => x.status === "done").length;
    const complete = ndone === grp.steps.length;
    // A finished phase folds away, unless it holds the selected step or the
    // human opened it; the phase still being worked on is always open.
    const key = `${d.name}|${grp.phase}`;
    const open = PHASES_OPEN[key] ?? (!complete || (sel && sel.phase === grp.phase));
    out.push(h("div", { class: `phase ${open ? "open" : ""} ${complete ? "complete" : ""}`, onclick: () => { PHASES_OPEN[key] = !open; renderSteps(); } },
      h("span", { class: "chev" }, "▸"), complete ? "✓ " : "", grp.phase, h("span", { class: "n" }, `${ndone}/${grp.steps.length}`)));
    if (!open) continue;
    for (const s of grp.steps) {
      const count = s.members_total ? `${s.members_done.length}/${s.members_total}` : "";
      out.push(h("div", {
        class: `step ${s.status} ${s.kind === "gate" ? "gate" : ""} ${s.id === RUN.selected ? "sel" : ""}`,
        title: [s.summary, s.reason || s.status].filter(Boolean).join(" — "),
        onclick: () => { location.hash = `#/run/${encodeURIComponent(d.name)}/${encodeURIComponent(s.id)}`; },
      }, h("span", { class: "ic" }, icon(s)), h("span", { class: "title truncate" }, s.title), h("span", { class: "count" }, count)));
    }
  }
  put(box, ...out);
  box.scrollTop = scroll;
}

function focusDetail() {
  RUN.focusDetail = false;
  const box = $("#detail-static");
  if (!box) return;
  box.scrollIntoView({ behavior: "smooth", block: "start" });
  box.classList.remove("flash");
  void box.offsetWidth; // restart the animation on a second click
  box.classList.add("flash");
}

function selectedStep() { return RUN.data.steps.find((s) => s.id === RUN.selected) || RUN.data.steps[0]; }

function opts(extra = {}) { return { ...RUN.settings, ...extra }; }

async function runToGate() {
  const d = RUN.data;
  let preview;
  try { preview = (await api(`/api/runs/${encodeURIComponent(d.name)}/preview`)).steps; } catch (e) { return toast(e.message, true); }
  const n = preview.reduce((acc, s) => acc + dispatchCount(s), 0);
  const avg = averageCost();
  const lines = [
    h("p", {}, "This runs every step below in order and stops at the next gate, at any check that reports findings, or at anything that needs you."),
    h("ul", {}, ...preview.map((s) => h("li", {}, s.title, h("span", { class: "muted" }, !s.calls_model ? " — code, no model"
      : s.kind === "fanout" && !s.members_total ? " — model fan-out; how many is known once the steps before it run"
      : ` — ${dispatchCount(s)} model dispatch(es)`)))),
    h("p", {}, h("strong", {}, `${n}+ model dispatches`), ` using ${RUN.settings.model} at ${RUN.settings.effort} effort` + (RUN.settings.budget ? `, capped at $${RUN.settings.budget} each.` : ", no per-dispatch cap.")),
    avg ? h("p", { class: "muted" }, `Dispatches in this run have averaged ${money(avg)} each.`) : null,
    h("p", { class: "muted" }, "A round's later steps are only known once the round before them finishes, so a chain through the round loop can start more than this."),
  ];
  if (!(await confirmDialog("Run to next gate", lines, "Start"))) return;
  try { await api(`/api/runs/${encodeURIComponent(d.name)}/run-to-gate`, opts()); toast("Started"); refreshRun(); } catch (e) { toast(e.message, true); }
}

async function runStep(step, repair = false) {
  const n = dispatchCount(step);
  const extra = {};
  if (step.id === "smoke") {
    const roster = $("#smoke-roster");
    extra.agents = roster && roster.value.trim();
    if (!extra.agents) return toast("Choose an agents roster file first", true);
  }
  if (step.calls_model) {
    const avg = averageCost();
    const resuming = !repair && ((step.unfinished || []).length || (step.members_todo.length && step.members_done.length));
    const what = repair ? "Repair" : step.status === "done" ? "Run again" : resuming ? "Resume" : "Run";
    const ok = await confirmDialog(`${what}: ${step.title}`, [
      h("p", {}, h("strong", {}, repair ? `up to ${step.members_total || 1} model dispatch(es) — only the members the findings name` : `${n} model dispatch(es)`), ` using ${RUN.settings.model} at ${RUN.settings.effort} effort` + (RUN.settings.budget ? `, capped at $${RUN.settings.budget} each.` : ".")),
      repair ? h("p", {}, "The findings from the failed check are attached to the dispatch word for word. This is the step's one repair.") : null,
      step.status === "done" ? h("p", {}, "This step is already done. Running it again overwrites its output.") : null,
      resuming ? h("p", {}, "Only the dispatches that did not finish run again; everything that finished is kept and not paid for twice.") : null,
      avg ? h("p", { class: "muted" }, `Dispatches in this run have averaged ${money(avg)} each.`) : null,
    ], what);
    if (!ok) return;
  }
  try {
    await api(`/api/runs/${encodeURIComponent(RUN.name)}/steps/${encodeURIComponent(step.id)}/${repair ? "repair" : "run"}`, opts(extra));
    toast("Started");
    refreshRun();
  } catch (e) { toast(e.message, true); }
}

async function postAction(path, body, okMsg) {
  try {
    const job = await api(`/api/runs/${encodeURIComponent(RUN.name)}/${path}`, body);
    if (job.status && job.status !== "succeeded") toast(job.message || job.status, true);
    else toast(okMsg);
    RUN.staticFor = null;
    refreshRun();
    return job;
  } catch (e) { toast(e.message, true); return null; }
}

function renderDetail() {
  const step = selectedStep();
  const sig = `${step.id}|${step.status}|${RUN.data.ledger.failed[step.id] ? 1 : 0}`;
  const stat = $("#detail-static");
  // The static half holds forms; it is rebuilt only when the step or its status
  // changes, so a poll never wipes a note being typed.
  if (RUN.staticFor !== sig && !stat.contains(document.activeElement)) {
    RUN.staticFor = sig;
    put(stat, ...staticDetail(step));
  }
  // The dynamic half is rebuilt on every poll; without this, a section the reader
  // opened or closed snapped back every 1.5 s, so a running job's table could not
  // be watched.
  const dyn = $("#detail-dynamic");
  const was = new Map([...dyn.querySelectorAll("details[data-key]")].map((el) => [el.dataset.key, el.open]));
  put(dyn, ...dynamicDetail(step));
  for (const el of dyn.querySelectorAll("details[data-key]")) if (was.has(el.dataset.key)) el.open = was.get(el.dataset.key);
}

function staticDetail(step) {
  const d = RUN.data;
  const failed = !!d.ledger.failed[step.id];
  const attempts = d.ledger.attempts[step.id] || 0;
  const busy = !!d.active;
  const KIND = { code: "code · no model", prompt: "one model dispatch", fanout: "model fan-out", gate: "human gate", followup: "verdict follow-up" };
  const statusPill = step.kind === "gate" && step.status === "ready" ? h("span", { class: "pill s-gate" }, "waiting for you") : pill(step.status);
  const out = [
    h("div", { class: "detail-head" }, h("div", { class: "ttl" }, h("h2", {}, step.title),
      h("div", { class: "chips" }, statusPill, h("span", { class: "chip-k" }, KIND[step.kind] || step.kind),
        step.stage ? h("span", { class: "chip-k mono" }, step.stage) : null,
        step.members_total ? h("span", { class: "chip-k" }, `${step.members_done.length}/${step.members_total} members`) : null))),
  ];
  if (step.summary) out.push(h("p", { class: "summary" }, step.summary));
  if (step.reason && step.reason !== STATE.prompt_reason) out.push(h("p", { class: "reason" }, step.reason));
  if (step.notes.length > 6) {
    out.push(h("details", { class: "notes" }, h("summary", {}, step.notes[0], h("span", { class: "muted" }, ` — show all ${step.notes.length - 1}`)),
      ...step.notes.slice(1).map((n) => h("div", {}, n))));
  } else if (step.notes.length) out.push(h("div", { class: "notes" }, ...step.notes.map((n) => h("div", {}, n))));
  const what = h("details", { class: "subform" }, h("summary", {}, "What this runs"),
    h("div", { class: "cmds" }, ...step.recipe.map((op) => h("div", {}, (OP_TEXT[op.op] || (() => op.op))(op)))));

  if (step.kind === "gate") {
    out.push(...gatePanel(step, busy), what);
  } else {
    const actions = h("div", { class: "actions" });
    const canRun = !busy && ["ready", "failed", "done"].includes(step.status);
    const noModel = step.calls_model && !STATE.prompt_ready;
    if (step.id === "smoke") {
      const roster = h("input", { id: "smoke-roster", style: "flex:1;min-width:240px", placeholder: "agents roster file (never invented)" });
      actions.append(roster, h("button", { onclick: async () => { const p = await pickOne({ mode: "file", start: STATE.root }); if (p) roster.value = p[0]; } }, "Choose…"));
    }
    // A fan-out re-run only dispatches the members with no finished output, so
    // a step that was cut off part-way resumes rather than starting over.
    const left = step.members_todo.length;
    const resumable = (step.unfinished || []).length || (left && step.members_done.length);
    actions.append(h("button", { class: step.status === "done" ? "" : "primary", disabled: !canRun || noModel, onclick: () => runStep(step) },
      step.status === "done" ? "Run again"
        : resumable ? `▸ Resume${left ? ` (${left} left)` : ""}`
        : step.status === "failed" ? (step.members_total ? "Run the missing members again" : "Run again") : "▸ Run"));
    if (failed) {
      actions.append(h("button", { class: "primary", disabled: busy || !step.calls_model || attempts >= 2, title: attempts >= 2 ? "already repaired once" : step.calls_model ? "re-dispatch with the findings attached" : "a code step's findings name an upstream artifact", onclick: () => runStep(step, true) }, "Repair (one attempt)"));
    }
    actions.append(h("span", { class: "hint" }, noModel ? STATE.prompt_reason
      : busy ? "A job is running in this run." : step.status === "waiting" ? "An earlier step is not done yet."
      : step.calls_model ? `${dispatchCount(step) || "Some"} dispatch(es) · ${RUN.settings.model}` : "Code only — no model, no cost."));
    out.push(actions);
    // Only once some members ran and the rest did not: a step that never ran
    // has nothing to accept yet.
    if (failed || (step.members_todo.length && step.members_done.length && step.status !== "waiting")) {
      const note = h("textarea", { placeholder: "Why is it right to go on? This goes in decisions.md." });
      out.push(h("details", { class: "subform" }, h("summary", {}, failed ? "Accept these findings and continue" : "Accept as it stands (some members never produced output)"),
        note, h("div", { class: "row", style: "margin-top:8px" }, h("button", { disabled: busy, onclick: () => postAction(`steps/${encodeURIComponent(step.id)}/accept`, { note: note.value }, "Accepted") }, "Accept"))));
    }
    out.push(what);
  }
  if (step.round && (step.id.endsWith("/score-seal")) && step.status === "done") {
    const note = h("textarea", { placeholder: "Why stop the loop here?" });
    out.push(h("details", { class: "subform" }, h("summary", {}, "Stop the round loop after this round"), note,
      h("div", { class: "row", style: "margin-top:8px" }, h("button", { disabled: busy, onclick: () => postAction("stop-rounds", { note: note.value }, "Loop stopped") }, "Stop rounds"))));
  }
  return out;
}

// A gate brief is plain text: a `GATE N -- <run>` line, then sections whose
// heading starts in column 0 and whose lines are indented under it. That shape
// is all this relies on, so a section the brief adds later still renders.
function parseBrief(text) {
  const sections = [];
  for (const raw of text.split("\n")) {
    if (/^GATE \d+ -- /.test(raw)) continue;
    if (raw && !/^\s/.test(raw)) { sections.push({ title: raw.replace(/:$/, ""), lines: [] }); continue; }
    if (!sections.length) sections.push({ title: "Brief", lines: [] });
    sections[sections.length - 1].lines.push(raw);
  }
  for (const sec of sections) {
    while (sec.lines.length && !sec.lines[sec.lines.length - 1].trim()) sec.lines.pop();
    sec.items = sec.lines.filter((l) => /^  \S/.test(l)).length;
  }
  return sections.filter((sec) => sec.lines.some((l) => l.trim()));
}

const BRIEF_SHOWN = 10;

function briefLine(line) {
  const depth = Math.min(3, Math.floor((line.match(/^ */)[0].length) / 2));
  const text = line.trim();
  if (!text) return h("div", { class: "bl gap" });
  const cls = `bl d${depth}${/^\(none/.test(text) ? " none" : ""}${/\bunresolved\b|ABOVE the ceiling|\bfailed\b/i.test(text) ? " warn" : ""}`;
  // "name: 12/40 claims cited (30%)" and the like get a bar, so a long table
  // can be read by eye before it is read line by line.
  const m = text.match(/^(.{1,80}?):\s+(\d+)\/(\d+)\b(.*)$/);
  if (m && Number(m[3]) > 0) {
    const pct = Math.round((100 * Number(m[2])) / Number(m[3]));
    return h("div", { class: `${cls} bar-line` }, h("span", { class: "k mono truncate", title: m[1] }, m[1]),
      h("span", { class: "meter" }, h("i", { class: pct < 25 ? "low" : "", style: `width:${pct}%` })),
      h("span", { class: "v" }, `${m[2]}/${m[3]}${m[4]}`));
  }
  const id = text.match(/^((?:\[\d+\] )?[a-z][\w.-]*-[\w.-]+):\s(.*)$/);
  if (id) return h("div", { class: cls }, h("span", { class: "mono id" }, id[1]), " ", id[2]);
  return h("div", { class: cls }, text);
}

function gatePanel(step, busy) {
  // Gate 0 has a structured brief: cards for what needs a human, a checkbox per
  // file, and the rulings sent as `rubrica overrule`. Every other gate (and gate
  // 0 before triage is sealed) keeps the sectioned text brief.
  if (step.gate === 0) return gate0Panel(step, busy);
  return briefPanel(step, busy);
}

function briefPanel(step, busy) {
  const out = [];
  const g = step.gate;
  const key = `rubrica-gate|${RUN.name}|${g}`;
  let draft = {};
  try { draft = JSON.parse(localStorage.getItem(key) || "{}") || {}; } catch (_) { draft = {}; }
  draft.comments = draft.comments || {};
  const saveDraft = () => { try { localStorage.setItem(key, JSON.stringify(draft)); } catch (_) {} renderCount(); };
  const ready = step.status === "ready";

  const sectionsBox = h("div", { class: "brief-sections" }, h("p", { class: "muted" }, "Loading the gate brief…"));
  const historyBox = h("div", {});
  const countBox = h("span", { class: "muted" });
  const renderCount = () => {
    const n = Object.values(draft.comments).filter((c) => c && c.trim()).length;
    countBox.textContent = n ? `${n} section comment(s) will be included.` : "No section comments yet — use “Comment” on any section above.";
  };

  api(`/api/runs/${encodeURIComponent(RUN.name)}/gate/${g}`).then((r) => {
    const sections = parseBrief(r.text);
    put(sectionsBox, ...sections.map((sec) => {
      const many = sec.lines.length > BRIEF_SHOWN;
      const body = h("div", { class: "sec-body" });
      let all = !many;
      let filter = "";
      const paint = () => {
        const lines = filter ? sec.lines.filter((l) => l.toLowerCase().includes(filter)) : sec.lines;
        const shown = all || filter ? lines : lines.slice(0, BRIEF_SHOWN);
        put(body, ...shown.map(briefLine),
          !all && !filter ? h("button", { class: "small ghost", onclick: () => { all = true; paint(); } }, `Show all ${sec.lines.length} lines`) : null,
          filter && !lines.length ? h("div", { class: "bl none" }, "No line matches.") : null);
      };
      paint();
      const has = () => !!(draft.comments[sec.title] || "").trim();
      const comment = h("textarea", { class: "sec-comment", placeholder: `Your comment on “${sec.title}”`, value: draft.comments[sec.title] || "",
        oninput: (e) => { draft.comments[sec.title] = e.target.value; saveDraft(); btn.classList.toggle("on", has()); } });
      comment.hidden = !has();
      // In the heading, so it costs no row of its own; preventDefault keeps the
      // click from also folding the section.
      const btn = h("button", { class: `small sec-btn ${has() ? "on" : ""}`, onclick: (e) => { e.preventDefault(); e.stopPropagation(); card.open = true; comment.hidden = !comment.hidden; if (!comment.hidden) comment.focus(); } }, "💬 Comment");
      const search = many ? h("input", { class: "small sec-filter", placeholder: "Filter lines", oninput: (e) => { filter = e.target.value.trim().toLowerCase(); paint(); } }) : null;
      const quiet = /^\s*\(none/.test(sec.lines.join(" ").trim());
      // Open unless empty: a long section shows its first lines only, so the
      // whole brief can be skimmed top to bottom without a click.
      const card = h("details", { class: `sec ${quiet ? "quiet" : ""}`, open: quiet ? null : true },
        h("summary", {}, h("span", { class: "sec-title" }, sec.title), sec.items ? h("span", { class: "n" }, String(sec.items)) : null,
          h("span", { class: "spacer" }), ready ? btn : null),
        search ? h("div", { class: "sec-tools" }, search) : null,
        ready ? comment : null, body);
      return card;
    }));
    put(historyBox, r.history && r.history.length
      ? h("details", { class: "subform" }, h("summary", {}, `Earlier notes on this gate (${r.history.length})`),
          h("div", { class: "cmds" }, ...r.history.map((l) => h("div", {}, l))))
      : null);
  }).catch((e) => put(sectionsBox, h("div", { class: "banner err" }, e.message)));

  out.push(h("div", { class: "row", style: "margin-top:18px" }, h("h3", { style: "margin:0" }, `What gate ${g} asks you to check`), h("span", { class: "spacer" }),
      h("a", { class: "button small", href: `/runs/${encodeURIComponent(RUN.name)}/gate/${g}`, target: "_blank" }, "Plain text ↗"),
      h("a", { class: "button small", href: `/runs/${encodeURIComponent(RUN.name)}/`, target: "_blank" }, "Run summary ↗")),
    sectionsBox, historyBox);

  if (ready) {
    const note = h("textarea", { placeholder: g === 0 ? "Overall: what you checked, and whether the chosen inputs are right." : "Overall: what you checked, and your ruling on anything open.",
      value: draft.note || "", oninput: (e) => { draft.note = e.target.value; saveDraft(); } });
    renderCount();
    // One line, because decisions.md is one entry per line.
    const compose = () => [
      (draft.note || "").trim(),
      ...Object.entries(draft.comments).filter(([, c]) => c && c.trim()).map(([t, c]) => `on "${t}": ${c.trim()}`),
    ].filter(Boolean).join(" | ");
    const send = async (path, okMsg) => {
      const text = compose();
      // Approving needs no prose (the console records that it was approved here);
      // feedback with nothing in it says nothing.
      if (!text && !path.endsWith("/approve")) return toast("Write a note or a section comment first.", true);
      const job = await postAction(path, { note: text }, okMsg);
      if (job && job.status === "succeeded") { try { localStorage.removeItem(key); } catch (_) {} }
    };
    out.push(h("div", { class: "actions feedback", style: "flex-direction:column;align-items:stretch" },
      h("strong", {}, "Your review"), note, countBox,
      h("div", { class: "row" },
        h("button", { class: "primary", disabled: busy, onclick: () => send(`gates/${g}/approve`, `Gate ${g} approved`) }, `✓ Approve gate ${g}`),
        h("button", { disabled: busy, onclick: () => send(`gates/${g}/feedback`, "Feedback recorded — the gate is still open") }, "Record feedback, don't approve yet")),
      h("p", { class: "hint", style: "margin:0" }, g === 0
        ? "Approving admits the chosen inputs (rubrica intake) and writes your review to decisions.md."
        : "Both buttons write your review to decisions.md; only Approve lets the run go on. ",
        "The model steps never read decisions.md — to change what a step produced, edit its file or re-run the step, then approve.")));
  }
  if (g >= 1) {
    const check = h("select", {}, ...STATE.waivable_checks.map((c) => h("option", { value: c }, c)));
    const subject = h("input", { placeholder: "e.g. an artifact_id" });
    const remedy = h("select", {}, ...STATE.remedies.map((r) => h("option", { value: r }, r)));
    const reason = h("textarea", { placeholder: "Why the finding is correct and its fix is not available where it was raised." });
    out.push(h("details", { class: "subform" }, h("summary", {}, "Waive a finding (rubrica waive)"),
      h("div", { class: "grid2" }, h("div", {}, h("label", {}, "Check"), check), h("div", {}, h("label", {}, "Subject"), subject)),
      h("label", {}, "Remedy"), remedy, h("label", {}, "Reason"), reason,
      h("button", { disabled: busy, onclick: () => postAction("waive", { check: check.value, subject: subject.value.trim(), remedy: remedy.value, reason: reason.value }, "Waiver recorded") }, "Waive")));
    const lim = {};
    const limits = ["max_rounds", "max_scenarios", "max_scenario_part_bytes"].map((k) => { lim[k] = h("input", { type: "number", min: 1, placeholder: "unchanged" }); return h("div", {}, h("label", {}, k), lim[k]); });
    const why = h("textarea", { placeholder: "Why change it? Recorded in decisions.md." });
    out.push(h("details", { class: "subform" }, h("summary", {}, "Change a limit (rubrica set-limit)"), h("div", { class: "grid2" }, ...limits), h("label", {}, "Reason"), why,
      h("button", { disabled: busy, onclick: () => { const v = {}; for (const k in lim) if (lim[k].value) v[k] = Number(lim[k].value); postAction("set-limit", { limits: v, reason: why.value }, "Limit changed"); } }, "Set limit")));
  }
  return out;
}

// -- shared by the interactive gates -------------------------------------------
//
// The person at a gate decides only what they want to. Anything left alone stays
// as the stage decided; a reason is welcome and never demanded (the console then
// records "no reason given"); a card can be ticked "looks right" without
// changing it, and those ticks go into the review note.

// An optional reason: a text box plus one-click suggestions.
function reasonField(value, set, presets = []) {
  const input = h("input", { class: "g0-reason", placeholder: "Why? (optional)", value: value || "",
    oninput: (e) => set(e.target.value) });
  return h("span", { class: "g-reason" }, input,
    ...presets.map((text) => h("button", { class: "small ghost g-chip", title: "Use this reason",
      onclick: () => { input.value = text; set(text); } }, text)));
}

// The "you don't have to decide everything" line every interactive gate leads with.
function gateIntro(what) {
  return h("p", { class: "g-intro" },
    h("b", {}, "You only need to change what looks wrong. "),
    `Anything you leave alone stays as ${what} decided. Reasons are optional, and “Looks right” records that you checked a card without changing it.`);
}

// "Looks right" toggle for one card; `ok` is the draft's set of ticked card ids.
function okToggle(ok, id, onChange) {
  const on = !!ok[id];
  return h("button", { class: `small g-ok ${on ? "on" : ""}`, title: "Record that you checked this and agree",
    onclick: () => { if (on) delete ok[id]; else ok[id] = true; onChange(); } }, on ? "✓ Looks right" : "Looks right");
}

// The ticked cards, as one clause for the review note.
function okClause(ok) {
  const ids = Object.keys(ok);
  if (!ids.length) return "";
  const shown = ids.slice(0, 12).join(", ");
  return `checked and agreed: ${shown}${ids.length > 12 ? ` and ${ids.length - 12} more` : ""}`;
}

// The first few cards, and a button for the rest.
const CARDS_SHOWN = 6;
function someCards(cards, state, repaint) {
  if (state.all || cards.length <= CARDS_SHOWN + 2) return cards;
  return [...cards.slice(0, CARDS_SHOWN),
    h("button", { class: "small", onclick: () => { state.all = true; repaint(); } }, `Show ${cards.length - CARDS_SHOWN} more`)];
}

const DECLINE_TEXT = {
  off_objective: "not what this run is about",
  out_of_scope: "outside the target",
  near_duplicate: "a near-duplicate of another file",
  superseded: "superseded by another file",
  implementation_detail: "an implementation detail",
  no_evidence_value: "doesn't help the tests",
};

// -- gate 0: interactive ----------------------------------------------------
//
// The page never writes a run file. Each change becomes a `rubrica overrule`
// call on the server, then `triage-seal` and the checks re-run, so what the page
// shows after a save is what the run will actually admit. Pending changes live
// in this browser's draft until saved, so a poll cannot wipe them.

const GATE0_KINDS = {
  objective: "Objective",
  missing_surface: "Missing surface",
  decline: "Declined file",
  gap: "Gap",
  large_admit: "Large admit",
  split_group: "Split folder",
};

function gate0Panel(step, busy) {
  const box = h("div", {}, h("p", { class: "muted" }, "Loading gate 0…"));
  api(`/api/runs/${encodeURIComponent(RUN.name)}/gate/0`).then((r) => {
    if (!r.data || !r.data.sealed) return put(box, ...briefPanel(step, busy));
    put(box, ...gate0View(step, busy, r));
  }).catch((e) => put(box, h("div", { class: "banner err" }, e.message)));
  return [box];
}

function gate0View(step, busy, r) {
  const d = r.data;
  const ready = step.status === "ready" && !d.locked;
  const key = `rubrica-gate0|${RUN.name}`;
  let draft = {};
  try { draft = JSON.parse(localStorage.getItem(key) || "{}") || {}; } catch (_) { draft = {}; }
  draft.changes = draft.changes || {};
  draft.comments = draft.comments || {};
  draft.ok = draft.ok || {};
  const cardsState = { all: false };
  const save = () => { try { localStorage.setItem(key, JSON.stringify(draft)); } catch (_) {} };
  const files = new Map(d.files.map((f) => [f.candidate_id, f]));
  // A draft from before the last save may name a change the run already holds.
  for (const cid of Object.keys(draft.changes)) if (!files.has(cid)) delete draft.changes[cid];

  const target = (f) => {
    const c = draft.changes[f.candidate_id];
    if (!c) return f.decision;
    return c.action === "clear" ? f.triage_decision : c.action;
  };
  // Choosing a decision: back to what the run holds drops the change; back to
  // triage's own after a human override is a `clear`.
  const setChoice = (f, want) => {
    if (want === f.decision) delete draft.changes[f.candidate_id];
    else if (f.authority === "human" && want === f.triage_decision) draft.changes[f.candidate_id] = { action: "clear", reason: (draft.changes[f.candidate_id] || {}).reason || "" };
    else draft.changes[f.candidate_id] = { ...(draft.changes[f.candidate_id] || {}), action: want };
  };
  const choose = (f, want) => { setChoice(f, want); save(); repaint(); };
  const sizeOf = (f) => (f.bytes == null ? "?" : size(f.bytes));
  const who = (f) => (f.authority === "human" ? h("span", { class: "g0-who human", title: `triage said ${f.triage_decision}` }, "you") : h("span", { class: "g0-who" }, "triage"));

  const summaryBox = h("div", {});
  const needsBox = h("div", { class: "g0-cards" });
  const filesBox = h("div", {});
  const overridesBox = h("div", {});
  const actionsBox = h("div", {});
  let filter = "";
  let filesOpen = false;

  // A file's decision control: two buttons, plus a reason code and a reason
  // when it differs from what the run holds.
  const control = (f) => {
    const t = target(f);
    const changed = !!draft.changes[f.candidate_id];
    const c = draft.changes[f.candidate_id] || {};
    const seg = h("div", { class: "seg small" },
      h("button", { class: t === "admit" ? "on" : "", disabled: !ready, onclick: () => choose(f, "admit") }, "Admit"),
      h("button", { class: t === "decline" ? "on" : "", disabled: !ready, onclick: () => choose(f, "decline") }, "Decline"));
    if (!changed || !ready) return h("div", { class: "g0-control" }, seg);
    // A decline is pre-classified with the most general code; the person can change it.
    if (t === "decline" && c.action !== "clear" && !c.reason_code) { c.reason_code = "no_evidence_value"; draft.changes[f.candidate_id] = c; save(); }
    const code = t === "decline" && c.action !== "clear"
      ? h("select", { title: "Why it is declined", onchange: (e) => { c.reason_code = e.target.value; draft.changes[f.candidate_id] = c; save(); paintPending(); } },
          ...d.decline_codes.map((k) => h("option", { value: k, selected: c.reason_code === k ? true : null }, DECLINE_TEXT[k] || k.replaceAll("_", " "))))
      : null;
    const presets = t === "admit" ? ["needed for the tests", "triage misjudged it"] : ["not part of the target", "too big for what it adds"];
    const reason = reasonField(c.reason, (v) => { c.reason = v; draft.changes[f.candidate_id] = c; save(); paintPending(); }, presets);
    return h("div", { class: "g0-control" }, seg, code, reason);
  };

  const paintSummary = () => {
    const s = d.summary;
    const pending = Object.keys(draft.changes).length;
    put(summaryBox, h("div", { class: `g0-summary ${s.supported ? "" : "warn"}` },
      h("div", {}, h("div", { class: "v" }, s.supported ? "supported" : "NOT supported"), h("div", { class: "l" }, `objective: ${s.objective || "?"}`)),
      h("div", {}, h("div", { class: "v" }, `${s.admitted}`), h("div", { class: "l" }, `admitted · ${size(s.admitted_bytes)}`)),
      h("div", {}, h("div", { class: "v" }, `${s.declined}`), h("div", { class: "l" }, "declined")),
      h("div", {}, h("div", { class: "v" }, `${s.gaps_open}/${s.gaps_total}`), h("div", { class: "l" }, "gaps open")),
      h("div", {}, h("div", { class: "v" }, `${s.overridden}`), h("div", { class: "l" }, "your rulings")),
      pending ? h("div", {}, h("div", { class: "v pend" }, `${pending}`), h("div", { class: "l" }, "unsaved changes")) : null),
      d.locked ? h("p", { class: "banner" }, "Gate 0 is approved: intake has admitted these files, so they can no longer be changed in this run.") : null);
  };

  const card = (n) => {
    const f = n.candidate_id ? files.get(n.candidate_id) : null;
    const changed = f && draft.changes[f.candidate_id];
    const comment = h("textarea", { class: "sec-comment", placeholder: "Your comment (goes into your review note)", value: draft.comments[n.title] || "",
      oninput: (e) => { draft.comments[n.title] = e.target.value; save(); } });
    comment.hidden = !(draft.comments[n.title] || "").trim();
    const extra = [];
    if (n.kind === "gap") {
      if (n.wanted) extra.push(h("div", { class: "g0-wanted" }, h("b", {}, "Suggested fix: "), n.wanted));
      if (n.projection_id) {
        extra.push(h("div", { class: "muted small" }, "To supply it, write the file and run:"),
          h("code", { class: "g0-cmd" }, `rubrica adopt-projection --run ${d.run} --projection ${n.projection_id} --file <path>`));
      }
      extra.push(h("div", { class: "muted small" }, "Or accept the gap, and say so in a comment."));
    }
    if (n.kind === "split_group") extra.push(h("div", { class: "muted small" }, `Slices: ${(n.slices || []).join(", ")}. Check its files in “All files” below.`));
    if (n.recommended) extra.push(h("div", { class: "g0-wanted" }, h("b", {}, "Recommended objective: "), `${n.recommended.objective} — ${n.recommended.reason}`));
    return h("div", { class: `g0-card k-${n.kind} ${changed ? "changed" : ""}` },
      h("div", { class: "g0-card-head" }, h("span", { class: "chip-k" }, GATE0_KINDS[n.kind] || n.kind),
        h("span", { class: "g0-title" }, n.title), f ? who(f) : null, h("span", { class: "spacer" }),
        f ? h("span", { class: "muted small" }, sizeOf(f)) : null,
        ready && !changed ? okToggle(draft.ok, n.candidate_id || n.id, () => { save(); repaint(); }) : null,
        ready ? h("button", { class: "small ghost", title: "Add a comment", onclick: () => { comment.hidden = !comment.hidden; if (!comment.hidden) comment.focus(); } }, "💬") : null),
      n.detail ? h("details", { class: "g0-more" }, h("summary", {}, n.detail.length > 140 ? `${n.detail.slice(0, 140)}…` : n.detail),
        n.detail.length > 140 ? h("div", {}, n.detail) : null) : null,
      ...extra,
      f ? control(f) : null,
      ready ? comment : null);
  };

  // Declines sharing one reason code fold into a single card once there are
  // more than DECLINE_GROUP of them: seven near-duplicates are one question
  // ("were these really duplicates?"), not seven.
  const DECLINE_GROUP = 3;
  const paintNeeds = () => {
    if (!d.needs_you.length) {
      return put(needsBox, h("p", { class: "muted" }, "Nothing here needs you: no declines, no open gaps, no missing surfaces. Check the file list below if you want to, then approve."));
    }
    const byCode = new Map();
    for (const n of d.needs_you) {
      if (n.kind !== "decline") continue;
      const code = (files.get(n.candidate_id) || {}).reason_code || "?";
      if (!byCode.has(code)) byCode.set(code, []);
      byCode.get(code).push(n);
    }
    const shown = new Set();
    let out = [];
    for (const n of d.needs_you) {
      if (n.kind !== "decline") { out.push(card(n)); continue; }
      const code = (files.get(n.candidate_id) || {}).reason_code || "?";
      const group = byCode.get(code);
      if (group.length <= DECLINE_GROUP) { out.push(card(n)); continue; }
      if (shown.has(code)) continue;
      shown.add(code);
      const changed = group.filter((g) => draft.changes[g.candidate_id]).length;
      out.push(h("details", { class: `g0-card g0-group k-decline ${changed ? "changed" : ""}`, open: changed ? true : null },
        h("summary", { class: "g0-card-head" }, h("span", { class: "chip-k" }, "Declined files"),
          h("span", { class: "g0-title" }, `${group.length} declined as ${code.replaceAll("_", " ")}`),
          h("span", { class: "spacer" }), changed ? h("span", { class: "g0-pending" }, `${changed} changed`) : h("span", { class: "muted small" }, "open to review each")),
        h("div", { class: "g0-cards" }, ...group.map(card))));
    }
    put(needsBox, someCards(out, cardsState, paintNeeds));
  };

  const paintFiles = () => {
    const folders = new Map();
    for (const f of d.files) {
      if (filter && !`${f.candidate_id} ${f.path || ""} ${f.folder}`.toLowerCase().includes(filter)) continue;
      if (!folders.has(f.folder)) folders.set(f.folder, []);
      folders.get(f.folder).push(f);
    }
    const rows = [];
    for (const [folder, list] of folders) {
      const admitted = list.filter((f) => target(f) === "admit").length;
      const box = h("input", { type: "checkbox", disabled: !ready, title: "Admit or decline every file in this folder" });
      box.checked = admitted === list.length;
      box.indeterminate = admitted > 0 && admitted < list.length;
      // One repaint for the folder, not one per file: a folder can hold a hundred.
      box.onchange = () => {
        for (const f of list) if (f.admissible || !box.checked) setChoice(f, box.checked ? "admit" : "decline");
        save(); repaint();
      };
      rows.push(h("div", { class: "g0-folder" }, h("label", { class: "pick-box" }, box), h("b", { class: "mono" }, folder),
        h("span", { class: "muted small" }, `${admitted}/${list.length} admitted · ${size(list.reduce((a, f) => a + (f.bytes || 0), 0))}`)));
      for (const f of list) {
        const t = target(f);
        const fb = h("input", { type: "checkbox", disabled: !ready || (!f.admissible && t !== "admit") });
        fb.checked = t === "admit";
        fb.onchange = () => choose(f, fb.checked ? "admit" : "decline");
        const changed = !!draft.changes[f.candidate_id];
        rows.push(h("div", { class: `g0-file ${changed ? "changed" : ""} ${t === "admit" ? "" : "out"}` },
          h("label", { class: "pick-box" }, fb),
          h("details", {}, h("summary", {}, h("span", { class: "mono" }, f.candidate_id), " ", who(f),
            f.reason_code ? h("span", { class: "muted small" }, ` ${f.reason_code}`) : null),
            h("div", { class: "small" }, f.path ? h("div", { class: "mono muted" }, f.path) : null,
              h("div", {}, h("b", {}, "Triage: "), `${f.triage_decision || "?"} — ${f.triage_reason || ""}`),
              f.authority === "human" ? h("div", {}, h("b", {}, "You: "), `${f.decision} — ${f.reason || ""}`) : null)),
          h("span", { class: "muted small" }, sizeOf(f)),
          changed ? control(f) : null));
      }
    }
    const search = h("input", { class: "small sec-filter", placeholder: "Filter files", value: filter,
      oninput: (e) => { filter = e.target.value.trim().toLowerCase(); paintFiles(); const el = filesBox.querySelector(".sec-filter"); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } } });
    const sec = h("details", { class: "sec", open: filesOpen ? true : null, ontoggle: (e) => { filesOpen = e.target.open; } },
      h("summary", {}, h("span", { class: "sec-title" }, "All files"), h("span", { class: "n" }, String(d.files.length)),
        h("span", { class: "muted small" }, "checked = the run reads it")),
      h("div", { class: "sec-tools" }, search),
      h("div", { class: "sec-body g0-files" }, rows.length ? rows : h("div", { class: "bl none" }, "No file matches.")));
    put(filesBox, sec);
  };

  const paintOverrides = () => {
    put(overridesBox, d.overrides.length
      ? h("details", { class: "subform" }, h("summary", {}, `Your rulings in force (${d.overrides.length})`),
          ...d.overrides.map((o) => h("div", { class: "row g0-ovr" },
            h("span", { class: "mono" }, o.candidate_id), h("span", {}, `${o.replaces} → ${o.disposition.disposition}`),
            h("span", { class: "muted small" }, o.disposition.reason), h("span", { class: "spacer" }),
            ready ? h("button", { class: "small", onclick: () => { const f = files.get(o.candidate_id); if (f) choose(f, f.triage_decision); } }, "Undo") : null)))
      : null);
  };

  const note = h("textarea", { placeholder: "Anything to add? (optional)", value: draft.note || "",
    oninput: (e) => { draft.note = e.target.value; save(); } });
  const shared = h("input", { placeholder: "One reason for every change that has none of its own (optional)", value: draft.shared || "",
    oninput: (e) => { draft.shared = e.target.value; save(); paintPending(); } });
  // Updated in place as reasons are typed; repainting the whole action bar
  // would replace the input the human is typing in.
  const pendingBox = h("div", { class: "g0-pending" });
  const paintPending = () => {
    const n = Object.keys(draft.changes).length;
    const { problems } = collect();
    const okN = Object.keys(draft.ok).length;
    put(pendingBox, n ? `${n} unsaved change(s)` : null, okN ? h("span", { class: "muted" }, `${n ? " · " : ""}${okN} marked looks right`) : null,
      problems.length ? h("span", { class: "warn" }, ` — ${problems.join("; ")}`) : null);
  };
  const compose = () => [
    (draft.note || "").trim(),
    ...Object.entries(draft.comments).filter(([, c]) => c && c.trim()).map(([t, c]) => `on "${t}": ${c.trim()}`),
    okClause(draft.ok),
  ].filter(Boolean).join(" | ");
  const collect = () => {
    const out = [], problems = [];
    for (const [cid, c] of Object.entries(draft.changes)) {
      const reason = (c.reason || "").trim() || (draft.shared || "").trim();
      out.push({ candidate: cid, action: c.action, reason_code: c.action === "decline" ? c.reason_code : undefined, reason });
    }
    return { changes: out, problems };
  };
  const send = async (approve) => {
    const { changes, problems } = collect();
    if (problems.length) return toast(problems.join("; "), true);
    const text = compose();
    if (!approve && !changes.length && !text) return toast("Nothing to save yet.", true);
    if (approve) {
      const ok = await confirmDialog("Approve gate 0", [
        changes.length ? `${changes.length} change(s) will be applied first, then the run admits what is checked.` : "The run admits what triage chose.",
        "After this, the file selection is fixed for this run.",
      ], "Approve");
      if (!ok) return;
    }
    // The panel is rebuilt only while focus is outside it (so a poll never wipes
    // typing); the clicked button would otherwise keep the saved page stale.
    if (document.activeElement) document.activeElement.blur();
    const job = await postAction("gates/0/changes", { changes, note: text, approve }, approve ? "Gate 0 approved" : "Saved — gate 0 is still open");
    if (job && job.status === "succeeded") { try { localStorage.removeItem(key); } catch (_) {} RUN.staticFor = null; refreshRun(); }
  };
  const paintActions = () => {
    if (!ready) return put(actionsBox, null);
    const n = Object.keys(draft.changes).length;
    paintPending();
    put(actionsBox, h("div", { class: "actions feedback", style: "flex-direction:column;align-items:stretch" },
      h("strong", {}, "Your review"),
      pendingBox,
      n ? shared : null,
      note,
      h("div", { class: "row" },
        h("button", { class: "primary", disabled: busy, onclick: () => send(true) }, n ? `✓ Approve with ${n} change(s)` : "✓ Approve gate 0"),
        h("button", { disabled: busy, onclick: () => send(false) }, n ? "Save changes, don't approve yet" : "Record feedback, don't approve yet"),
        n ? h("button", { class: "ghost", disabled: busy, onclick: () => { draft.changes = {}; save(); repaint(); } }, "Discard changes") : null),
      h("p", { class: "hint", style: "margin:0" },
        "Each change is recorded with `rubrica overrule` (your reason goes into the record and decisions.md), then the triage record is re-sealed. ",
        "Approving then admits the checked files (rubrica intake). Triage's own decisions stay on disk beside yours.")));
  };

  function repaint() { paintSummary(); paintNeeds(); paintFiles(); paintOverrides(); paintActions(); }
  repaint();

  const sections = parseBrief(r.text);
  const full = h("details", { class: "subform" }, h("summary", {}, "Full text report"),
    h("div", { class: "sec-body" }, ...sections.flatMap((sec) => [h("div", { class: "bl" }, h("b", {}, sec.title)), ...sec.lines.map(briefLine)])));
  return [
    h("div", { class: "row", style: "margin-top:18px" }, h("h3", { style: "margin:0" }, "Gate 0: what the run may read"), h("span", { class: "spacer" }),
      h("a", { class: "button small", href: `/runs/${encodeURIComponent(RUN.name)}/gate/0`, target: "_blank" }, "Plain text ↗"),
      h("a", { class: "button small", href: `/runs/${encodeURIComponent(RUN.name)}/`, target: "_blank" }, "Run summary ↗")),
    summaryBox,
    ready ? gateIntro("triage") : null,
    h("h4", { class: "g0-h" }, d.locked ? `What was up for review (${d.needs_you.length})` : `Worth a look (${d.needs_you.length})`),
    needsBox,
    filesBox,
    overridesBox,
    r.history && r.history.length
      ? h("details", { class: "subform" }, h("summary", {}, `Earlier notes on this gate (${r.history.length})`),
          h("div", { class: "cmds" }, ...r.history.map((l) => h("div", {}, l))))
      : null,
    full,
    actionsBox,
  ];
}

function dynamicDetail(step) {
  const d = RUN.data;
  const out = [];
  const jobs = d.jobs.filter((j) => j.step === step.id || (j.chain && j.entries.some((e) => e.label === `step: ${step.title}`)));
  const active = d.active;
  if (step.members_total) {
    // One square per member: green done, light green half-way, amber dispatching
    // now, red failed.
    const live = step.kind === "followup" ? followupLive(step, active) : fanoutLive(active);
    const done = new Set(step.members_done);
    const all = [...step.members_done, ...step.members_todo];
    const cls = (m) => (done.has(m) || live[m] === "succeeded" ? "ok" : live[m] === "running" ? "run"
      : live[m] === "halted" ? "bad" : live[m] === "part" ? "part" : "");
    const finished = all.filter((m) => cls(m) === "ok").length;
    out.push(h("div", { class: "panel" }, h("div", { class: "section-head" }, h("h2", {}, "Members"), h("span", { class: "spacer" }),
        h("span", { class: "muted" }, step.kind === "followup"
          ? `${finished} of ${step.members_total} done`
          : `${step.members_done.length} of ${step.members_total} on disk`)),
      h("div", { class: "members-grid" }, ...all.map((m) => h("span", { class: cls(m), title: `${m} — ${live[m] || "waiting"}` }))),
      step.members_todo.length ? h("details", { "data-key": "todo", style: "margin-top:10px" }, h("summary", {}, `${step.members_todo.length} still to do`),
        h("div", { class: "mono muted", style: "overflow-wrap:anywhere" }, step.members_todo.join("  "))) : null));
  }
  const shown = active && (active.step === step.id || active.chain) ? [active, ...jobs.filter((j) => j.id !== active.id)] : jobs;
  if (!shown.length) {
    out.push(h("div", { class: "panel tight" }, h("p", { class: "muted", style: "margin:0" }, "Nothing has run this step from the console yet.")));
    return out;
  }
  out.push(h("h3", {}, "History"));
  for (const job of shown.slice(0, 8)) out.push(jobPanel(job));
  return out;
}

// A fan-out's member ids are `stage:id`; one square per id.
function fanoutLive(active) {
  return active ? Object.fromEntries(active.members.map((m) => [m.id.split(":").pop(), m.status])) : {};
}

// The follow-up's members are scenario ids, but its dispatches are not: a re-seed
// is `instantiate:id` then `challenge:id`, and every reject shares the one `score`
// dispatch. Keying on the id alone let the later, still-queued challenge hide the
// finished instantiate, and never coloured a reject at all.
function followupLive(step, active) {
  if (!active) return {};
  const by = Object.fromEntries(active.members.map((m) => [m.id, m.status]));
  const live = {};
  for (const s of step.members_todo) {
    const score = by.score;
    const inst = by[`instantiate:${s}`];
    const chal = by[`challenge:${s}`];
    if (!inst && !chal) { if (score) live[s] = score; continue; }
    if (inst === "halted" || chal === "halted") live[s] = "halted";
    else if (inst === "running" || chal === "running") live[s] = "running";
    else if (chal === "succeeded") live[s] = "succeeded";
    else if (inst === "succeeded") live[s] = "part";
  }
  return live;
}

// Running first, then failed, then waiting, then finished: in a fan-out of a
// hundred the dispatches doing something now were at the bottom of the table.
const MEMBER_ORDER = { running: 0, halted: 1, queued: 2, cancelled: 3, succeeded: 4 };

function jobPanel(job) {
  const rows = job.entries.map((e, i) => h("tr", {}, h("td", { class: "mono truncate", title: e.label }, e.label), h("td", {}, pill(e.status)), h("td", {}, e.exit ?? ""),
    h("td", {}, e.log ? h("button", { class: "ghost small", onclick: () => showLog(job, { entry: i }, e.label) }, "log") : null)));
  const ordered = [...job.members].sort((a, b) => (MEMBER_ORDER[a.status] ?? 2) - (MEMBER_ORDER[b.status] ?? 2));
  const members = ordered.map((m) => h("tr", {}, h("td", { class: "mono truncate", title: m.id }, m.id), h("td", {}, pill(m.status)),
    h("td", {}, m.turns || ""), h("td", {}, m.cost != null ? money(m.cost) : ""),
    h("td", { class: `truncate ${m.error ? "s-failed" : "mono muted"}`, title: m.error || m.last || "" }, m.error || m.last || ""),
    h("td", {}, h("button", { class: "ghost small", onclick: () => showLog(job, { member: m.id }, m.id) }, "log"))));
  const bad = ["halted", "findings"].includes(job.status);
  const okN = job.members.filter((m) => m.status === "succeeded").length;
  return h("div", { class: "panel" },
    h("div", { class: "job-head" }, h("span", { class: "name" }, job.chain ? "Run to next gate" : job.repair ? "Repair" : job.title), pill(job.status),
      h("span", { class: "spacer" }), h("span", { class: "muted" }, ago(job.created))),
    h("div", { class: "stats" },
      h("div", {}, h("span", { class: "v" }, took(job) || "—"), h("span", { class: "l" }, "time")),
      h("div", {}, h("span", { class: "v" }, money(job.cost)), h("span", { class: "l" }, "cost")),
      job.members.length ? h("div", {}, h("span", { class: "v" }, `${okN}/${job.members.length}`), h("span", { class: "l" }, "dispatches ok")) : null,
      job.model ? h("div", {}, h("span", { class: "v mono" }, job.model), h("span", { class: "l" }, job.effort)) : null),
    job.message ? h("p", { class: `msg ${bad ? "bad" : "muted"}` }, job.message) : null,
    job.findings && job.findings.length && job.status !== "succeeded" ? h("details", { "data-key": `${job.id}:findings`, open: true, style: "margin-top:8px" }, h("summary", {}, `Findings (${job.findings_total})`),
      h("pre", { class: "box", style: "margin-top:6px" }, job.findings.join("\n") + (job.findings_total > job.findings.length ? `\n… ${job.findings_total - job.findings.length} more` : ""))) : null,
    members.length ? h("details", { "data-key": `${job.id}:members`, open: job.status === "running" || (members.length <= 6 && bad), style: "margin-top:8px" }, h("summary", {}, `${members.length} dispatch(es)`),
      h("table", {}, h("colgroup", {}, h("col", { style: "width:26%" }), h("col", { style: "width:110px" }), h("col", { style: "width:60px" }), h("col", { style: "width:70px" }), h("col"), h("col", { style: "width:56px" })),
        h("thead", {}, h("tr", {}, h("th", {}, "Member"), h("th", {}, "Status"), h("th", {}, "Turns"), h("th", {}, "Cost"), h("th", {}, "Doing"), h("th", {}))), h("tbody", {}, members))) : null,
    rows.length ? h("details", { "data-key": `${job.id}:commands`, open: bad, style: "margin-top:4px" }, h("summary", {}, `${rows.length} command(s)`),
      h("table", {}, h("colgroup", {}, h("col"), h("col", { style: "width:110px" }), h("col", { style: "width:50px" }), h("col", { style: "width:56px" })),
        h("thead", {}, h("tr", {}, h("th", {}, "Command"), h("th", {}, "Result"), h("th", {}, "Exit"), h("th", {}))), h("tbody", {}, rows))) : null);
}

function renderLog(text, pretty) {
  if (!pretty) return h("pre", { class: "box" }, text);
  const out = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    if (line.startsWith("{")) {
      let ev;
      try { ev = JSON.parse(line); } catch (_) { out.push(h("div", { class: "log-line mono" }, line)); continue; }
      if (ev.type === "assistant") {
        for (const b of (ev.message && ev.message.content) || []) {
          if (b.type === "text" && b.text) out.push(h("div", { class: "log-line" }, h("span", { class: "k" }, "model"), b.text));
          if (b.type === "tool_use") out.push(h("div", { class: "log-line mono" }, h("span", { class: "k" }, "tool"), `${b.name} ${JSON.stringify(b.input).slice(0, 300)}`));
        }
      } else if (ev.type === "result") {
        out.push(h("div", { class: "log-line" }, h("span", { class: "k" }, "result"), `${ev.subtype || ""} ${ev.total_cost_usd != null ? money(ev.total_cost_usd) : ""} ${ev.num_turns || ""} turns`));
      }
      continue;
    }
    out.push(h("div", { class: "log-line mono" }, line));
  }
  return h("div", { class: "box", style: "max-height:60vh;overflow:auto" }, ...out);
}

function showLog(job, which, label) {
  let text = "";
  let offset = -1;
  let pretty = true;
  let timer = null;
  const view = h("div", {});
  const toggle = h("label", { style: "font-weight:400" }, h("input", { type: "checkbox", checked: true, onchange: (e) => { pretty = e.target.checked; draw(); } }), " readable view");
  const body = h("div", {}, toggle, view);
  const close = openModal(label, body, () => clearTimeout(timer));
  function draw() { const atEnd = true; put(view, renderLog(text, pretty)); if (atEnd) view.firstChild.scrollTop = 1e9; }
  async function tick() {
    try {
      const q = new URLSearchParams({ ...which, offset: String(offset) });
      const r = await api(`/api/jobs/${job.id}/log?${q}`);
      if (r.text) { text += r.text; draw(); }
      if (!text) put(view, h("p", { class: "muted" }, "Nothing written yet."));
      offset = r.next;
      const j = await api(`/api/jobs/${job.id}`);
      if (["running", "queued"].includes(j.status)) timer = setTimeout(tick, 1500);
    } catch (e) { put(view, h("p", { class: "s-failed" }, e.message)); }
  }
  tick();
  return close;
}

route();
