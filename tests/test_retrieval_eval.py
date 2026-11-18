"""Reliability checks: measured retrieval accuracy on the labelled question set."""
import pytest

from eval_retrieval import EVAL_SET, evaluate, summarize


@pytest.fixture(scope="module")
def summary():
    return summarize(evaluate())


def test_eval_set_has_both_kinds():
    kinds = {kind for _, _, kind in EVAL_SET}
    assert kinds == {"direct", "paraphrase"}


def test_direct_questions_always_find_right_file_first(summary):
    # Regression guard: questions that share words with the guides must keep working.
    assert summary["direct"]["hit@1"] == 1.0


def test_overall_accuracy_does_not_regress_below_measured_baseline(summary):
    # Baseline measured on 2026-11-18: 8/12 = 67% hit@1 overall.
    assert summary["all"]["hit@1"] >= 0.65


@pytest.mark.xfail(reason="Known weakness: keyword (TF-IDF) retrieval misses paraphrases; "
                          "measured 2/6. Fix with synonyms or embeddings.", strict=False)
def test_paraphrase_questions_meet_target(summary):
    assert summary["paraphrase"]["hit@1"] >= 0.8
