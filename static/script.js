"use strict";

/*
 * KIWIX DISCOVERY FRONTEND
 *
 * Talks to the FastAPI backend (app.py):
 *   GET /api/search?q=&mode=&n=      ranked results with `why` signals and size variants
 *   GET /api/library?q=&budget_gb=   storage-aware library
 *   GET /api/meta                    catalogue size, snapshot date, whether MiniLM modes are available
 *   GET /api/eval                    offline evaluation report (eval/results.json)
 *
 * Served by the backend (http://localhost:8000) it uses relative URLs. To open the page from somewhere else,
 * add ?api=http://localhost:8000 to the address.
 */

const API_BASE = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const RESULT_COUNT = 60;

const STORAGE = {
 library: "kiwix-discovery-library-v2",
 budget: "kiwix-discovery-budget-gb-v1"
};
const safeRead = (key, fallback) => {
  try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); }
  catch { return fallback; }
};
const safeWrite = (key, value) => {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage may be blocked */ }
};

const MODE_LABELS = {
 hybrid: "Hybrid (rules + MiniLM)",
 intent: "Intent (rules + BM25)",
 baseline: "Baseline (BM25 keywords)",
 semantic: "Semantic only (MiniLM)"
};
const LANG_NAMES = {
 eng:"English", fra:"French", spa:"Spanish", deu:"German", hin:"Hindi", ara:"Arabic", por:"Portuguese",
 rus:"Russian", zho:"Chinese", ita:"Italian", ben:"Bengali", tam:"Tamil", jpn:"Japanese", kor:"Korean",
 nld:"Dutch", pol:"Polish", tur:"Turkish", ukr:"Ukrainian", vie:"Vietnamese", ind:"Indonesian",
 swe:"Swedish", ell:"Greek", heb:"Hebrew", fas:"Persian", urd:"Urdu", tel:"Telugu", mar:"Marathi", mul:"Multilingual"
};
const FLAVOUR_LABELS = { maxi:"Full (maxi)", nopic:"No pictures", mini:"Intro only (mini)", "":"Standard" };

const state = {
 query: "",
 mode: "hybrid",
 sort: "rank",
 subject: "", language: "", updated: "",
 maxGB: Infinity,
 knownSize: false, hideStale: false, noLimits: false,
 results: [], parsed: null, error: "", loading: false,
 seq: 0,
 meta: null,
 library: safeRead(STORAGE.library, []),
 budget: Number(safeRead(STORAGE.budget, 5)) || 5,
 modalName: null,
 evalLoaded: false
};

/* ---------- API boundary ---------- */

async function getJSON(path, params = {}) {
 if (location.protocol === "file:" && !API_BASE) throw new Error("file-protocol");
 const qs = new URLSearchParams(params).toString();
 let res;
 try { res = await fetch(API_BASE + path + (qs ? "?" + qs : "")); }
 catch { throw new Error("unreachable"); }
 if (!res.ok) throw new Error("http-" + res.status);
 return res.json();
}
const DiscoveryService = {
 search: (q, mode) => getJSON("/api/search", { q, mode, n: RESULT_COUNT }),
 library: (q, budget) => getJSON("/api/library", { q, budget_gb: budget }),
 meta: () => getJSON("/api/meta"),
 evalReport: () => getJSON("/api/eval")
};
function friendlyError(err) {
 const m = String(err && err.message || err);
 if (m === "file-protocol")
  return {title: "Open this page through the backend",
   body: "This file was opened directly from disk. Start the backend with <code>uvicorn app:app --reload</code> and open <code>http://localhost:8000</code>, or add <code>?api=http://localhost:8000</code> to this page's address."};
 if (m === "unreachable")
  return {title: "Can't reach the backend",
   body: "Start it with <code>uvicorn app:app --reload</code> and make sure the address matches. The page needs the local server for search."};
 return {title: "The backend returned an error", body: "Details: <code>" + escapeHTML(m) + "</code>. Check the server console."};
}

/* ---------- helpers ---------- */

