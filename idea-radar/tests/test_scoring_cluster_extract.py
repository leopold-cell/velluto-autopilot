from idearadar.cluster import cluster
from idearadar.extract import extract_problems, verify_quote
from idearadar.scoring import payers_needed, score_idea

GOOD = dict(recurrence=1, affluence=1, wtp=1, competition_gap=1, ai_automatable=1, buildable=1, reach=1, timing=1)


def test_score_max_and_penalties():
    r = score_idea(GOOD, 99, 5000, 2000)
    assert r.score == 100 and not r.penalties
    weak = score_idea({**GOOD, "affluence": 0.1, "reach": 0.1}, 99, 5000, 2000)
    assert "weak_affluence_evidence" in weak.penalties and "no_clear_channel" in weak.penalties
    assert weak.score < 70


def test_payers_needed_penalty():
    assert payers_needed(49, 5000) == 146
    assert "too_many_payers_needed" in score_idea(GOOD, 2, 5000, 2000).penalties


def test_cluster_groups_similar_problems():
    items = [(1, "Ferienimmobilie verwalten Handwerker koordinieren Wartung Zweitwohnsitz"),
             (2, "Wartung Ferienimmobilie Handwerker koordinieren schwierig Zweitwohnsitz"),
             (3, "Steuerberater findet Nachfolger Firma Verkauf Geschäftsführer")]
    groups = cluster(items)
    assert sorted(map(sorted, groups)) == [[1, 2], [3]]


class FakeLLM:
    def __init__(self, data):
        self.data = data

    def complete_json(self, system, user, *, max_tokens=2000):
        return self.data


def test_extract_drops_unverified_quotes():
    text = "Ich leite eine GmbH mit 40 Mitarbeitern und zahle 300 Euro im Monat für einen Steuerberater, der nie antwortet."
    llm = FakeLLM({"problems": [{"item_id": 1, "summary": "Steuerberater antwortet nicht", "persona": "GF", "affluence": 0.9,
                                 "affluence_quote": "GmbH mit 40 Mitarbeitern", "wtp": 0.9, "wtp_quote": "zahle 3000 Euro im Monat"},
                                {"item_id": 99, "summary": "unknown item", "affluence": 1}]})
    out = extract_problems(llm, [(1, text)])
    assert len(out) == 1
    assert out[0]["affluence"] == 0.9 and out[0]["wtp"] == 0.0  # invented wtp quote is rejected
    assert verify_quote("GmbH   mit 40 Mitarbeitern", text)
