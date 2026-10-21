"""Kiwix Discovery backend. Run:  uvicorn app:app --reload   then open http://localhost:8000"""
import json, math, os, re, sqlite3, sys
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("KIWIX_DB", os.path.join(HERE, "data", "catalog_enriched.db"))
sys.path.insert(0, HERE)
app = FastAPI()
# Lets the page be opened from another origin or from a file (e.g. main.html?api=http://localhost:8000). Read-only API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])

STOP = set("a an the for to of in on and or my me i want need with about from by is are be can please how what".split())
GENERIC = set("teach teaching learn learning resources resource build library best good kids children student students year years olds old".split())
SUBJECTS = {  # subject -> trigger words  (edit freely)
    "science-math": "science physics chemistry biology math maths mathematics algebra geometry calculus".split(),
    "health-medicine": "health medical medicine doctor disease nursing".split() + ["first aid"],
    "preparedness": "disaster disasters emergency survival earthquake flood prepper preparing".split(),
    "programming": "programming coding python javascript developer".split(),
    "language": "dictionary vocabulary grammar".split(),
    "agriculture": "farming agriculture crops gardening".split(),
    "literature": "books novels literature stories".split(),
}
LANGS = {"english": "eng", "french": "fra", "spanish": "spa", "german": "deu", "hindi": "hin", "arabic": "ara",
         "portuguese": "por", "russian": "rus", "chinese": "zho", "italian": "ita", "bengali": "ben", "tamil": "tam"}


def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def words(s): return re.findall(r"[a-z0-9]+", s.lower())


SEM = None  # (rowids, matrix, embedder) once embeddings are loaded


def load_semantic(emb_dir=None):
    """Load MiniLM embeddings built by scripts/build_embeddings.py. Returns False (semantic off) if unavailable."""
    global SEM
    d = emb_dir or os.environ.get("KIWIX_EMB_DIR") or os.path.join(HERE, "data")
    try:
        if not os.path.exists(os.path.join(d, "embeddings.npy")): SEM = None; return False
        from embedder import MODEL_NAME, get_embedder
        mf = os.path.join(d, "embeddings_model.txt"); built = open(mf).read().strip() if os.path.exists(mf) else "unknown"
        expected = "stub" if os.environ.get("KIWIX_FAKE_EMBED") else MODEL_NAME
        if built != expected:
            print(f"semantic ranking disabled: embeddings were built with '{built}' but the app uses '{expected}'. Re-run scripts/build_embeddings.py")
            SEM = None; return False
        SEM = (np.load(os.path.join(d, "embedding_rowids.npy")), np.load(os.path.join(d, "embeddings.npy")), get_embedder()); return True
    except Exception as e:
        print("semantic ranking disabled:", e); SEM = None; return False


def sem_scores(q, top=300):
    """rowid -> cosine similarity between the query and each resource (top N)."""
    if SEM is None: return {}
    ids, M, emb = SEM
    sims = M @ np.asarray(emb.encode([q], normalize_embeddings=True))[0]
    return {int(ids[i]): float(sims[i]) for i in np.argsort(-sims)[:top]}


def parse(q):
    """Turn a sentence into structured intent + leftover keywords."""
    ql = q.lower(); it = {"subject": None, "levels": set(), "lang": None, "max_gb": None, "age": None}
    m = re.search(r"(\d+(?:\.\d+)?)\s*(gb|mb)\b", ql)
    if m:
        it["max_gb"] = float(m.group(1)) / (1 if m.group(2) == "gb" else 1000); ql = ql.replace(m.group(0), " ")
    m = re.search(r"(\d+)[- ]?(?:year|yr)", ql)
    if m:
        a = it["age"] = int(m.group(1)); ql = ql.replace(m.group(0), " ")
        it["levels"] = {"children-8-13"} if a <= 7 else {"children-8-13", "primary-secondary"} if a <= 13 else \
            {"primary-secondary", "secondary-college"} if a <= 17 else {"secondary-college", "college", "adult"}
    if re.search(r"\b(kids?|children|school)\b", ql): it["levels"] |= {"children-8-13", "primary-secondary"}
    if re.search(r"\b(university|college)\b", ql): it["levels"] |= {"college", "secondary-college"}
    for name, code in LANGS.items():
        if re.search(rf"\b{name}\b", ql): it["lang"] = code; ql = re.sub(rf"\b{name}\b", " ", ql)
    for subj, trig in SUBJECTS.items():
        if any(re.search(rf"\b{t}\b", ql) for t in trig): it["subject"] = subj; break
    if it["lang"] and re.search(r"\b(learn|learning|speak|study)\b", q.lower()) and not it["subject"]:
        it["subject"] = "language"
    it["tokens"] = [w for w in words(ql) if w not in STOP and w not in GENERIC]
    return it