function escapeHTML(value) {
 return String(value ?? "").replace(/[&<>"']/g, c => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
 })[c]);
}
function byId(id) { return document.getElementById(id); }
function notify(message) {
 const toast = byId("toast"); toast.textContent = message; toast.classList.add("show");
 clearTimeout(notify.timer); notify.timer = setTimeout(() => toast.classList.remove("show"), 2800);
}
function formatGB(gb) {
 if (gb === null || gb === undefined || Number.isNaN(gb)) return "Unknown size";
 if (gb <= 0) return "0 MB";
 if (gb < 0.001) return "<1 MB";
 if (gb < 1) return Math.round(gb * 1024) + " MB";
 return gb.toFixed(gb >= 10 ? 0 : 2).replace(/\.?0+$/, "") + " GB";
}
function prettySubject(s) {
 if (!s || s === "unknown") return "Unknown subject";
 return s.split("-").join(" / ").replace(/^./, c => c.toUpperCase());
}
function langCodes(item) { return String(item.language || "").split(",").map(s => s.trim()).filter(Boolean); }
function langName(code) { return LANG_NAMES[code] || code.toUpperCase(); }
function langLabel(item) {
 const codes = langCodes(item);
 if (!codes.length) return "Language unknown";
 const names = codes.slice(0, 2).map(langName).join(", ");
 return codes.length > 2 ? names + " +" + (codes.length - 2) : names;
}
function year(item) { const y = parseInt(String(item.updated || "").slice(0, 4), 10); return Number.isFinite(y) ? y : null; }
const isLimitation = s => /^limitation/i.test(s);
const isStale = item => (item.why || []).some(s => /not updated recently/i.test(s));
function limitationCount(item) { return (item.why || []).filter(isLimitation).length; }
function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : ""; }
function directUrl(u) { return String(u || "").replace(/\.meta4$/, ""); }
function pickVariant(item) {
 const vs = item.variants || [];
 return vs.find(v => v.download_url === item.download_url) || vs[0] ||
  {flavour: "", size_gb: item.size_gb, download_url: item.download_url};
}
function variantSummary(item) {
 const sizes = (item.variants || []).map(v => v.size_gb).filter(v => v !== null && v !== undefined);
 if (sizes.length < 2) return "";
 const lo = Math.min(...sizes), hi = Math.max(...sizes);
 return sizes.length + " versions, " + formatGB(lo) + " to " + formatGB(hi);
}
function download(filename, text, type) {
 const blob = new Blob([text], {type}), url = URL.createObjectURL(blob), a = document.createElement("a");
 a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
}

/* Size slider: 0..100 maps logarithmically to 10 MB .. 200 GB; 100 means no limit. */
const SIZE_MIN_GB = 0.01, SIZE_MAX_GB = 200;
function sliderToGB(v) {
 v = Number(v);
 if (v >= 100) return Infinity;
 return SIZE_MIN_GB * Math.pow(SIZE_MAX_GB / SIZE_MIN_GB, v / 100);
}

/* ---------- library state ---------- */

const saved = name => state.library.some(x => x.name === name);
const persistLibrary = () => safeWrite(STORAGE.library, state.library);
function totalSavedGB() { return state.library.reduce((s, x) => s + (x.size_gb || 0), 0); }
function makeEntry(item, variant, note) {
 return {name: item.name, title: item.title, language: item.language, subject: item.subject,
  flavour: variant.flavour || "", size_gb: variant.size_gb ?? null,
  url: variant.download_url || item.download_url || "", why: item.why || [], note: note || ""};
}
function buildNote(item) {
 const v = item.chosen_variant || {};
 const signal = (item.why || []).find(s => !isLimitation(s));
 return (FLAVOUR_LABELS[v.flavour || ""] || v.flavour) + " version, " + formatGB(v.size_gb) + (signal ? ". " + signal : "");
}

/* ---------- filtering and ordering ---------- */

