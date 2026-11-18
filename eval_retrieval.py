"""Measure retriever reliability against a small labelled question set.

Run:  python eval_retrieval.py
Reports hit@1 (right file ranked first), hit@3 (right file in top 3), and average top score,
separately for 'direct' questions (share words with the guides) and 'paraphrase' questions
(same meaning, different words). Failures are written to eval_failures.log.
"""
from __future__ import annotations

import logging
from statistics import mean

from retriever import Retriever

# (question, expected source file, kind)
EVAL_SET = [
    # direct: wording overlaps the guides
    ("how many meals a day should an adult dog eat", "feeding.md", "direct"),
    ("when should I give antibiotics twice a day", "medication.md", "direct"),
    ("how long should I walk my labrador each day", "exercise.md", "direct"),
    ("how often should I trim my dog's nails", "grooming.md", "direct"),
    ("how often should a healthy adult pet see the vet", "vet_visits.md", "direct"),
    ("what if I miss a dose of medication", "medication.md", "direct"),
    # paraphrase: same meaning, different words
    ("my puppy is hungry, how many times should it eat", "feeding.md", "paraphrase"),
    ("sick dog meds", "medication.md", "paraphrase"),
    ("is it too hot to take my pug outside", "exercise.md", "paraphrase"),
    ("my cat's fur is getting tangled", "grooming.md", "paraphrase"),
    ("getting my old dog checked over", "vet_visits.md", "paraphrase"),
    ("can I give the pills with dinner", "medication.md", "paraphrase"),
]

logging.basicConfig(
    filename="eval_failures.log", filemode="w", level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def evaluate(retriever: Retriever | None = None, k: int = 3) -> list[dict]:
    retriever = retriever or Retriever()
    results = []
    for question, expected, kind in EVAL_SET:
        hits = retriever.retrieve(question, k=k)
        sources = [h["source"] for h in hits]
        row = {
            "question": question, "expected": expected, "kind": kind,
            "top1": sources[0] if sources else None,
            "hit1": bool(sources) and sources[0] == expected,
            "hit3": expected in sources,
            "top_score": hits[0]["score"] if hits else 0.0,
        }
        if not row["hit3"]:
            logging.warning("MISS q=%r expected=%s got=%s", question, expected, sources or "nothing")
        elif not row["hit1"]:
            logging.info("RANKED LOW q=%r expected=%s top1=%s", question, expected, row["top1"])
        results.append(row)
    return results


def summarize(results: list[dict]) -> dict:
    out = {}
    for label, rows in (("all", results),
                        ("direct", [r for r in results if r["kind"] == "direct"]),
                        ("paraphrase", [r for r in results if r["kind"] == "paraphrase"])):
        out[label] = {
            "n": len(rows),
            "hit@1": sum(r["hit1"] for r in rows) / len(rows),
            "hit@3": sum(r["hit3"] for r in rows) / len(rows),
            "avg_top_score": round(mean(r["top_score"] for r in rows), 3),
        }
    return out


if __name__ == "__main__":
    results = evaluate()
    for r in results:
        mark = "PASS" if r["hit1"] else ("top3" if r["hit3"] else "MISS")
        print(f"{mark:4}  [{r['kind']:10}] {r['question']!r} -> {r['top1']} "
              f"(want {r['expected']}, score {r['top_score']})")
    print()
    for label, s in summarize(results).items():
        print(f"{label:10} n={s['n']:2}  hit@1={s['hit@1']:.0%}  hit@3={s['hit@3']:.0%}  "
              f"avg top score={s['avg_top_score']}")
    print("\nFailures logged to eval_failures.log")
