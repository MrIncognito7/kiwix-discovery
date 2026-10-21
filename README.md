# Kiwix Discovery: find knowledge by intent, not by filename

Offline, intent-based recommender for Kiwix ZIM resources (FOSS Forge 2.0, Track 02). You describe a goal
("teach science to 12-year-olds", "learn French", "prepare for disasters", "5 GB of medical material") and it
recommends resources from a local snapshot of the Kiwix catalogue, explains each recommendation, and can build a
storage-aware "My Library". No cloud API is used at runtime.

## Project layout
```
app.py                  backend: query parser, baseline BM25, intent ranker, MiniLM semantic ranking, library builder, API
embedder.py             loads the MiniLM model (offline copy in data/model_* after first build)
static/index.html       frontend
data/catalog_enriched.db  catalogue snapshot (SQLite): resources, resources_fts, resources_enriched
scripts/ingest_catalog.py   OPDS XML -> SQLite + metadata audit flags
scripts/enrich_catalog.py   derived fields (subject, audience, freshness, variants), each marked inferred/catalog
scripts/build_embeddings.py  encode the catalogue with MiniLM -> data/embeddings.npy
scripts/find_duplicates.py  duplicate detection -> data/duplicates.csv
scripts/manifest.py         export a library manifest (JSON + download.sh)
scripts/stress_test.py      larger-catalogue test (~55k rows) with injected missing metadata
eval/queries_labels.json    25 test queries with relevance judgments
eval/run_eval.py            baseline vs intent comparison -> eval/results.md
tests/test_core.py          unit tests (pytest)
```

## Run
```
pip install fastapi uvicorn pytest pandas lxml
uvicorn app:app --reload          # open http://localhost:8000
python -m pytest -q tests         # unit tests
python eval/run_eval.py --show    # evaluation (add --show to print each method's top results)
python scripts/stress_test.py     # large catalogue test
python scripts/manifest.py "teach science to 12-year-olds" --budget 5
```
Refresh the data: `curl --compressed 'https://opds.library.kiwix.org/catalog/v2/entries?count=-1' -o catalog.xml`,
then `python scripts/ingest_catalog.py catalog.xml catalog.db` and `python scripts/enrich_catalog.py catalog.db`;
copy the result to `data/catalog_enriched.db`.

## Method
1. **Data.** The OPDS catalogue (3,657 entries) is loaded into SQLite. Audit flags record missing descriptions, sizes,
   categories and duplicates. Missing categories are recovered from the download-URL folder. Resources that share a
   `name` but differ in `flavour` (maxi/nopic/mini) are treated as **size variants, not duplicates**.
2. **Baseline.** Plain BM25 (SQLite FTS5; title weighted above tags above category above description) on the raw query.
   No parsing, no filters.
3. **Intent ranker.** The query is parsed with dictionaries into subject, audience (from age or words like "kids"),
   language and size limit. BM25 candidates plus subject/language candidates are filtered (language, size) and scored:
   text relevance + subject match + audience fit + popularity proxy (log article count) - staleness - audience mismatch.
   Translations of the same project are collapsed (English preferred) unless a language was requested.
4. **Explanations.** Every result lists the signals that fired and states limitations when metadata is missing,
   inferred, stale or contradicts the request.
5. **Build My Library.** Relevance-first greedy selection: take the best item that fits, use its largest variant under
   a 40% per-item cap, discount subjects already chosen (diversity), one entry per title.

## Evidence
Relevance judgments were written from reading the catalogue (`eval/queries_labels.json`), then both methods were run
on the same 25 queries (k=10). Full per-query table: `eval/results.md`.

| Method | P@10 | Recall@10 | nDCG@10 | MRR |
|---|---|---|---|---|
| baseline | 0.232 | 0.427 | 0.405 | 0.568 |
| intent | 0.296 | 0.472 | 0.537 | 0.805 |

nDCG per query: intent better on 18, tied on 4, worse on 3.