function filteredItems() {
 let list = [...state.results];
 if (state.subject) list = list.filter(x => (x.subject || "unknown") === state.subject);
 if (state.language) list = list.filter(x => langCodes(x).includes(state.language));
 if (state.updated) list = list.filter(x => (year(x) || 0) >= Number(state.updated));
 list = list.filter(x => x.size_gb !== null && x.size_gb !== undefined ? x.size_gb <= state.maxGB : !state.knownSize);
 if (state.knownSize) list = list.filter(x => x.size_gb !== null && x.size_gb !== undefined);
 if (state.hideStale) list = list.filter(x => !isStale(x));
 if (state.noLimits) list = list.filter(x => limitationCount(x) === 0);
 return list;
}
function activeItems() {
 const list = filteredItems();
 if (state.sort === "size") list.sort((a, b) => (a.size_gb ?? Infinity) - (b.size_gb ?? Infinity));
 else if (state.sort === "new") list.sort((a, b) => String(b.updated || "").localeCompare(String(a.updated || "")));
 return list;
}
function populateFilterOptions() {
 const fill = (id, entries, current) => {
  const select = byId(id), first = select.options[0];
  select.innerHTML = ""; select.appendChild(first);
  entries.forEach(([value, label]) => {
   const opt = document.createElement("option"); opt.value = value; opt.textContent = label; select.appendChild(opt);
  });
  const ok = entries.some(([v]) => String(v) === String(current));
  select.value = ok ? current : "";
  return ok ? current : "";
 };
 const count = {}, langs = {}, years = new Set();
 state.results.forEach(x => {
  const s = x.subject || "unknown"; count[s] = (count[s] || 0) + 1;
  langCodes(x).forEach(c => { langs[c] = (langs[c] || 0) + 1; });
  if (year(x)) years.add(year(x));
 });
 state.subject = fill("subject", Object.keys(count).sort().map(s => [s, prettySubject(s) + " (" + count[s] + ")"]), state.subject);
 state.language = fill("language", Object.keys(langs).sort((a, b) => langs[b] - langs[a]).map(c => [c, langName(c) + " (" + langs[c] + ")"]), state.language);
 state.updated = fill("updated", [...years].sort((a, b) => b - a).slice(0, 6).map(y => [String(y), y + " or newer"]), state.updated);
}

/* ---------- rendering ---------- */

