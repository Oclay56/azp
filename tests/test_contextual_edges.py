from app.contextual_edges import apply_contextual_edge_layer


def _pick(
    market_key="hits",
    side="under",
    line=1.5,
    score=82,
    confidence="high",
    risk_flags=None,
    reasons=None,
    **extra,
):
    return {
        "marketKey": market_key,
        "statKey": market_key,
        "side": side,
        "lean": side if side == "over" else "under_or_avoid_over",
        "line": line,
        "score": score,
        "confidence": confidence,
        "riskFlags": list(risk_flags or []),
        "reasons": list(reasons or ["recent_per_game_below_line"]),
        **extra,
    }


def test_hits_under_1_5_gets_distribution_context_without_hard_override():
    row = apply_contextual_edge_layer(_pick(market_key="hits", side="under", line=1.5))

    assert "hit_distribution_clustered_0_1" in row["contextualEdge"]["tags"]
    assert "hits_under_1_5_distribution_support" in row["reasons"]
    assert row["score"] > 82
    assert row["confidence"] == "high"


def test_thin_hits_under_adds_risk_instead_of_false_safety():
    row = apply_contextual_edge_layer(_pick(market_key="hits", side="under", line=0.5))

    assert "thin_hit_under_margin" in row["riskFlags"]
    assert row["confidence"] == "medium"
    assert row["contextualEdge"]["scoreAdjustment"] < 0


def test_runs_under_keeps_candidate_but_marks_game_script_dependency():
    row = apply_contextual_edge_layer(_pick(market_key="runs", side="under", line=0.5))

    assert "game_script_dependent_counting_stat" in row["riskFlags"]
    assert "run_production_market" in row["contextualEdge"]["tags"]
    assert row["confidence"] == "medium"


def test_wide_zone_umpire_does_not_boost_pitcher_strikeout_unders():
    row = apply_contextual_edge_layer(
        _pick(
            market_key="strikeouts",
            stat_key="strikeOuts",
            side="under",
            line=5.5,
            umpireContext={"category": "wide_zone", "calledStrikeRateDelta": 0.035},
        )
    )

    assert "wide_zone_umpire_risks_pitcher_k_under" in row["riskFlags"]
    assert "wide_zone_umpire_boosts_strikeouts" not in row["reasons"]
    assert row["confidence"] == "medium"


def test_missing_umpire_context_is_deferred_not_penalized():
    row = apply_contextual_edge_layer(_pick(market_key="strikeouts", side="over", line=4.5))

    assert "umpire_impact" in row["contextualEdge"]["deferredLayers"]
    assert "missing_umpire_context" not in row["riskFlags"]
