from __future__ import annotations

from typing import Any


PITCHER_MARKETS = {
    "strikeouts",
    "pitcher-strikeouts",
    "earned-runs",
    "pitcher-earned-runs",
    "walks-allowed",
    "hits-allowed",
    "outs-recorded",
    "pitcher-outs",
    "first-earned-run",
}

RUN_PRODUCTION_MARKETS = {"runs", "rbi"}


def apply_contextual_edge_layer(row: dict[str, Any]) -> dict[str, Any]:
    """Attach deterministic context tags without inventing new picks."""

    enriched = dict(row)
    reasons = _unique_strings(enriched.get("reasons") or [])
    risk_flags = _unique_strings(enriched.get("riskFlags") or [])
    tags: list[str] = []
    notes: list[str] = []
    deferred_layers: list[str] = []
    score_adjustment = 0

    market = _normalize(enriched.get("marketKey") or enriched.get("statKey"))
    stat = _normalize(enriched.get("statKey"))
    side = _side(enriched)
    line = _float_or_none(enriched.get("line"))

    score_adjustment += _apply_distribution_context(
        market=market,
        side=side,
        line=line,
        reasons=reasons,
        risk_flags=risk_flags,
        tags=tags,
        notes=notes,
    )
    score_adjustment += _apply_prop_positioning_context(
        market=market,
        stat=stat,
        side=side,
        line=line,
        reasons=reasons,
        risk_flags=risk_flags,
        tags=tags,
        notes=notes,
    )
    umpire_adjustment = _apply_umpire_context(
        market=market,
        stat=stat,
        side=side,
        row=enriched,
        reasons=reasons,
        risk_flags=risk_flags,
        tags=tags,
        notes=notes,
    )
    if umpire_adjustment is None:
        deferred_layers.append("umpire_impact")
    else:
        score_adjustment += umpire_adjustment

    enriched["reasons"] = _unique_strings(reasons)
    enriched["riskFlags"] = _unique_strings(risk_flags)
    enriched["score"] = _clamped_score(enriched.get("score"), score_adjustment)
    enriched["confidence"] = _confidence(enriched.get("confidence"), enriched["riskFlags"])
    enriched["contextualEdge"] = {
        "tags": _unique_strings(tags),
        "notes": _unique_strings(notes),
        "scoreAdjustment": score_adjustment,
        "deferredLayers": _unique_strings(deferred_layers),
    }
    return enriched


def _apply_distribution_context(
    market: str,
    side: str,
    line: float | None,
    reasons: list[str],
    risk_flags: list[str],
    tags: list[str],
    notes: list[str],
) -> int:
    adjustment = 0

    if market == "hits":
        tags.append("hit_distribution_clustered_0_1")
        if side == "under" and line is not None and line >= 1.5:
            reasons.append("hits_under_1_5_distribution_support")
            notes.append("hits naturally cluster at zero or one more than multi-hit games")
            adjustment += 2
        elif side == "under" and line is not None and line <= 0.5:
            risk_flags.append("thin_hit_under_margin")
            notes.append("under 0.5 hits has no miss cushion")
            adjustment -= 4
        elif side == "over" and line is not None and line >= 1.5:
            risk_flags.append("multi_hit_dependency")
            notes.append("over 1.5 hits requires a multi-hit outcome")
            adjustment -= 3

    if market == "total-bases":
        tags.append("total_bases_right_tail")
        if side == "under":
            reasons.append("total_bases_under_reduces_extra_base_outlier_risk")
            notes.append("total bases are pulled upward by rare extra-base outcomes")
            adjustment += 1
        elif side == "over":
            risk_flags.append("extra_base_hit_dependency")
            adjustment -= 3

    if market == "home-runs":
        tags.append("rare_event_market")
        risk_flags.append("rare_event_market")
        adjustment -= 5

    return adjustment