function errorPanel(title, bodyHtml) {
 return `<div class="error-panel"><strong>${escapeHTML(title)}</strong><p style="margin-top:8px;color:#62647b;line-height:1.7">${bodyHtml}</p></div>`;
}
function whyList(item) {
 const why = item.why || [];
 if (!why.length) return "<div class=\"sig\">No explanation was returned for this result.</div>";
 return "<ul>" + why.map(s => `<li class="${isLimitation(s) ? "lim" : "sig"}">${escapeHTML(s)}</li>`).join("") + "</ul>";
}
function renderParsed() {
 const box = byId("parsed"), chips = [], p = state.parsed;
 if (state.error || state.loading || !state.query) { box.innerHTML = ""; return; }
 if (p) {
  if (p.subject) chips.push("Subject: " + prettySubject(p.subject));
  if (p.lang) chips.push("Language: " + langName(p.lang));
  if (p.max_gb) chips.push("Max size: " + formatGB(p.max_gb));
  if (p.age) chips.push("Age: " + p.age);
  if (!chips.length) chips.push("No subject, language or size detected; ranking uses keywords");
 } else if (state.mode === "baseline") chips.push("Keyword match only: the goal is not interpreted");
 else if (state.mode === "semantic") chips.push("Nearest neighbours by meaning only: no filters applied");
 box.innerHTML = chips.length ? `<span class="muted" style="font-size:11px;align-self:center">UNDERSTOOD</span>` +
  chips.map(c => `<span class="tag">${escapeHTML(c)}</span>`).join("") : "";
}
function renderCards() {
 const list = activeItems(), cards = byId("cards");
 byId("stat-saved").textContent = state.library.length;
 byId("stat-size").textContent = formatGB(totalSavedGB());
 byId("results-title").textContent = state.query ? "Discovery results" : "Recommended for you";
 byId("results-subtitle").textContent = state.query
  ? "Goal: " + state.query + " · " + MODE_LABELS[state.mode]
  : "Start with an example goal or describe your own";
 if (state.loading) {
  byId("result-count").textContent = "";
  cards.innerHTML = `<div class="empty skeleton"><p class="muted">Searching the local catalogue…</p></div>`;
  return;
 }
 if (state.error) {
  byId("result-count").textContent = "";
  cards.innerHTML = state.error.html ? errorPanel(state.error.title, state.error.body) : errorPanel("Search unavailable", escapeHTML(state.error));
  return;
 }
 const hidden = state.results.length - list.length;
 byId("result-count").textContent = list.length + " resources" + (hidden > 0 ? " (" + hidden + " hidden by filters)" : "");
 cards.innerHTML = list.length ? list.map(item => {
  const lims = limitationCount(item), summary = variantSummary(item);
  return `<article class="resource">
    <div class="resource-top">
      <div class="resource-icon">${escapeHTML((item.title || "?").trim().charAt(0).toUpperCase())}</div>
      <div class="resource-info"><h3>${escapeHTML(item.title)}</h3>
      <p>${escapeHTML(prettySubject(item.subject))} · ${escapeHTML(langLabel(item))}</p></div>
      <button class="save ${saved(item.name) ? "saved" : ""}" data-save="${escapeHTML(item.name)}"
       aria-label="${saved(item.name) ? "Remove from" : "Add to"} library">${saved(item.name) ? "♥" : "♡"}</button>
    </div>
    <div class="tags"><span class="tag rank">#${item._rank}</span>
      <span class="tag">${formatGB(item.size_gb)}</span>
      ${item.updated ? `<span class="tag">Updated ${escapeHTML(item.updated)}</span>` : ""}
      ${isStale(item) ? '<span class="tag stale">Stale</span>' : ""}
      ${lims ? `<span class="tag warn">${lims} limitation${lims > 1 ? "s" : ""}</span>` : ""}
    </div>
    <p class="description">${escapeHTML(item.description || "No description in the catalogue.")}</p>
    <div class="why"><strong>✦ Why this resource?</strong>${whyList(item)}</div>
    <div class="card-foot"><small>${escapeHTML(summary || "Single version")}</small>
      <button class="linkbtn" data-detail="${escapeHTML(item.name)}">Details ↗</button></div>
  </article>`;
 }).join("") : `<div class="empty"><div style="font-size:28px">⌕</div>
    <h3 style="margin:10px">${state.results.length ? "No resources match these filters" : "No matching resources"}</h3>
    <p class="muted" style="margin:8px 0 15px">${state.results.length ? "Remove some filters to see the " + state.results.length + " results." : "Try a broader goal or a different ranking method."}</p>
    ${state.results.length ? '<button class="secondary" id="empty-reset">Reset filters</button>' : ""}</div>`;
}
function renderLibrary() {
 const items = state.library;
 const total = totalSavedGB(), remaining = state.budget - total;
 const unknown = items.filter(x => x.size_gb === null || x.size_gb === undefined).length;
 byId("lib-count").textContent = items.length;
 byId("lib-size").textContent = formatGB(total);
 byId("lib-remaining").textContent = remaining < 0 ? "-" + formatGB(-remaining) : formatGB(remaining);
 byId("budget").value = state.budget;
 byId("budget-bar").style.width = Math.min(100, total / state.budget * 100) + "%";
 byId("budget-bar").style.background = remaining < 0 ? "#d84b5c" : "var(--purple)";
 byId("budget-note").textContent = (remaining < 0
  ? "Over budget by " + formatGB(-remaining) + ". Consider removing resources."
  : "You have " + formatGB(remaining) + " of planned storage remaining.") +
  (unknown ? " " + unknown + " saved resource" + (unknown > 1 ? "s have" : " has") + " an unknown size and isn't counted." : "");
 byId("nav-count").textContent = items.length ? "(" + items.length + ")" : "";
 byId("stat-saved").textContent = items.length;
 byId("stat-size").textContent = formatGB(total);
 byId("library-list").innerHTML = items.length ? `<div class="table-wrap"><table>
 <thead><tr><th>Resource</th><th>Language</th><th>Version</th><th>Action</th></tr></thead>
 <tbody>${items.map(x => `<tr><td><strong>${escapeHTML(x.title)}</strong><br>
 <span class="muted">${escapeHTML(prettySubject(x.subject))}</span>${x.note ? `<span class="note-line">✦ ${escapeHTML(x.note)}</span>` : ""}</td>
 <td>${escapeHTML(langLabel(x))}</td>
 <td>${escapeHTML(FLAVOUR_LABELS[x.flavour || ""] || x.flavour)} · ${formatGB(x.size_gb)}</td>
 <td><button class="linkbtn" data-save="${escapeHTML(x.name)}">Remove</button></td></tr>`).join("")}</tbody>
 </table></div>` : `<div class="empty"><h3>Your library is empty</h3>
 <p class="muted" style="margin:8px 0 15px">Discover resources and save the ones you need, or let Build My Library pick for you.</p>
 <button class="primary" data-goto="discover">Explore resources</button></div>`;
}

