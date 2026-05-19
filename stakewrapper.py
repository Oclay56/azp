from __future__ import annotations

import argparse
import json
import sys

from app.stake_sgm_browser import DEFAULT_CDP_URL, read_stake_sgm_board


DEFAULT_FIXTURE = "46450286-miami-marlins-atlanta-braves"


def _filter_rows(
    rows: list[dict],
    market: str | None,
    player: str | None,
    playable_only: bool,
) -> list[dict]:
    filtered = rows
    if market:
        market_l = market.lower()
        filtered = [row for row in filtered if market_l in (row.get("market") or "").lower()]
    if player:
        player_l = player.lower()
        filtered = [row for row in filtered if player_l in (row.get("player") or "").lower()]
    if playable_only:
        filtered = [row for row in filtered if row.get("playable")]
    return filtered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read the Stake UI-backed MLB Same Game Multi board from Chrome."
    )
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE, help="Stake fixture slug.")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help="Chrome remote debugging URL.")
    parser.add_argument("--market", help="Optional market text filter, for example hits or runs.")
    parser.add_argument("--player", help="Optional player name filter.")
    parser.add_argument("--playable-only", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    try:
        board = read_stake_sgm_board(args.fixture, args.cdp_url)
        board["teamMarkets"] = _filter_rows(
            board["teamMarkets"],
            args.market,
            None,
            args.playable_only,
        )
        board["playerProps"] = _filter_rows(
            board["playerProps"],
            args.market,
            args.player,
            args.playable_only,
        )
        board["returnedCounts"] = {
            "teamMarkets": len(board["teamMarkets"]),
            "playerProps": len(board["playerProps"]),
        }
        board["filters"] = {
            "market": args.market,
            "player": args.player,
            "playableOnly": args.playable_only,
        }

        if args.summary:
            board = {
                "fixture": board["fixture"],
                "teams": board["teams"],
                "counts": board["counts"],
                "returnedCounts": board["returnedCounts"],
                "filters": board["filters"],
                "warnings": board["warnings"],
            }
        print(json.dumps(board, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
