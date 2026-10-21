"""Duplicate detection. python scripts/find_duplicates.py  -> data/duplicates.csv
 - variants: same `name`, different flavour (a size choice, NOT a duplicate)
 - possible duplicates: same normalised title + primary language under different `name`s"""
import os, re, sqlite3, sys
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
df = pd.read_sql("SELECT name,title,primary_lang,flavour,size_gb,updated FROM resources_enriched",
                 sqlite3.connect(os.path.join(ROOT, "data", "catalog_enriched.db")))
df["key"] = df.title.str.lower().str.replace(r"[^\w ]", "", regex=True).str.strip() + "|" + df.primary_lang
g = df.groupby("key").filter(lambda x: x["name"].nunique() > 1).sort_values(["key", "name"])
g.to_csv(os.path.join(ROOT, "data", "duplicates.csv"), index=False)
print(f"{df.name.nunique()} distinct names, {len(df)} rows; {len(df) - df.name.nunique()} extra rows are size variants")
print(f"{g.key.nunique()} title+language groups appear under several names ({len(g)} rows) -> data/duplicates.csv")
print(g.head(8).to_string(index=False))
