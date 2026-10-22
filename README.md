# Kiwix Discovery

### Find knowledge by intent, not by filename.

Kiwix Discovery helps people find useful offline learning resources by describing **what they want to accomplish**, rather than searching only by title or filename.

For example:

- "Teach science to 12-year-olds"
- "Learn French"
- "Prepare for disasters"
- "Build a library of medical resources within 5 GB"

It searches a local snapshot of the Kiwix catalogue, ranks matching resources, explains recommendation signals, and helps build a storage-aware personal library.

> **Privacy by design:** search and ranking run locally. No cloud AI API is required at runtime. The first-time model download and catalogue setup require internet access if the files are not already available.

---

## Quick start

```bash
git clone https://github.com/MrIncognito7/kiwix-discovery.git
cd kiwix-discovery
python setup.py
```

Then activate the environment and start the server:

```bash
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
uvicorn app:app --reload
```

Open **http://127.0.0.1:8000**. If the port is occupied, add `--port 8001`.

`setup.py` creates a virtual environment, installs dependencies, downloads the public Kiwix catalogue, builds the local database and builds the semantic embeddings (so all four ranking modes work). The first run downloads a small model and can take a few minutes. It is safe to re-run: finished steps are skipped. To rebuild, delete `data/catalog_enriched.db` (catalogue) or `data/.embeddings_built` (embeddings) and run it again.

Requirements: Python 3.10+ and internet access for the first run.

<details>
<summary><strong>Manual setup (step by step)</strong></summary>

### 1. Create a virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Set up the catalogue data

**Option A: you already have the `data/` folder.** Copy it into the repository root and check that `data/catalog_enriched.db` exists. For semantic or hybrid ranking, the embedding files and model metadata must also be present and match the configured model. Do not commit the data folder unless you have checked file sizes and redistribution licences.

**Option B: build it from the public catalogue.**

```bash
mkdir -p data
curl --compressed "https://opds.library.kiwix.org/catalog/v2/entries?count=-1" -o catalog.xml
python scripts/ingest_catalog.py catalog.xml catalog.db
python scripts/enrich_catalog.py catalog.db
cp catalog.db data/catalog_enriched.db
rm -f catalog.xml catalog.db
```

On Windows, delete the temporary `catalog.xml` and `catalog.db` files with File Explorer or PowerShell. The downloaded catalogue is a snapshot and may not include the newest entries.

### 4. Optional: enable semantic and hybrid ranking

```bash
python scripts/build_embeddings.py
```

The first run may download the configured SentenceTransformer model and can take time depending on your connection and hardware. Model files and embeddings are stored locally under `data/`.

### 5. Start the app

```bash
uvicorn app:app --reload
```

Open http://127.0.0.1:8000. If the port is occupied, add `--port 8001`.

</details>

---

## Why this matters

Offline knowledge is valuable when internet access is slow, expensive, unreliable, or unavailable. But a large catalogue can be difficult to navigate when someone knows their learning goal but not the name of the resource they need.

Kiwix Discovery bridges that gap with intent-aware discovery and storage-aware planning.

## Features

- **Goal-oriented search:** describe a learning or information need in natural language.
- **Multiple ranking modes:** BM25 baseline, rule-based intent ranking, semantic ranking, and hybrid ranking when embeddings are available.
- **Recommendation explanations:** see which signals contributed to a result and where metadata is missing or inferred.
- **Storage-aware "My Library":** assemble a selection of resources under a storage budget.
- **Catalogue metadata auditing:** flag missing fields and possible duplicates.
- **Exportable library manifest:** generate a manifest and download script for a planned library.
- **Evaluation tools:** compare ranking approaches against a small set of manually labelled queries.

## How it works

1. **Catalogue ingestion:** import the public Kiwix OPDS catalogue into SQLite.
2. **Metadata enrichment:** derive helpful fields such as subject, audience, freshness, and resource variants. Derived fields are heuristic and should not be mistaken for authoritative catalogue metadata.
3. **Candidate retrieval:** use SQLite FTS5/BM25 and relevant catalogue candidates.
4. **Intent ranking:** infer signals such as subject, audience, language, and size limit, then score and filter candidates.
5. **Optional semantic ranking:** encode resource text and queries with a multilingual SentenceTransformer model and compare their embeddings.
6. **Library planning:** select relevant resources while considering storage limits and subject diversity.

### Ranking modes

| Mode       | What it does                                                  |
|------------|---------------------------------------------------------------|
| `baseline` | BM25 text search using SQLite FTS5                            |
| `intent`   | BM25 plus rule-based intent signals and filters               |
| `semantic` | Nearest-neighbour ranking using precomputed MiniLM embeddings |
| `hybrid`   | Combines intent ranking with a semantic similarity signal     |

Semantic and hybrid modes require embeddings built with the configured model. Without embeddings, the application can still use its non-semantic modes.

## Project structure

```
kiwix-discovery/
├── setup.py                  # One-command setup
├── app.py                    # FastAPI app and search/library endpoints
├── embedder.py               # SentenceTransformer model loading
├── requirements.txt          # Python dependencies
├── static/
│   └── index.html            # Frontend
├── scripts/
│   ├── ingest_catalog.py     # OPDS XML -> SQLite
│   ├── enrich_catalog.py     # Derived metadata and audit fields
│   ├── build_embeddings.py   # Build semantic embeddings
│   ├── find_duplicates.py    # Duplicate/variant analysis
│   ├── manifest.py           # Export a library manifest
│   └── stress_test.py        # Larger-catalogue stress test
├── eval/
│   ├── queries_labels.json   # Manually labelled evaluation queries
│   └── run_eval.py           # Compare ranking methods
├── tests/
│   └── test_core.py          # Unit tests
└── data/                     # Local/generated files; not committed
```

The `data/` directory is intentionally excluded from Git because it can contain the local catalogue database, generated embeddings, and downloaded model files.

---

## Tests and evaluation

Run the unit tests:

```bash
python -m pytest -q tests
```

Run the ranking evaluation:

```bash
python eval/run_eval.py
```

To print per-query result details, if supported by the current script:

```bash
python eval/run_eval.py --show
```

Run the larger-catalogue stress test:

```bash
python scripts/stress_test.py
```

Export a sample library manifest:

```bash
python scripts/manifest.py "teach science to 12-year-olds" --budget 5
```

Check `--help` for the supported options if a command differs in your local version.

### Evaluation results currently documented

Full details are in [`eval/results.md`](eval/results.md), if present in your checkout.

## Limitations

- Evaluation labels are small and manually authored; more independent, held-out queries are needed.
- Subject and audience values can be inferred from folder names and keyword rules, so they may be incomplete or wrong.
- Article count is only a rough popularity proxy; actual download/popularity data is not available in the catalogue.
- The intent parser supports a limited set of language names and English-language rules. Multilingual semantic matching is partial and depends on the model and query.
- The library builder is a heuristic, not an optimal knapsack solver.
- Semantic similarity settings are hand-picked and may need calibration for different queries.
- Catalogue data can become stale; re-ingest it periodically (delete `data/catalog_enriched.db` and re-run `python setup.py`).

## Data, models, and GitHub

Large or generated files are deliberately not included in this repository:

- local catalogue database(s)
- downloaded model weights
- generated embedding arrays and indexes
- caches, virtual environments, and local environment files

## Tech stack

- **Backend:** Python, FastAPI
- **Search:** SQLite FTS5 / BM25 and rule-based intent ranking
- **Semantic ranking:** SentenceTransformers and precomputed embeddings (optional)
- **Frontend:** HTML, CSS, JavaScript
- **Evaluation:** pytest and project-specific ranking scripts
