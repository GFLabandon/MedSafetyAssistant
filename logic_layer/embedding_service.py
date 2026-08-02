"""Deterministic local text vectors for bounded conversation recall.

This service intentionally does not call an embedding model.  It uses stable
character n-gram feature hashing so the project can keep one Ollama model for
generation and tool routing while Redis session recall remains reproducible.
The vectors are lexical retrieval features, not learned semantic embeddings.
"""

from __future__ import annotations

from hashlib import blake2b
from math import sqrt
import re
from typing import List
import unicodedata

from config import Config


_WHITESPACE = re.compile(r"\s+")
_NGRAM_WEIGHTS = ((1, 0.5), (2, 1.0), (3, 1.0))


class EmbeddingService:
    """Create stable local hashing vectors without a model or network call."""

    def __init__(self):
        self.vectorizer_id = Config.SESSION_VECTORIZER_ID
        self.dimensions = Config.SESSION_VECTOR_DIMENSIONS
        if not 128 <= self.dimensions <= 4096:
            raise ValueError("SESSION_VECTOR_DIMENSIONS must be between 128 and 4096")

    def embed_text(self, text: str) -> List[float]:
        """Return one L2-normalized lexical hashing vector."""

        normalized = self._normalize(text)
        if not normalized:
            return []

        vector = [0.0] * self.dimensions
        compact = normalized.replace(" ", "")
        for ngram_size, weight in _NGRAM_WEIGHTS:
            if len(compact) < ngram_size:
                continue
            for start in range(len(compact) - ngram_size + 1):
                self._accumulate(
                    vector,
                    f"c{ngram_size}:{compact[start:start + ngram_size]}",
                    weight,
                )
        for token in normalized.split(" "):
            if token:
                self._accumulate(vector, f"w:{token}", 1.5)

        magnitude = sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return []
        return [value / magnitude for value in vector]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Preserve input order while vectorizing each text locally."""

        return [self.embed_text(text) for text in texts]

    def _accumulate(self, vector: List[float], feature: str, weight: float) -> None:
        digest = blake2b(
            feature.encode("utf-8"),
            digest_size=8,
            person=b"medsafety-v1",
        ).digest()
        index = int.from_bytes(digest[:4], "big") % self.dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign * weight

    @staticmethod
    def _normalize(text: str) -> str:
        if not isinstance(text, str):
            return ""
        normalized = unicodedata.normalize("NFKC", text).casefold()
        return _WHITESPACE.sub(" ", normalized).strip()