### Larger catalogue (`scripts/stress_test.py`)
```
built 54855 rows
baseline      median     191 ms   max     192 ms
intent        median     286 ms   max     344 ms
library(5GB)  median    1056 ms   max    1238 ms
top intent results on big catalogue: ['PhET Interactive Simulati', 'PhET Interactive Simulati', 'PhET Interactive Simulati', 'PhET Interactive Simulati', 'PhET Interactive Simulati']
results with missing-metadata limitation notes: 2 of 20
```

## Semantic ranking with a multilingual MiniLM (machine learning)
`paraphrase-multilingual-MiniLM-L12-v2` is a small pre-trained sentence-embedding model (118M parameters, 384
dimensions, 50+ languages, runs on CPU). Each resource (title + description + tags + category) and each query is turned
into a vector; resources closest to the query by cosine similarity are semantically similar, even without shared
words and across languages (an English query can match a Hindi title, and the reverse). Nothing is trained or
fine-tuned here; the model is used as published.

```
pip install -r requirements.txt
python scripts/build_embeddings.py     # one-time, needs internet: downloads the model (~470 MB), embeds 3,657 entries
uvicorn app:app --reload               # page now offers "Hybrid (rules + MiniLM)" and "Semantic only (MiniLM)"
python eval/run_eval.py                # compares four methods and rewrites eval/results.md
```
Modes: **baseline** (BM25), **intent** (rules + BM25, no ML), **semantic** (MiniLM nearest neighbours only) and
**hybrid** (intent + MiniLM similarity as an extra scoring signal, with a "semantically similar" explanation).
After the first build the model is saved under `data/model_*`, so runtime needs no internet and no cloud API.
Embeddings record which model made them; if the model setting changes, the app disables semantic modes and asks you to
rebuild. Without embeddings the app still works; semantic modes say embeddings are missing.

**What is ML and what is rules:** the sentence embeddings and similarity are ML (pre-trained model). The query parser,
subject/audience inference, filters, scoring weights and library builder are hand-written rules and heuristics.
To compare against the smaller English-only model: `KIWIX_MODEL=sentence-transformers/all-MiniLM-L6-v2`, rebuild, re-run eval.

> **Results above were produced before MiniLM was added.** Run `python eval/run_eval.py` after building embeddings and
> use the new table in your write-up. Report it as measured, including if hybrid does not beat intent.

## Known limitations (read before trusting the numbers)
- **Labels are one person's judgment** of 25 queries, written as name patterns. They are noisy and the set is small;
  edit them and re-run. Some patterns are strict (e.g. "learn Hindi" excludes Hindi-language science courses).
- **Some tuning used a few of the same queries** (science for 12-year-olds, learn French, disasters), so the
  improvement is likely overstated. Add held-out queries before drawing conclusions.
- **Subject, audience and content type are inferred** from folder names and keyword rules, not catalogue fields.
  They are marked `inferred`, ~300 resources have no audience at all, and ranking uses them anyway.
- **No popularity or download data** exists in the catalogue; article count is a rough proxy.
- `has_videos` / `has_pictures` tags look unreliable (e.g. every Gutenberg entry says videos) and are not used.
- Intent ranking is weaker than the baseline on some queries (grammar, dictionaries, school math): the parser has no
  idea what e.g. "dictionary" means beyond the keyword, and audience words such as "school" are not matched to
  resources like `madrasa_ar`.
- Size filters apply to the specific variant row that scored best; a smaller variant of a resource may exist.
- The library builder is a heuristic, not an optimal knapsack, and takes about a second on 55k rows.
- The rule-based parser still knows only 12 language names and English keywords; only the MiniLM signal understands other languages.
- MiniLM weight (0.7) and its 0.25 similarity floor are hand-picked, not tuned. This model was trained for paraphrase similarity, not question-to-document search, so its similarity scale may need a different floor.
- Catalogue snapshot date: see the `updated` column; re-ingest to refresh.

## Stretch goals status
Duplicate detection (`find_duplicates.py`, size variants vs possible duplicates): done. Exportable manifest
(`manifest.py` and the page's export button): done. Diversity: simple subject discount. Multilingual search: partial
(language filter, no cross-language query matching).
