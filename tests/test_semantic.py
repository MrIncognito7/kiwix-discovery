import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "scripts"))
import app, build_embeddings
from embedder import HashEmbedder

def test_semantic_plumbing_with_stub_embedder(tmp_path, monkeypatch):
    """Checks wiring only (candidate union, scoring, explanations, fallback). Quality needs the real MiniLM."""
    monkeypatch.setattr(app, "SEM", None)
    assert app.semantic_only("science", 5) == [] and app.sem_scores("science") == {}
    shape = build_embeddings.build(app.DB, str(tmp_path), HashEmbedder()); assert shape[1] == 384
    monkeypatch.setenv("KIWIX_FAKE_EMBED", "1"); assert app.load_semantic(str(tmp_path))
    res, _ = app.intent("teach science to 12-year-olds", 10, semantic=True)
    assert res and any("semantically similar" in w for r in res for w in r["why"])
    assert app.semantic_only("french dictionary", 5)
    assert app.library("science", 3, semantic=True)["used_gb"] <= 3 + 1e-6
    app.SEM = None