/* ---------- evaluation tab ---------- */

const EVAL_LABELS = {baseline: "Baseline (BM25)", intent: "Intent (rules + BM25)", semantic: "Semantic (MiniLM)", hybrid: "Hybrid (rules + MiniLM)"};
const pct = v => (v === undefined || v === null) ? "–" : Math.round(v * 100) + "%";
async function loadEvaluation() {
 const box = byId("eval-body");
 try {
  const report = await DiscoveryService.evalReport();
  if (report.error) { box.innerHTML = `<div class="empty"><h3>No report yet</h3><p class="muted" style="margin-top:8px">${escapeHTML(report.error)}</p></div>`; return; }
  renderEvaluation(report); state.evalLoaded = true;
 } catch (err) {
  const e = friendlyError(err); box.innerHTML = errorPanel(e.title, e.body);
 }
}
function renderEvaluation(r) {
 const methods = r.methods || Object.keys(r.summary || {});
 const label = m => EVAL_LABELS[m] || m;
 const best = methods.reduce((a, m) => (r.summary[m].ndcg > (r.summary[a] ? r.summary[a].ndcg : -1) ? m : a), methods[0]);
 const vs = r.vs_baseline;
 const bars = methods.map(m => `<div class="bar-row"><span>${escapeHTML(label(m))}</span>
  <div class="bar"><div class="${m === "baseline" ? "alt" : ""}" style="width:${Math.round(r.summary[m].ndcg * 100)}%"></div></div>
  <strong>${r.summary[m].ndcg.toFixed(2)}</strong></div>`).join("");
 const summaryRows = methods.map(m => {
  const s = r.summary[m];
  return `<tr><td><strong>${escapeHTML(label(m))}</strong></td><td>${s.p.toFixed(3)}</td><td>${s.recall.toFixed(3)}</td><td>${s.ndcg.toFixed(3)}</td><td>${s.mrr.toFixed(3)}</td></tr>`;
 }).join("");
 const perRows = (r.per_query || []).map(q => {
  const vals = methods.map(m => q.ndcg[m]), max = Math.max(...vals);
  return `<tr><td>${escapeHTML(q.q)}</td><td>${q.n_rel}</td>${methods.map(m =>
   `<td class="${q.ndcg[m] === max && max > 0 ? "best" : ""}">${q.ndcg[m].toFixed(2)}</td>`).join("")}</tr>`;
 }).join("");
 byId("eval-body").innerHTML = `
  <div class="notice">Judgments are one person's reading of the catalogue (<code>${escapeHTML(r.judgments || "eval/queries_labels.json")}</code>) and some ranking rules were tuned while looking at a few of these same queries. Treat the gains as indicative, not proven. Report: ${escapeHTML(r.generated || "unknown date")}, k=${r.k}.</div>
  <div class="metric-grid">
    <div class="metric"><span class="muted">Judged queries</span><strong>${r.queries}</strong><small class="muted">Fixed test set</small></div>
    <div class="metric"><span class="muted">Best nDCG@${r.k}</span><strong>${escapeHTML(label(best))}</strong><small class="muted">${r.summary[best].ndcg.toFixed(3)} mean</small></div>
    <div class="metric"><span class="muted">${vs ? escapeHTML(label(vs.method)) + " vs baseline" : "Per-query result"}</span>
      <strong>${vs ? vs.better + " better" : "–"}</strong><small class="muted">${vs ? vs.tied + " tied, " + vs.worse + " worse (nDCG per query)" : ""}</small></div>
  </div>
  <div class="panel">
    <h3>Mean nDCG@${r.k} by method</h3>
    <p>Higher is better. Baseline is plain keyword BM25 with no query parsing.</p>
    <div class="compare-bars">${bars}</div>
    <div class="table-wrap"><table><thead><tr><th>Method</th><th>P@${r.k}</th><th>Recall@${r.k}</th><th>nDCG@${r.k}</th><th>MRR</th></tr></thead><tbody>${summaryRows}</tbody></table></div>
  </div>
  <div class="panel" style="margin-top:20px">
    <h3>Per-query nDCG@${r.k}</h3>
    <p>The best method on each query is highlighted. #rel is the number of resources judged relevant.</p>
    <div class="table-wrap eval-table-wrap"><table><thead><tr><th>Query</th><th>#rel</th>${methods.map(m => `<th>${escapeHTML(label(m))}</th>`).join("")}</tr></thead><tbody>${perRows}</tbody></table></div>
    ${r.note ? `<p class="muted" style="font-size:11px;margin-top:12px">${escapeHTML(r.note)}</p>` : ""}
  </div>
  <div class="panel" style="margin-top:20px">
    <h3>Known limitations</h3>
    <ul class="limit-list">
      <li>Only ${r.queries} queries, judged by one person; the numbers are noisy.</li>
      <li>Subject, audience and content type are inferred from folder names and keyword rules, not catalogue fields.</li>
      <li>The catalogue has no download or popularity data; article count is only a rough proxy.</li>
      <li>Intent ranking is weaker than the baseline on some queries (grammar, dictionaries, school maths).</li>
      <li>MiniLM weights and its similarity floor are hand-picked, not tuned.</li>
    </ul>
  </div>`;
}

