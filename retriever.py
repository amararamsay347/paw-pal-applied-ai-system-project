"""Retriever for the RAG layer.

Loads the markdown files in kb/, splits them into paragraph chunks, and ranks chunks
against a query with TF-IDF cosine similarity. Pure Python, no extra dependencies.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

KB_DIR = Path(__file__).parent / "kb"

STOPWORDS = frozenset(
    "a an and are as at be by for from has have he her his how i in is it its my of on or "
    "she that the their they this to was what when with you your do does should give them "
    "often much long can will need needs".split()
)


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str  # file name, used for citations


def _stem(word: str) -> str:
    """Very light stemming: dogs -> dog, feeding -> feed, walking -> walk."""
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 3 and word.endswith("s"):
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    """Lowercase words with stopwords removed and light stemming."""
    return [_stem(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in STOPWORDS]


def load_chunks(kb_dir: Path = KB_DIR) -> list[Chunk]:
    """One chunk per paragraph, skipping headings and the trailing 'Note:' disclaimer."""
    chunks = []
    for path in sorted(kb_dir.glob("*.md")):
        for para in path.read_text(encoding="utf-8").split("\n\n"):
            para = para.strip()
            if not para or para.startswith("#") or para.startswith("Note:"):
                continue
            chunks.append(Chunk(text=para, source=path.name))
    return chunks


class Retriever:
    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks = chunks if chunks is not None else load_chunks()
        self._tokens = [Counter(tokenize(c.text)) for c in self.chunks]
        df = Counter(w for toks in self._tokens for w in toks)
        n = len(self.chunks)
        self._idf = {w: math.log((n + 1) / (d + 1)) + 1 for w, d in df.items()}
        self._vecs = [self._vector(toks) for toks in self._tokens]

    def _vector(self, counts: Counter) -> dict[str, float]:
        vec = {w: c * self._idf[w] for w, c in counts.items() if w in self._idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {w: v / norm for w, v in vec.items()}

    def retrieve(self, query: str, k: int = 3, min_score: float = 0.05) -> list[dict]:
        """Top-k chunks for the query, best first. Chunks scoring below min_score are dropped,
        so an unrelated query returns [] instead of junk."""
        q = self._vector(Counter(tokenize(query)))
        scored = [
            (sum(w * vec.get(t, 0.0) for t, w in q.items()), chunk)
            for vec, chunk in zip(self._vecs, self.chunks)
        ]
        scored.sort(key=lambda s: s[0], reverse=True)
        return [
            {"text": c.text, "source": c.source, "score": round(s, 3)}
            for s, c in scored[:k] if s >= min_score
        ]


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "my dog is on antibiotics, when should I give them"
    print(f"Query: {query}\n")
    for hit in Retriever().retrieve(query):
        print(f"[{hit['source']}] score={hit['score']}\n  {hit['text']}\n")
