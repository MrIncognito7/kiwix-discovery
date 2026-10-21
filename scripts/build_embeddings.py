"""Encode every catalogue entry with MiniLM.  python scripts/build_embeddings.py   (needs internet once)
Writes data/embeddings.npy (N x 384, L2-normalised), data/embedding_rowids.npy and a local model copy under data/model_*."""
import os, sqlite3, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from embedder import MODEL_NAME, HashEmbedder, get_embedder, LOCAL


def build(db, out_dir, embedder):
    rows = sqlite3.connect(db).execute("SELECT rowid, title, description, tags, family FROM resources_enriched ORDER BY rowid").fetchall()
    texts = [f"{t}. {d or ''} {(g or '').replace(';', ', ')} {f or ''}".strip() for _, t, d, g, f in rows]
    emb = np.asarray(embedder.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=True), dtype="float32")
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "embeddings.npy"), emb); np.save(os.path.join(out_dir, "embedding_rowids.npy"), np.array([r[0] for r in rows]))
    open(os.path.join(out_dir, "embeddings_model.txt"), "w").write("stub" if isinstance(embedder, HashEmbedder) else MODEL_NAME)
    return emb.shape


if __name__ == "__main__":
    e = get_embedder(); print("embedded", build(os.path.join(ROOT, "data", "catalog_enriched.db"), os.path.join(ROOT, "data"), e))
    if hasattr(e, "save"): e.save(LOCAL); print("saved offline model copy to", LOCAL)