/* ---------- actions ---------- */

async function runSearch() {
 const q = byId("intent").value.trim();
 if (!q) { notify("Describe your goal or choose an example."); byId("intent").focus(); return; }
 state.query = q;
 const seq = ++state.seq;
 state.loading = true; state.error = ""; renderCards(); renderParsed();
 try {
  const data = await DiscoveryService.search(q, state.mode);
  if (seq !== state.seq) return;
  state.results = (data.results || []).map((x, i) => ({...x, _rank: i + 1}));
  state.parsed = data.parsed || null;
  state.error = data.error || "";
 } catch (err) {
  if (seq !== state.seq) return;
  state.results = []; state.parsed = null; state.error = {html: true, ...friendlyError(err)};
 }
 state.loading = false;
 populateFilterOptions(); renderParsed(); renderCards();
}
function toggleSave(name) {
 if (saved(name)) {
  state.library = state.library.filter(x => x.name !== name); notify("Removed from My Library.");
 } else {
  const item = state.results.find(x => x.name === name);
  if (!item) return;
  state.library.push(makeEntry(item, pickVariant(item))); notify("Added to My Library.");
 }
 persistLibrary(); renderCards(); renderLibrary();
}
function addVariant(name, index) {
 const item = state.results.find(x => x.name === name);
 const variant = item && (item.variants || [])[index];
 if (!variant) return;
 state.library = state.library.filter(x => x.name !== name);
 state.library.push(makeEntry(item, variant));
 persistLibrary(); renderCards(); renderLibrary(); notify("Saved the " + (FLAVOUR_LABELS[variant.flavour || ""] || variant.flavour).toLowerCase() + " version.");
}
async function buildLibrary() {
 const q = state.query || byId("intent").value.trim();
 if (!q) { notify("Run a search on Discover first, so the library can be built around your goal."); return; }
 if (state.library.length && !confirm("Replace your current " + state.library.length + " saved resources with an automatic selection?")) return;
 const btn = byId("build-library"); btn.disabled = true; btn.textContent = "Building…";
 try {
  const r = await DiscoveryService.library(q, state.budget);
  if (!r.items || !r.items.length) { notify("Nothing relevant fits a " + formatGB(state.budget) + " budget for this goal."); return; }
  state.query = q;
  state.library = r.items.map(i => makeEntry(i, i.chosen_variant, buildNote(i)));
  persistLibrary(); renderCards(); renderLibrary();
  notify("Built a library of " + r.items.length + " resources using " + formatGB(r.used_gb) + " of " + formatGB(r.budget_gb) + ".");
 } catch (err) {
  notify(friendlyError(err).title + ".");
 } finally { btn.disabled = false; btn.textContent = "✦ Build from my goal"; }
}
function openDetails(name) {
 const item = state.results.find(x => x.name === name); if (!item) return;
 state.modalName = name;
 const entry = state.library.find(x => x.name === name);
 const link = safeUrl(directUrl(item.download_url));
 byId("modal-title").textContent = item.title;
 byId("modal-content").innerHTML = `
  <div class="tags"><span class="tag rank">#${item._rank}</span><span class="tag">${escapeHTML(prettySubject(item.subject))}</span>
  <span class="tag">${escapeHTML(langLabel(item))}</span></div>
  <p style="margin-top:15px;line-height:1.8">${escapeHTML(item.description || "No description in the catalogue.")}</p>
  <h3 style="margin-top:20px">Why it was recommended</h3>
  <div class="why" style="margin-top:8px">${whyList(item)}</div>
  <h3 style="margin-top:20px">Catalogue metadata</h3>
  <div class="table-wrap"><table><tbody>
  <tr><td>Languages</td><td>${escapeHTML(langCodes(item).map(langName).join(", ") || "Unknown")}</td></tr>
  <tr><td>Subject</td><td>${escapeHTML(prettySubject(item.subject))}</td></tr>
  <tr><td>Updated</td><td>${escapeHTML(item.updated || "Unknown")}</td></tr>
  <tr><td>Size (best-matching version)</td><td>${formatGB(item.size_gb)}</td></tr>
  <tr><td>Ranking score</td><td>${escapeHTML(item.score)}</td></tr>
  <tr><td>Catalogue name</td><td>${escapeHTML(item.name)}</td></tr>
  </tbody></table></div>
  ${(item.variants || []).length ? `<h3 style="margin-top:20px">Versions</h3>${item.variants.map((v, i) => `
   <div class="variant-row"><span><strong>${escapeHTML(FLAVOUR_LABELS[v.flavour || ""] || v.flavour)}</strong> · ${formatGB(v.size_gb)}</span>
   ${entry && entry.url === v.download_url ? '<span class="muted">Saved</span>' : `<button class="linkbtn" data-add-variant="${escapeHTML(name)}" data-vi="${i}">Save this version</button>`}</div>`).join("")}` : ""}
  ${link ? `<p style="margin-top:14px"><a class="dl-link" href="${escapeHTML(link)}" target="_blank" rel="noopener noreferrer">Direct download link ↗</a></p>` : ""}
  <button class="primary" style="width:100%;margin-top:16px" data-save="${escapeHTML(name)}">
  ${saved(name) ? "Remove from My Library" : "Add to My Library"}</button>`;
 byId("modal-backdrop").classList.add("open");
}
function closeModal() { state.modalName = null; byId("modal-backdrop").classList.remove("open"); }
function switchView(view) {
 document.querySelectorAll(".view").forEach(el => el.classList.toggle("active", el.id === view));
 document.querySelectorAll(".navbtn").forEach(el => el.classList.toggle("active", el.dataset.view === view));
 if (view === "library") renderLibrary();
 if (view === "evaluation" && !state.evalLoaded) loadEvaluation();
 window.scrollTo({top: 0, behavior: "smooth"});
}
function exportManifest() {
 if (!state.library.length) { notify("Your library is empty."); return; }
 const items = state.library.map(x => ({title: x.title, name: x.name, flavour: x.flavour, size_gb: x.size_gb,
  why: x.why, url: directUrl(x.url)}));
 download("my_library.json", JSON.stringify({query: state.query || null, budget_gb: state.budget,
  used_gb: Math.round(totalSavedGB() * 100) / 100, items}, null, 2), "application/json");
}
function exportScript() {
 const usable = state.library.filter(x => safeUrl(directUrl(x.url)));
 if (!usable.length) { notify("Nothing with a download link to export."); return; }
 const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'";
 const text = "#!/bin/sh\n" + usable.map(x =>
  `curl -L -C - -O ${q(directUrl(x.url))}   # ${String(x.title).replace(/[\r\n]+/g, " ")} (${x.size_gb ?? "?"} GB)\n`).join("");
 download("download.sh", text, "text/x-shellscript");
}