def _apply_prop_positioning_context(
    market: str,
    stat: str,
    side: str,
    line: float | None,
    reasons: list[str],
    risk_flags: list[str],
    tags: list[str],
    notes: list[str],
) -> int:
    adjustment = 0

    if market in RUN_PRODUCTION_MARKETS:
        tags.append("run_production_market")
        risk_flags.append("game_script_dependent_counting_stat")
        notes.append("runs and RBI depend heavily on lineup slot and game script")
        adjustment -= 4

    if _is_pitcher_market(market, stat):
        tags.append("pitcher_management_sensitive")
        if "strikeout" in f"{market} {stat}":
            if side == "under":
                reasons.append("pitcher_k_under_can_benefit_from_pitch_count_or_early_hook")
                notes.append("pitcher K unders depend as much on workload as skill")
            elif side == "over":
                risk_flags.append("pitcher_workload_leash_needed")
                notes.append("pitcher K overs need enough innings and pitch count runway")
                adjustment -= 2
        if line is not None and line >= 8.5:
            risk_flags.append("high_pitcher_line")
            adjustment -= 3

    if market in {"earned-runs", "pitcher-earned-runs", "hits-allowed"}:
        tags.append("run_environment_sensitive")
        risk_flags.append("game_environment_sensitive")
        adjustment -= 2

    return adjustment


def _apply_umpire_context(
    market: str,
    stat: str,
    side: str,
    row: dict[str, Any],
    reasons: list[str],
    risk_flags: list[str],
    tags: list[str],
    notes: list[str],
) -> int | None:
    context = row.get("umpireContext") or (row.get("mlbGame") or {}).get("umpireContext")
    if not isinstance(context, dict) or not context:
        return None

    category = _normalize(context.get("category"))
    text = f"{market} {stat}"
    is_strikeout = "strikeout" in text
    is_hitter_count = market in {"hits", "total-bases", "home-runs"}
    adjustment = 0
    tags.append("umpire_impact")

    if category in {"wide-zone", "wide_zone", "enforcer", "k-friendly"}:
        tags.append("wide_zone_umpire")
        if is_strikeout and side == "under":
            risk_flags.append("wide_zone_umpire_risks_pitcher_k_under")
            notes.append("wide zones tend to help strikeouts, so K unders lose support")
            adjustment -= 6
        elif is_strikeout and side == "over":
            reasons.append("wide_zone_umpire_boosts_strikeouts")
            adjustment += 4
        elif is_hitter_count and side == "under":
            reasons.append("wide_zone_umpire_suppresses_hitter_contact")
            adjustment += 2
    elif category in {"tight-zone", "tight_zone", "hitter-friendly", "walk-heavy"}:
        tags.append("tight_zone_umpire")
        if is_strikeout and side == "under":
            reasons.append("tight_zone_umpire_suppresses_strikeouts")
            adjustment += 4
        elif is_strikeout and side == "over":
            risk_flags.append("tight_zone_umpire_risks_pitcher_k_over")
            adjustment -= 5
        elif is_hitter_count and side == "under":
            risk_flags.append("tight_zone_umpire_can_extend_offense")
            adjustment -= 3
    else:
        tags.append("neutral_umpire")

    return adjustment


def _is_pitcher_market(market: str, stat: str) -> bool:
    return market in PITCHER_MARKETS or any(
        token in f"{market} {stat}"
        for token in ("strikeout", "earned-run", "outs", "walks-allowed", "hits-allowed")
    )


def _side(row: dict[str, Any]) -> str:
    value = str(row.get("side") or row.get("lean") or "").strip().lower()
    selection = str(row.get("selection") or "").strip().lower()
    text = f"{value} {selection}"
    if "under" in text:
        return "under"
    if "over" in text:
        return "over"
    return "unknown"


def _confidence(current: Any, risk_flags: list[str]) -> str:
    normalized = str(current or "medium").strip().lower()
    if risk_flags and normalized == "high":
        return "medium"
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "medium"


def _clamped_score(value: Any, adjustment: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 50
    return max(0, min(100, score + adjustment))


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_strings(values: list[Any]) -> list[str]:
    seen = set()
    results = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results
