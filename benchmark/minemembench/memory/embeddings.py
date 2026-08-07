"""Pure-Python embeddings for the `vector` memory baseline.

`Embedder` is the seam through which the backend talks to any embedding
implementation. `HashEmbedder` is the shipped *baseline*: deterministic and
network-free, so the benchmark runs offline and byte-identically across
processes. An API-backed embedder (OpenAI embeddings, a local model, ...) can
be dropped in later without touching the backend or the storage format.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

#: Bag-of-words dimension of HashEmbedder vectors.
EMBED_DIM = 256

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    """Anything that maps text to a fixed-length embedding vector."""

    name: str

    def embed(self, text: str) -> list[float]:
        """Embed `text` into a fixed-dimensional vector (not necessarily normalized)."""


class HashEmbedder:
    """Baseline embedder: hashed bag-of-words, deterministic and offline.

    Tokenizes on any non-alphanumeric character and lowercases, then hashes
    every token with md5 into a fixed 256-dim bag-of-words vector that is
    L2-normalized. Texts sharing tokens get positive cosine similarity;
    disjoint texts score zero (modulo hash collisions). Intentionally crude —
    it exists to make the vector backend run without any external embedding
    service, not to rival a real embedding model.
    """

    name = "hash"

    @staticmethod
    def embed(text: str) -> list[float]:
        vector = [0.0] * EMBED_DIM
        for token in _TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            vector[digest[0]] += 1.0
        return _l2_normalize(vector)


def _l2_normalize(vector: list[float]) -> list[float]:
    """Normalize `vector` to unit length; all-zero vectors pass through."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors, in [-1, 1]; 0.0 for a zero vector."""
    dot = sum(av * bv for av, bv in zip(a, b))
    norm_a = math.sqrt(sum(av * av for av in a))
    norm_b = math.sqrt(sum(bv * bv for bv in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