/* ---------- event wiring ---------- */

byId("search-btn").addEventListener("click", runSearch);
byId("intent").addEventListener("keydown", e => {
 if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runSearch(); }
});
document.querySelectorAll("[data-prompt]").forEach(btn => btn.addEventListener("click", () => {
 byId("intent").value = btn.dataset.prompt; runSearch();
}));
document.querySelectorAll("[data-view]").forEach(btn => btn.addEventListener("click", () => switchView(btn.dataset.view)));
byId("mode").addEventListener("change", e => {
 state.mode = e.target.value;
 if (byId("intent").value.trim()) runSearch();
});
byId("sort").addEventListener("change", e => { state.sort = e.target.value; renderCards(); });
["subject", "language", "updated"].forEach(id => byId(id).addEventListener("change", () => {
 state[id] = byId(id).value; renderCards();
}));
byId("max-size").addEventListener("input", e => {
 state.maxGB = sliderToGB(e.target.value);
 byId("size-label").textContent = state.maxGB === Infinity ? "No limit" : formatGB(state.maxGB);
 renderCards();
});
byId("known-size").addEventListener("change", e => { state.knownSize = e.target.checked; renderCards(); });
byId("hide-stale").addEventListener("change", e => { state.hideStale = e.target.checked; renderCards(); });
byId("no-limits").addEventListener("change", e => { state.noLimits = e.target.checked; renderCards(); });
byId("reset").addEventListener("click", () => {
 ["subject", "language", "updated"].forEach(id => { byId(id).value = ""; state[id] = ""; });
 byId("max-size").value = 100; byId("size-label").textContent = "No limit";
 ["known-size", "hide-stale", "no-limits"].forEach(id => { byId(id).checked = false; });
 byId("sort").value = "rank";
 Object.assign(state, {maxGB: Infinity, knownSize: false, hideStale: false, noLimits: false, sort: "rank"});
 renderCards();
});
byId("save-budget").addEventListener("click", () => {
 const val = Number(byId("budget").value);
 if (!Number.isFinite(val) || val <= 0) { notify("Enter a valid positive budget."); return; }
 state.budget = val; safeWrite(STORAGE.budget, val);
 renderLibrary(); notify("Storage budget updated.");
});
byId("build-library").addEventListener("click", buildLibrary);
byId("export").addEventListener("click", exportManifest);
byId("export-sh").addEventListener("click", exportScript);
byId("modal-close").addEventListener("click", closeModal);
byId("modal-backdrop").addEventListener("click", e => { if (e.target === byId("modal-backdrop")) closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
document.addEventListener("click", e => {
 const save = e.target.closest("[data-save]");
 if (save) { toggleSave(save.dataset.save); if (state.modalName) openDetails(state.modalName); return; }
 const variant = e.target.closest("[data-add-variant]");
 if (variant) { addVariant(variant.dataset.addVariant, Number(variant.dataset.vi)); if (state.modalName) openDetails(state.modalName); return; }
 const detail = e.target.closest("[data-detail]");
 if (detail) { openDetails(detail.dataset.detail); return; }
 const goto = e.target.closest("[data-goto]");
 if (goto) { switchView(goto.dataset.goto); return; }
 if (e.target.id === "empty-reset") byId("reset").click();
});

/* ---------- startup ---------- */

async function init() {
 byId("intent").value = "teach science to 12-year-olds";
 renderLibrary();
 try {
  const meta = await DiscoveryService.meta();
  state.meta = meta;
  byId("stat-total").textContent = Number(meta.resources).toLocaleString();
  byId("stat-total-note").textContent = "Resources indexed" + (meta.snapshot ? " · snapshot " + meta.snapshot : "");
  if (!meta.semantic) {
   ["hybrid", "semantic"].forEach(v => {
    const opt = byId("mode").querySelector(`option[value="${v}"]`);
    opt.disabled = true; opt.textContent = MODE_LABELS[v] + " (embeddings not built)";
   });
   state.mode = "intent";
  }
 } catch { state.mode = "intent"; }
 byId("mode").value = state.mode;
 runSearch();
}
init();