def fts_scores(c, toks):
    if not toks: return {}
    sql = ("SELECT resources_fts.rowid rid, bm25(resources_fts,10,1,3,2) b FROM resources_fts "
           "WHERE resources_fts MATCH ? ORDER BY b LIMIT 300")
    return {r["rid"]: -r["b"] for r in c.execute(sql, (" OR ".join(toks),))}


def card(r, score, why):
    return {"name": r["name"], "title": r["title"], "description": (r["description"] or "")[:220],
            "language": r["language"], "subject": r["subject"], "education_level": r["education_level"],
            "size_gb": round(r["size_gb"], 3) if r["size_gb"] is not None else None,
            "score": round(score, 3), "why": why, "download_url": r["download_url"], "updated": r["updated"][:10]}


def add_variants(c, results):
    for res in results:
        res["variants"] = [{"flavour": v["flavour"], "size_gb": round(v["size_gb"], 3) if v["size_gb"] is not None else None,
                            "download_url": v["download_url"]}
                           for v in c.execute("SELECT * FROM resources_enriched WHERE name=? ORDER BY size_gb", (res["name"],))]
    return results


def baseline(q, n=20):
    """Plain keyword BM25 on the raw query. No parsing, no filters, no explanations."""
    c = db(); sc = fts_scores(c, [w for w in words(q) if w not in STOP])
    out, seen = [], set()
    for rid, s in sorted(sc.items(), key=lambda x: -x[1]):
        r = c.execute("SELECT * FROM resources_enriched WHERE rowid=?", (rid,)).fetchone()
        if r["name"] in seen: continue
        seen.add(r["name"]); out.append(card(r, s, ["keyword match (BM25)"]))
        if len(out) == n: break
    return add_variants(c, out)


def intent(q, n=20, semantic=False):
    c = db(); it = parse(q); sc = fts_scores(c, it["tokens"]); mx = max(sc.values(), default=1) or 1
    sem = sem_scores(q) if semantic else {}; smax = max(sem.values(), default=0)
    ids = list(set(sc) | set(sem))
    cond, par = [f"rowid IN ({','.join('?'*len(ids)) or 'NULL'})"], list(ids)
    if it["subject"]: cond.append("subject=?"); par.append(it["subject"])
    if it["lang"]: cond.append("language LIKE ?"); par.append(f"%{it['lang']}%")
    rows = c.execute("SELECT rowid rid, * FROM resources_enriched WHERE " + " OR ".join(cond), par).fetchall()
    maxpop = max([r["popularity_proxy"] or 0 for r in rows], default=1) or 1
    best = {}
    for r in rows:
        if it["lang"] and it["lang"] not in (r["language"] or "").split(","): continue
        if it["max_gb"] and r["size_gb"] and r["size_gb"] > it["max_gb"]: continue
        s, why = 0.0, []
        t = sc.get(r["rid"], 0) / mx
        if t: s += 0.7 * t; why.append(f"matches your keywords ({t:.2f})")
        if sem and r["rid"] in sem and smax > 0.25:   # MiniLM similarity above a 0.25 floor, scaled to the best match
            sv = max(0.0, (sem[r["rid"]] - 0.25) / (smax - 0.25))
            if sv > 0: s += 0.7 * sv; why.append(f"semantically similar to your request ({sem[r['rid']]:.2f})")
        if it["subject"]:
            if r["subject"] == it["subject"]:
                s += 0.6; why.append(f"subject '{r['subject']}'" + (" (inferred from category/keywords)" if r["subject_source"] == "inferred" else ""))
            elif r["subject"] == "unknown": why.append("limitation: subject unknown")
        if it["levels"]:
            if r["education_level"] in it["levels"]: s += 0.8; why.append(f"suited to {r['education_level']} (inferred)")
            elif r["education_level"] == "general": why.append("general-audience resource")
            elif r["education_level"] == "unknown": why.append("limitation: no education level in metadata, audience fit unchecked")
            else: s -= 0.3; why.append(f"limitation: aimed at {r['education_level']} audiences, not the one requested")
        s += 0.2 * (r["popularity_proxy"] or 0) / maxpop
        if r["is_stale"]: s -= 0.05; why.append("limitation: not updated recently")
        if r["size_gb"] is None: why.append("limitation: size missing")
        if it["lang"]: why.append(f"language '{it['lang']}' available")
        if s <= 0: continue
        key = r["name"]
        if not it["lang"]:  # same project in many languages -> keep one, prefer English
            key = re.sub(r"_[a-z]{2,3}(?:-[a-z]+)?_", "_*_", r["name"], count=1)
            if "eng" in (r["language"] or "").split(","): s += 0.05
        if key not in best or s > best[key][0]:
            best[key] = (s, card(r, s, why))
    out = [v[1] for v in sorted(best.values(), key=lambda x: -x[0])[:n]]
    return add_variants(c, out), it


