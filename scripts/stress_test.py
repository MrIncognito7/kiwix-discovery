"""Larger-catalogue test. python scripts/stress_test.py [copies=14]  (~50k rows)
Clones the real catalogue with new names/titles, then injects missing descriptions, sizes, categories and
exact-duplicate titles, rebuilds the FTS index and times search and library building."""
import os, random, sqlite3, statistics, sys, time
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
copies = int(sys.argv[1]) if len(sys.argv) > 1 else 14
src = sqlite3.connect(os.path.join(ROOT, "data", "catalog_enriched.db"))
base = pd.read_sql("SELECT * FROM resources_enriched", src); random.seed(1)
parts = []
for i in range(copies):
    d = base.copy(); d["name"] += f"_c{i}"; d["uuid"] += f"-{i}"
    if i % 2: d["title"] += f" part {i}"                     # half keep exact duplicate titles
    d.loc[d.sample(frac=.2, random_state=i).index, "description"] = ""      # 20% missing descriptions
    d.loc[d.sample(frac=.1, random_state=i + 50).index, ["size_bytes", "size_gb"]] = None   # 10% missing size
    d.loc[d.sample(frac=.05, random_state=i + 99).index, "category"] = ""
    parts.append(d)
big = pd.concat([base] + parts, ignore_index=True); path = "/tmp/stress_catalog.db"
if os.path.exists(path): os.remove(path)
con = sqlite3.connect(path); big.to_sql("resources_enriched", con, index=False)
con.execute("CREATE VIRTUAL TABLE resources_fts USING fts5(title, description, tags, category, content='')")
con.execute("INSERT INTO resources_fts(rowid,title,description,tags,category) SELECT rowid,title,description,tags,category FROM resources_enriched")
con.commit(); con.close(); print(f"built {len(big)} rows")
os.environ["KIWIX_DB"] = path; sys.path.insert(0, ROOT); import app
Qs = ["teach science to 12-year-olds", "learn French", "prepare for natural disasters", "medical resources under 2 GB", "programming for beginners"]
for label, fn in (("baseline", lambda q: app.baseline(q, 20)), ("intent", lambda q: app.intent(q, 20)), ("library(5GB)", lambda q: app.library(q, 5))):
    t = []
    for q in Qs:
        s = time.perf_counter(); r = fn(q); t.append((time.perf_counter() - s) * 1000)
    print(f"{label:13s} median {statistics.median(t):7.0f} ms   max {max(t):7.0f} ms")
res = app.intent("teach science to 12-year-olds", 20)[0]
print("top intent results on big catalogue:", [r["title"][:25] for r in res[:5]])
print("results with missing-metadata limitation notes:", sum(any("limitation" in w for w in r["why"]) for r in res), "of", len(res))
