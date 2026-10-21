"""Embedding model loader. Default: paraphrase-multilingual-MiniLM-L12-v2 (50+ languages, 384 dims).
Set KIWIX_MODEL=sentence-transformers/all-MiniLM-L6-v2 for the smaller English-only model, then rebuild embeddings.
build_embeddings.py saves a local copy under data/ so runtime needs no internet."""
import hashlib, os, re
import numpy as np

MODEL_NAME = os.environ.get("KIWIX_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "model_" + MODEL_NAME.split("/")[-1])

class HashEmbedder:
    """TEST STUB ONLY (KIWIX_FAKE_EMBED=1): hashed bag-of-words, not a language model. Used to test plumbing."""
    def encode(self, texts, **kw):
        out = np.zeros((len(texts), 384), dtype="float32")
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", t.lower()): out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % 384] += 1
        return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)


def get_embedder():
    if os.environ.get("KIWIX_FAKE_EMBED"): return HashEmbedder()
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(LOCAL if os.path.isdir(LOCAL) else MODEL_NAME)
