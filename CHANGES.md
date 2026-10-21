# Frontend integration: what changed

Copy these files over your project (same relative paths). Your `data/` folder is untouched.

| File | Change |
|---|---|
| `static/index.html`, `static/style.css`, `static/script.js` | New frontend, wired to `/api/search`, `/api/library`, `/api/meta`, `/api/eval`. Replaces the old single-page `index.html`. |
| `app.py` | Added `GET /api/meta` (catalogue size, snapshot date, whether MiniLM modes are available) and `GET /api/eval` (serves `eval/results.json`). Added read-only CORS so the page can also be opened with `?api=http://localhost:8000`. Search, library and ranking code are unchanged. |
| `eval/run_eval.py` | Also writes `eval/results.json` (summary, per-query nDCG and precision, wins/ties/losses). Metrics code unchanged. |
| `eval/results.json` | Generated from your existing `results.md` so the Evaluation tab works now. Re-run `python eval/run_eval.py` to regenerate it with per-query precision. |

Run as before: `uvicorn app:app --reload`, then open http://localhost:8000

Behaviour notes
- Ranking method dropdown maps to `mode=` (hybrid, intent, baseline, semantic). Hybrid/semantic are disabled automatically when embeddings are not built.
- Sidebar filters (subject, language, last updated, max size, stale, limitations) apply client-side to the top 60 results.
- "Understood" chips show what `parse()` extracted (subject, language, size cap, age).
- Library: Build My Library calls `/api/library`; saved items keep the chosen version. Export gives `my_library.json` (same shape as scripts/manifest.py) and a `download.sh`.
- The education-level filter was removed, as requested; `education_level` is still used by the backend ranker.
