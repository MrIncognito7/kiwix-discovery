"""Compare ranking methods.   python eval/run_eval.py [--show]
Methods: baseline (BM25), intent (rules + BM25) and, if embeddings are built, semantic (MiniLM only) and
hybrid (rules + BM25 + MiniLM). Metrics @10: Precision, Recall, nDCG (binary), MRR. Writes eval/results.md and eval/results.json (the page's Evaluation tab reads the JSON)."""
import datetime, json, math, os, re, sqlite3, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import app

Q = json.load(open(os.path.join(ROOT, "eval", "queries_labels.json")))["queries"]
c = sqlite3.connect(app.DB); c.row_factory = sqlite3.Row
meta, hay = {}, {}
for r in c.execute("SELECT name,title,size_gb FROM resources_enriched"):
    hay[r["name"]] = (r["name"] + " " + r["title"]).lower()
    if r["size_gb"] is not None: meta[r["name"]] = min(meta.get(r["name"], 1e9), r["size_gb"])

def methods(q):
    m = [("baseline", app.baseline(q, 10)), ("intent", app.intent(q, 10)[0])]
    if app.SEM is not None: m += [("semantic", app.semantic_only(q, 10)), ("hybrid", app.intent(q, 10, True)[0])]
    return m

def metrics(hits, n_rel, k=10):
    p = sum(hits[:k]) / k; rec = sum(hits[:k]) / n_rel if n_rel else 0
    dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits[:k])); ideal = sum(1 / math.log2(i + 2) for i in range(min(n_rel, k)))
    return p, rec, (dcg / ideal if ideal else 0), next((1 / (i + 1) for i, h in enumerate(hits) if h), 0)

names = [m for m, _ in methods("test")]; tot = {m: [0] * 4 for m in names}; rows = []; used = 0
for item in Q:
    pat, mx = re.compile(item["pattern"]), item.get("max_gb")
    rel = {n for n, h in hay.items() if pat.search(h) and (mx is None or meta.get(n, 1e9) <= mx)}
    if not rel: print("SKIP (no relevant resources):", item["q"]); continue
    used += 1; out = {}
    for tag, res in methods(item["q"]):
        hits = [int(r["name"] in rel and (mx is None or (r["size_gb"] is not None and r["size_gb"] <= mx))) for r in res] + [0] * 10
        out[tag] = metrics(hits[:10], len(rel))
        for i in range(4): tot[tag][i] += out[tag][i]
        if "--show" in sys.argv: print(f"{item['q'][:38]:38s} {tag:9s} {[r['name'][:20] for r in res[:5]]}")
    rows.append((item["q"], len(rel), out))

L = ["# Evaluation", "", f"{used} queries with relevance judgments (`eval/queries_labels.json`), k=10.", "",
     "| Query | #rel | " + " | ".join(f"nDCG {m}" for m in names) + " |", "|---|---|" + "---|" * len(names)]
for q, n, o in rows: L.append(f"| {q} | {n} | " + " | ".join(f"{o[m][2]:.2f}" for m in names) + " |")
L += ["", "| Method | P@10 | Recall@10 | nDCG@10 | MRR |", "|---|---|---|---|---|"]
for m in names: a = [v / max(used, 1) for v in tot[m]]; L.append(f"| {m} | {a[0]:.3f} | {a[1]:.3f} | {a[2]:.3f} | {a[3]:.3f} |")
last = names[-1]; w = [0, 0, 0]
for _, _, o in rows: d = o[last][2] - o["baseline"][2]; w[0 if d > .001 else 2 if d < -.001 else 1] += 1
L += ["", f"nDCG, {last} vs baseline: better on {w[0]}, tied on {w[1]}, worse on {w[2]} queries."]
open(os.path.join(ROOT, "eval", "results.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L[-9:]))
report = {"generated": datetime.date.today().isoformat(), "k": 10, "queries": used, "methods": names,
          "semantic_enabled": app.SEM is not None, "judgments": "eval/queries_labels.json",
          "summary": {m: dict(zip(("p", "recall", "ndcg", "mrr"), (v / max(used, 1) for v in tot[m]))) for m in names},
          "per_query": [{"q": q, "n_rel": n, "ndcg": {m: o[m][2] for m in names}, "p": {m: o[m][0] for m in names}} for q, n, o in rows],
          "vs_baseline": {"method": last, "better": w[0], "tied": w[1], "worse": w[2]}}
json.dump(report, open(os.path.join(ROOT, "eval", "results.json"), "w", encoding="utf-8"), indent=1)
