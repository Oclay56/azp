from __future__ import annotations

from app.local_helper_gui import HELPER_BG, HELPER_FG, should_minimize_to_tray


def test_should_minimize_to_tray_only_for_iconic_windows_with_tray_support():
    assert should_minimize_to_tray("iconic", tray_supported=True)
    assert not should_minimize_to_tray("normal", tray_supported=True)
    assert not should_minimize_to_tray("withdrawn", tray_supported=True)
    assert not should_minimize_to_tray("iconic", tray_supported=False)


def test_helper_gui_uses_dark_navy_theme():
    assert HELPER_BG == "#03041D"
    assert HELPER_FG == "#F4F0FF"
