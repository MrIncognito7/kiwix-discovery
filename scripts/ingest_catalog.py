#!/usr/bin/env python3
"""Parse a Kiwix OPDS catalog.xml into a clean SQLite table with metadata-quality flags.

Usage:  python ingest_catalog.py catalog.xml catalog.db
"""
import re
import sqlite3
import sys
from collections import defaultdict
from lxml import etree


def local(tag):
    """Strip the XML namespace from a tag name."""
    return etree.QName(tag).localname


def text_of(entry, name):
    for child in entry:
        if isinstance(child.tag, str) and local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def nested_name(entry, parent):
    """<author><name>X</name></author> -> X"""
    for child in entry:
        if isinstance(child.tag, str) and local(child.tag) == parent:
            for sub in child:
                if isinstance(sub.tag, str) and local(sub.tag) == "name":
                    return (sub.text or "").strip()
    return ""


def parse_entry(e):
    # size + download link live on the acquisition <link>
    size, url = None, ""
    for child in e:
        if isinstance(child.tag, str) and local(child.tag) == "link":
            if "acquisition" in (child.get("rel") or ""):
                if child.get("length"):
                    size = int(child.get("length"))
                url = child.get("href", "")

    tags_raw = text_of(e, "tags")
    tags = [t for t in tags_raw.split(";") if t]
    # Kiwix uses "_key:value" tags for structured info (e.g. _pictures:yes)
    flags = {t[1:].split(":")[0]: t.split(":", 1)[1] for t in tags if t.startswith("_") and ":" in t}
    plain_tags = [t for t in tags if not t.startswith("_")]

    return {
        "uuid": text_of(e, "id").replace("urn:uuid:", ""),
        "title": text_of(e, "title"),
        "description": text_of(e, "summary") or text_of(e, "content"),
        "language": text_of(e, "language"),
        "name": text_of(e, "name"),            # e.g. wikipedia_en_all
        "flavour": text_of(e, "flavour"),      # maxi / mini / nopic
        "category": text_of(e, "category") or flags.get("category", ""),
        "tags": ";".join(plain_tags),
        "has_pictures": flags.get("pictures", ""),
        "has_videos": flags.get("videos", ""),
        "publisher": nested_name(e, "publisher"),
        "author": nested_name(e, "author"),
        "updated": text_of(e, "updated"),
        "article_count": int(text_of(e, "articleCount") or 0) or None,
        "media_count": int(text_of(e, "mediaCount") or 0) or None,
        "size_bytes": size,
        "download_url": url,
    }


def main(xml_path, db_path):
    tree = etree.parse(xml_path)
    entries = [el for el in tree.getroot() if isinstance(el.tag, str) and local(el.tag) == "entry"]
    rows = [parse_entry(e) for e in entries]
    print(f"Parsed {len(rows)} entries")

    # --- Audit flags -------------------------------------------------------
    by_name = defaultdict(list)
    for r in rows:
        by_name[r["name"]].append(r)

    for r in rows:
        r["missing_description"] = int(len(r["description"]) < 10)
        r["missing_size"] = int(r["size_bytes"] is None)
        r["missing_language"] = int(not r["language"])
        r["missing_updated"] = int(not r["updated"])
        r["missing_category"] = int(not r["category"])
        # same `name` appearing several times (different dates/flavours)
        group = by_name[r["name"]]
        r["is_duplicate_name"] = int(bool(r["name"]) and len(group) > 1)
        latest = max(group, key=lambda x: x["updated"]) if group else r
        r["is_latest_version"] = int(r is latest)
        r["lang_count"] = len([l for l in r["language"].split(",") if l])

    # --- Write to SQLite ---------------------------------------------------
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS resources")
    cols = list(rows[0].keys())
    con.execute(f"CREATE TABLE resources ({', '.join(cols)})")
    con.executemany(
        f"INSERT INTO resources VALUES ({','.join('?' * len(cols))})",
        [tuple(r[c] for c in cols) for r in rows],
    )
    # Full-text index for the BM25 baseline (SQLite FTS5)
    con.execute("DROP TABLE IF EXISTS resources_fts")
    con.execute("CREATE VIRTUAL TABLE resources_fts USING fts5(title, description, tags, category, content='')")
    con.execute(
        "INSERT INTO resources_fts(rowid, title, description, tags, category) "
        "SELECT rowid, title, description, tags, category FROM resources"
    )
    con.commit()

    # --- Quick report ------------------------------------------------------
    n = len(rows)
    print("\nMetadata quality report")
    for flag in ["missing_description", "missing_size", "missing_language",
                 "missing_updated", "missing_category", "is_duplicate_name"]:
        c = sum(r[flag] for r in rows)
        print(f"  {flag:22s} {c:6d}  ({100 * c / n:.1f}%)")
    print("\nTop categories:", sorted(
        ((sum(1 for r in rows if r['category'] == c), c) for c in {r['category'] for r in rows}),
        reverse=True)[:8])
    con.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
