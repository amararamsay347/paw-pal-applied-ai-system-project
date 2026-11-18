import pytest

from retriever import Retriever, tokenize


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


@pytest.mark.parametrize(
    "query, expected_source",
    [
        ("my dog is on antibiotics, when do I give the doses", "medication.md"),
        ("how often should I feed my puppy", "feeding.md"),
        ("how long should I walk a beagle", "exercise.md"),
        ("how often should I brush my golden retriever", "grooming.md"),
        ("does my pet need to fast before surgery at the vet", "vet_visits.md"),
    ],
)
def test_top_hit_comes_from_expected_file(retriever, query, expected_source):
    hits = retriever.retrieve(query, k=3)
    assert hits, "expected at least one hit"
    assert hits[0]["source"] == expected_source


def test_unrelated_query_returns_nothing(retriever):
    assert retriever.retrieve("quarterly corporate tax filing deadlines") == []


def test_empty_query_returns_nothing(retriever):
    assert retriever.retrieve("") == []


def test_k_limits_results_and_scores_descend(retriever):
    hits = retriever.retrieve("dog food and exercise", k=2)
    assert len(hits) <= 2
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)


def test_hits_have_citation_fields(retriever):
    hit = retriever.retrieve("brush the dog")[0]
    assert set(hit) == {"text", "source", "score"}
    assert hit["source"].endswith(".md")


def test_tokenize_drops_stopwords_and_plurals():
    assert tokenize("The dogs are walking") == ["dog", "walk"]