def library(q, budget_gb, semantic=False):
    """Relevance-first greedy: pick the best item that fits, take its largest variant under a per-item cap,
    and discount subjects already chosen (diversity)."""
    items = [i for i in intent(q, 100, semantic)[0] if i["score"] >= 0.3]
    left, chosen, seen, titles = budget_gb, [], {}, set()
    while items:
        pick = None
        for i in items:
            if i["title"] in titles: continue
            fits = [v for v in i["variants"] if v["size_gb"] is not None and v["size_gb"] <= min(left, budget_gb * 0.4)]
            if not fits: continue
            adj = i["score"] * 0.7 ** seen.get(i["subject"], 0)
            if not pick or adj > pick[0]: pick = (adj, i, max(fits, key=lambda v: v["size_gb"]))
        if not pick: break
        _, i, v = pick; items.remove(i); titles.add(i["title"]); left -= v["size_gb"]; seen[i["subject"]] = seen.get(i["subject"], 0) + 1
        chosen.append({**i, "chosen_variant": v})
    return {"items": chosen, "used_gb": round(budget_gb - left, 2), "left_gb": round(left, 2), "budget_gb": budget_gb}


def semantic_only(q, n=20):
    """Pure MiniLM nearest neighbours (no rules, no filters), one entry per resource name."""
    c = db(); out, seen = [], set()
    for rid, sv in sorted(sem_scores(q, 150).items(), key=lambda x: -x[1]):
        r = c.execute("SELECT * FROM resources_enriched WHERE rowid=?", (rid,)).fetchone()
        if r["name"] in seen: continue
        seen.add(r["name"]); out.append(card(r, sv, [f"semantic similarity {sv:.2f} (MiniLM)"]))
        if len(out) == n: break
    return add_variants(c, out)


@app.get("/api/search")
def search(q: str, mode: str = "intent", n: int = 20):
    if mode == "baseline": return {"results": baseline(q, n)}
    if mode in ("semantic", "hybrid") and SEM is None:
        return {"results": [], "error": "Embeddings not built. Run: python scripts/build_embeddings.py"}
    if mode == "semantic": return {"results": semantic_only(q, n)}
    res, it = intent(q, n, semantic=(mode == "hybrid"))
    return {"results": res, "parsed": {k: (sorted(v) if isinstance(v, set) else v) for k, v in it.items()}}

@app.get("/api/library")
def lib(q: str, budget_gb: float = 5):
    return library(q, budget_gb, semantic=SEM is not None)


@app.get("/api/meta")
def meta():
    """Catalogue size, snapshot date and whether the MiniLM modes are available (used by the page header and mode picker)."""
    c = db(); names, rows, snap = c.execute("SELECT COUNT(DISTINCT name), COUNT(*), MAX(updated) FROM resources_enriched").fetchone()
    return {"resources": names, "rows": rows, "snapshot": (snap or "")[:10], "semantic": SEM is not None}

@app.get("/api/eval")
def eval_report():
    """Offline evaluation report written by `python eval/run_eval.py` (eval/results.json). Nothing is computed at request time."""
    p = os.path.join(HERE, "eval", "results.json")
    if not os.path.exists(p): return {"error": "No evaluation report yet. Run: python eval/run_eval.py"}
    return json.load(open(p, encoding="utf-8"))

load_semantic()
app.mount("/", StaticFiles(directory=os.path.join(HERE, "static"), html=True), name="static")
