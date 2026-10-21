"""Export a library manifest. python scripts/manifest.py "teach science to 12-year-olds" --budget 5
Writes my_library.json and download.sh (direct .zim URLs; use aria2c/curl, resumable)."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
ap = argparse.ArgumentParser(); ap.add_argument("query"); ap.add_argument("--budget", type=float, default=5); ap.add_argument("--out", default="my_library")
a = ap.parse_args(); lib = app.library(a.query, a.budget)
items = [{"title": i["title"], "name": i["name"], "flavour": i["chosen_variant"]["flavour"], "size_gb": i["chosen_variant"]["size_gb"],
          "why": i["why"], "url": i["chosen_variant"]["download_url"].removesuffix(".meta4")} for i in lib["items"]]
json.dump({"query": a.query, "budget_gb": a.budget, "used_gb": lib["used_gb"], "items": items}, open(a.out + ".json", "w"), indent=2, ensure_ascii=False)
open("download.sh", "w").write("#!/bin/sh\n" + "".join(f"curl -L -C - -O '{i['url']}'   # {i['title']} ({i['size_gb']} GB)\n" for i in items))
print(f"{len(items)} items, {lib['used_gb']} / {a.budget} GB -> {a.out}.json, download.sh")
