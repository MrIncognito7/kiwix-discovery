#!/usr/bin/env python3
"""Add derived fields to catalog.db -> table `resources_enriched`.

Every inferred field has a sibling `*_source` column ('catalog' | 'inferred' | 'unknown')
so the UI can say *why* a result matched and what is a guess.

Usage: python enrich_catalog.py catalog.db
"""
import re
import sqlite3
import sys
import pandas as pd

# --- Hand-written mappings (edit these; they are your "domain knowledge") -----
# folder/category -> (subject, content_type, education_level)
FAMILY = {
    "wikipedia":     ("general-reference", "encyclopedia", "general"),
    "wikibooks":     ("textbooks",         "books",        "secondary-college"),
    "wiktionary":    ("language",          "dictionary",   "general"),
    "wikiquote":     ("humanities",        "quotes",       "general"),
    "wikisource":    ("literature",        "books",        "general"),
    "wikivoyage":    ("travel-geography",  "guide",        "general"),
    "wikiversity":   ("education",         "courses",      "secondary-college"),
    "vikidia":       ("general-reference", "encyclopedia", "children-8-13"),
    "gutenberg":     ("literature",        "books",        "general"),
    "ted":           ("talks",             "video",        "general"),
    "phet":          ("science-math",      "simulations",  "primary-secondary"),
    "libretexts":    ("science-math",      "textbooks",    "college"),
    "stack_exchange":("q-and-a",           "q&a",          "adult"),
    "devdocs":       ("programming",       "documentation","adult"),
    "freecodecamp":  ("programming",       "courses",      "adult"),
    "ifixit":        ("repair-diy",        "how-to",       "adult"),
    "mooc":          ("education",         "courses",      "college"),
    "maps":          ("travel-geography",  "maps",         "general"),
    "videos":        ("various",           "video",        "general"),
    "psiram":        ("science-skepticism","articles",      "adult"),
    "zimit":         ("various",           "website",      "unknown"),
    "other":         ("various",           "website",      "unknown"),
}
# keyword -> subject override (checked on title+name+tags+description)
SUBJECT_KEYWORDS = [
    (r"physics|chemistry|biology|science|math|calculus|algebra|geometry|capacitor|conic|sorcier", "science-math"),
    (r"medic|health|first.?aid|disease|hospital|nurs|wikem|hesperian", "health-medicine"),
    (r"disaster|prepper|survival|emergency|water purif|shelter|earthquake|flood", "preparedness"),
    (r"grammar|vocab|dictionary|wiktionary|learn (french|spanish|german)", "language"),
    (r"history|geograph", "humanities"),
    (r"python|javascript|html|css|programming|developer|devdocs|linux|sql", "programming"),
    (r"farm|agricultur|crop|garden", "agriculture"),
]


def infer_subject(row):
    blob = " ".join([row.title, row["name"], row.tags]).lower()  # not description: it says "...in Greek Language" for every Wikivoyage
    for pat, subj in SUBJECT_KEYWORDS:
        if re.search(pat, blob):
            return subj, "inferred"
    fam = FAMILY.get(row.family)
    return (fam[0], "inferred") if fam else ("unknown", "unknown")


def main(db):
    con = sqlite3.connect(db)
    df = pd.read_sql("SELECT * FROM resources", con)

    # 1. Recover category from the download-URL folder (fixes ~24% missing categories)
    df["folder"] = df.download_url.str.extract(r"/zim/([^/]+)/")[0].fillna("")
    df["family"] = df.category.where(df.category != "", df.folder).str.lower()
    df["category_source"] = ["catalog" if c else ("inferred" if f else "unknown")
                             for c, f in zip(df.category, df.folder)]

    # 2. Languages: primary + full list
    df["languages"] = df.language.str.split(",")
    df["primary_lang"] = df.languages.str[0]
    df["is_multilingual"] = (df.languages.str.len() > 1).astype(int)

    # 3. Size
    df["size_gb"] = df.size_bytes / 1e9
    df["size_mb"] = df.size_bytes / 1e6

    # 4. Freshness (the catalogue is nearly all 2026, so use a relative cut-off)
    df["updated_dt"] = pd.to_datetime(df.updated, errors="coerce", utc=True)
    newest = df.updated_dt.max()
    df["age_days"] = (newest - df.updated_dt).dt.days
    df["is_stale"] = (df.age_days > 365).astype(int)

    # 5. Variants: same `name` with different flavours is NOT a duplicate; it's a size choice.
    df["variant_count"] = df.groupby("name")["uuid"].transform("count")
    df["is_smallest_variant"] = (df.size_bytes == df.groupby("name").size_bytes.transform("min")).astype(int)
    df["is_largest_variant"] = (df.size_bytes == df.groupby("name").size_bytes.transform("max")).astype(int)
    # Real near-duplicates: same title + language + flavour but a different `name`
    df["dup_key"] = (df.title.str.lower().str.strip() + "|" + df.primary_lang + "|" + df.flavour)
    df["is_possible_duplicate"] = df.duplicated("dup_key", keep=False).astype(int)

    # 6. Subject / content type / education level
    subj = df.apply(infer_subject, axis=1, result_type="expand")
    df["subject"], df["subject_source"] = subj[0], subj[1]
    df["content_type"] = df.family.map(lambda f: FAMILY.get(f, (0, "unknown", 0))[1])
    df["education_level"] = df.family.map(lambda f: FAMILY.get(f, (0, 0, "unknown"))[2])
    df["education_source"] = df.education_level.map(lambda v: "unknown" if v == "unknown" else "inferred")

    # 7. Popularity PROXY (no download stats in the catalogue): log article count
    import numpy as np
    df["popularity_proxy"] = np.log1p(df.article_count.fillna(0))
    df["popularity_source"] = "proxy:article_count"

    out = df.drop(columns=["languages", "updated_dt"])
    out.to_sql("resources_enriched", con, if_exists="replace", index=False)
    con.commit()

    print(f"Wrote {len(out)} rows to resources_enriched")
    print("\nSubject:\n", out.subject.value_counts().head(12).to_string())
    print("\nEducation level:\n", out.education_level.value_counts().to_string())
    print("\nCategory source:\n", out.category_source.value_counts().to_string())
    print("\nStale:", int(out.is_stale.sum()), "| possible dupes:", int(out.is_possible_duplicate.sum()),
          "| multilingual:", int(out.is_multilingual.sum()))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
