from __future__ import annotations

from app.storage import GptActionStore


def test_store_saves_gpt_decision_legs(tmp_path):
    store = GptActionStore(tmp_path / "gpt.sqlite")
    result = store.save_gpt_decision_result(
        {
            "decisionOwner": "custom_gpt",
            "matchup": "Blue Jays vs Angels",
            "date": "2026-05-08",
            "validation": {"valid": True},
            "selections": [
                {
                    "selectionId": "prop-1:under",
                    "propId": "prop-1",
                    "fixtureSlug": "blue-jays-angels",
                    "player": {"name": "George Springer"},
                    "team": {"name": "Toronto Blue Jays"},
                    "market": {"key": "hits", "name": "hits"},
                    "side": "under",
                    "line": 0.5,
                    "odds": 2.9,
                    "playable": True,
                    "availability": {"status": "active"},
                    "decisionProfile": {
                        "finalStatus": "playable",
                        "riskFlags": ["recent_and_season_agree"],
                    },
                }
            ],
        },
        request_body={"matchup": "Blue Jays vs Angels"},
    )

    rows = store.list_gpt_decision_legs(date_text="2026-05-08")
    assert result["gptDecisionLegsInserted"] == 1
    assert rows[0]["decisionId"] == result["decisionId"]
    assert rows[0]["player"] == "George Springer"
    assert rows[0]["playable"] is True
    assert rows[0]["decisionProfile"]["finalStatus"] == "playable"
    assert rows[0]["riskFlags"] == ["recent_and_season_agree"]
    assert rows[0]["settlement"]["status"] == "unsettled"


def test_store_saves_market_mappings(tmp_path):
    store = GptActionStore(tmp_path / "gpt.sqlite")
    result = store.save_market_mappings(
        [
            {
                "sport": "mlb",
                "stakeDisplayName": "Hits Allowed",
                "internalMarketKey": "hits-allowed",
                "statKey": "hits",
                "group": "pitching",
                "active": True,
                "examples": [{"player": "Pitcher"}],
            }
        ]
    )

    assert result["marketMappingsSaved"] == 1
