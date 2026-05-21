from __future__ import annotations

import pytest

from app.stake_sgm_browser import (
    _add_bet_confirmed,
    _check_page_ready,
    _fixture_matchup_from_slug,
    _find_or_open_fixture_page,
    _normalize_mlb_game_link,
    _has_logged_out_warning,
    _market_display_aliases,
    _market_search_text,
    fixture_url,
)


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.navigated_to: list[str] = []

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.url = url
        self.navigated_to.append(url)


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages

    def new_page(self) -> FakePage:
        page = FakePage("about:blank")
        self.pages.append(page)
        return page


class FakeLocator:
    def __init__(self, text: str) -> None:
        self.text = text

    def inner_text(self, *, timeout: int) -> str:
        return self.text


class FakeReadyPage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.navigated_to: list[str] = []

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        return None

    def locator(self, selector: str) -> FakeLocator:
        assert selector == "body"
        return FakeLocator(self.text)

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.navigated_to.append(url)


def test_find_or_open_fixture_page_refreshes_restricted_region_tab():
    fixture_slug = "46575343-miami-marlins-atlanta-braves"
    page = FakePage(
        fixture_url(fixture_slug)
        + "?regionKey=US&country=US&region=GA&modal=restrictedRegion"
    )
    context = FakeContext([page])

    found = _find_or_open_fixture_page(context, fixture_slug)

    assert found is page
    assert page.navigated_to == [fixture_url(fixture_slug)]


def test_find_or_open_fixture_page_reuses_clean_fixture_tab():
    fixture_slug = "46575343-miami-marlins-atlanta-braves"
    page = FakePage(fixture_url(fixture_slug))
    context = FakeContext([page])

    found = _find_or_open_fixture_page(context, fixture_slug)

    assert found is page
    assert page.navigated_to == []


def test_check_page_ready_reports_cloudflare_verification():
    page = FakeReadyPage(
        "stake.com\nPerforming security verification\n"
        "This website uses a security service to protect against malicious bots."
    )

    with pytest.raises(RuntimeError, match="Cloudflare verification"):
        _check_page_ready(page)


def test_check_page_ready_accepts_hyphenated_same_game_multi_tab():
    page = FakeReadyPage("Wallet\nMain\nSame-Game Multi\nPlayer Props")

    assert _check_page_ready(page) == []


def test_check_page_ready_reloads_region_blocked_fixture_before_failing():
    fixture_slug = "46575343-miami-marlins-atlanta-braves"
    page = FakeReadyPage("Sorry, Stake.com is not available in your region.")

    with pytest.raises(RuntimeError, match="region-blocked"):
        _check_page_ready(page, fixture_slug=fixture_slug)

    assert page.navigated_to == [fixture_url(fixture_slug)]


def test_has_logged_out_warning_detects_account_action_blocker():
    assert _has_logged_out_warning(
        ["browser appears logged out; read-only SGM data may still load"]
    )
    assert not _has_logged_out_warning(["page did not reach networkidle before continuing"])


def test_normalize_mlb_game_link_accepts_localized_stake_urls():
    link = _normalize_mlb_game_link(
        "https://stake.com/de/sports/baseball/usa/mlb/46575562-washington-nationals-new-york-mets"
    )

    assert link == {
        "fixtureSlug": "46575562-washington-nationals-new-york-mets",
        "url": "https://stake.com/de/sports/baseball/usa/mlb/46575562-washington-nationals-new-york-mets",
        "matchup": "Washington Nationals vs New York Mets",
        "teams": ["Washington Nationals", "New York Mets"],
    }


def test_normalize_mlb_game_link_rejects_non_fixture_links():
    assert _normalize_mlb_game_link("https://stake.com/sports/baseball/usa/mlb") is None
    assert _normalize_mlb_game_link("https://stake.com/sports/football/usa/nfl/123-test") is None


def test_fixture_matchup_from_slug_handles_multi_word_team_names():
    assert _fixture_matchup_from_slug(
        "46575351-new-york-yankees-toronto-blue-jays"
    ) == {
        "matchup": "New York Yankees vs Toronto Blue Jays",
        "teams": ["New York Yankees", "Toronto Blue Jays"],
    }


def test_market_aliases_cover_stake_sgm_team_and_translated_labels():
    assert _market_search_text("Team Hits") == "hits"
    assert _market_search_text("Team RBIs") == "rbi"
    assert _market_search_text("Failed Attempts") == "strikeouts"

    assert "Hits" in _market_display_aliases("Team Hits")
    assert "Team RBIs" in _market_display_aliases("Team RBIs")
    assert "RBIs" in _market_display_aliases("Team RBIs")
    assert "Failed Attempts" in _market_display_aliases("Strikeouts")
    assert "First Well Deserved Run" in _market_display_aliases("First ER")


def test_add_bet_confirmation_requires_sidebar_change_when_existing_slip_present():
    before = {
        "rightPanelEmpty": False,
        "rightPanelTextDigest": "same",
        "rightPanelTextLength": 120,
        "rightPanelSelectionCount": 2,
    }
    unchanged_after = {
        "rightPanelEmpty": False,
        "rightPanelTextDigest": "same",
        "rightPanelTextLength": 120,
        "rightPanelSelectionCount": 2,
    }
    changed_after = {
        "rightPanelEmpty": False,
        "rightPanelTextDigest": "different",
        "rightPanelTextLength": 180,
        "rightPanelSelectionCount": 4,
    }

    assert not _add_bet_confirmed(before, unchanged_after)
    assert _add_bet_confirmed(before, changed_after)
    assert _add_bet_confirmed({"rightPanelEmpty": True}, changed_after)
