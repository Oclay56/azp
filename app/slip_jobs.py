from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .mlb_props import slug_key
from .slate import DEFAULT_TIMEZONE, build_mlb_matchups


async def build_mlb_schedule_view(
    mlb_engine: Any,
    slate_date: date | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    timezone = ZoneInfo(timezone_name)
    target_date = slate_date or datetime.now(timezone).date()
    schedule = await mlb_engine.get_schedule(target_date.isoformat())
    games = [_schedule_game_row(game) for game in schedule.get("games") or []]
    return {
        "source": "mlb_stats_api",
        "date": target_date.isoformat(),
        "timezone": timezone_name,
        "gameCount": len(games),
        "games": games,
    }


async def build_mlb_schedule_stake_map(
    mlb_engine: Any,
    stake_client: Any,
    slate_date: date | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
    limit: int = 100,
) -> dict[str, Any]:
    mlb_schedule = await build_mlb_schedule_view(
        mlb_engine=mlb_engine,
        slate_date=slate_date,
        timezone_name=timezone_name,
    )
    stake_schedule = await build_mlb_matchups(
        client=stake_client,
        slate_date=slate_date,
        timezone_name=timezone_name,
        limit=limit,
    )
    stake_index = {
        _team_set_key(row.get("teams") or []): row
        for row in stake_schedule.get("matchups") or []
        if _team_set_key(row.get("teams") or [])
    }

    mapped_games = []
    for game in mlb_schedule["games"]:
        teams = [
            (game.get("awayTeam") or {}).get("name"),
            (game.get("homeTeam") or {}).get("name"),
        ]
        stake_match = stake_index.get(_team_set_key(teams))
        mapped = dict(game)
        mapped["stake"] = _stake_match_row(stake_match)
        mapped_games.append(mapped)

    return {
        "source": "mlb_stats_api_plus_stake_odds_api",
        "date": mlb_schedule["date"],
        "timezone": timezone_name,
        "gameCount": len(mapped_games),
        "stakeAvailableCount": sum(1 for game in mapped_games if game["stake"]["available"]),
        "games": mapped_games,
    }


def normalize_slip_job_request(payload: dict[str, Any]) -> dict[str, Any]:
    selections = _normalize_slip_job_selections(payload.get("selections"))

    matchup = _text(payload.get("matchup"))
    slate_date = _text(payload.get("date") or payload.get("slateDate"))
    return {
        "source": _text(payload.get("source")) or "custom_gpt",
        "prompt": _text(payload.get("prompt")),
        "slipType": _text(payload.get("slipType") or payload.get("slip_type")) or "review_slip",
        "matchup": matchup,
        "date": slate_date,
        "mode": _text(payload.get("mode")),
        "target": payload.get("target") if isinstance(payload.get("target"), dict) else {},
        "selections": selections,
        "request": payload,
    }


def _normalize_slip_job_selections(raw_selections: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_selections, list) or not raw_selections:
        raise ValueError("Slip job requires at least one selection.")
    return [
        _normalize_slip_job_selection(raw_selection, index)
        for index, raw_selection in enumerate(raw_selections, start=1)
    ]


def _normalize_slip_job_selection(raw_selection: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw_selection, dict):
        raise ValueError(f"Slip job selection {index} must be an object.")

    if raw_selection.get("valid") is False:
        status = _text(raw_selection.get("status")) or "invalid"
        raise ValueError(
            f"Slip job selection {index} failed validation ({status}). "
            "Do not create a slip job from invalid selections."
        )

    selection = raw_selection.get("current") if isinstance(raw_selection.get("current"), dict) else raw_selection
    player = selection.get("player") if isinstance(selection.get("player"), dict) else {}
    market = selection.get("market") if isinstance(selection.get("market"), dict) else {}
    player_name = _text(player.get("name"))
    market_name = _text(market.get("name") or market.get("key"))
    side = (_text(selection.get("side")) or "").lower()
    line = _float_or_none(selection.get("line"))
    odds = _float_or_none(selection.get("odds"))
    selection_id = _text(selection.get("selectionId"))
    fixture_slug = _text(selection.get("fixtureSlug"))

    missing = []
    if not selection_id:
        missing.append("selectionId")
    if not fixture_slug:
        missing.append("fixtureSlug")
    if not player_name or player_name.lower().startswith("unknown"):
        missing.append("player.name")
    if not market_name or market_name.lower() == "market":
        missing.append("market.name/key")
    if side not in {"over", "under"}:
        missing.append("side")
    if line is None:
        missing.append("line")
    if odds is None:
        missing.append("odds")

    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(
            f"Slip job selection {index} is missing exact validated fields: {missing_text}. "
            "Call validateSelections first and pass each valid result.current row to createSlipJob."
        )

    normalized = dict(selection)
    normalized["player"] = dict(player)
    normalized["market"] = dict(market)
    normalized["side"] = side
    normalized["line"] = line
    normalized["odds"] = odds
    return normalized


def _schedule_game_row(game: dict[str, Any]) -> dict[str, Any]:
    away = game.get("awayTeam") or {}
    home = game.get("homeTeam") or {}
    return {
        "gamePk": game.get("gamePk"),
        "matchup": _matchup_text(away, home),
        "gameDate": game.get("gameDate"),
        "status": game.get("status"),
        "awayTeam": away,
        "homeTeam": home,
        "probablePitchers": {
            "away": away.get("probablePitcher"),
            "home": home.get("probablePitcher"),
        },
    }


def _stake_match_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"available": False}
    return {
        "available": True,
        "fixtureSlug": row.get("fixtureSlug"),
        "name": row.get("name"),
        "teams": row.get("teams") or [],
        "startTime": row.get("startTime"),
        "status": row.get("status"),
        "type": row.get("type"),
        "source": row.get("source"),
    }


def _matchup_text(away: dict[str, Any], home: dict[str, Any]) -> str:
    away_name = away.get("name") or "Away"
    home_name = home.get("name") or "Home"
    return f"{away_name} vs {home_name}"


def _team_set_key(teams: list[Any]) -> str:
    keys = sorted(slug_key(team) for team in teams if slug_key(team))
    return "|".join(keys)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
