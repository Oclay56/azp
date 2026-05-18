from __future__ import annotations

import json

from app.local_archive import (
    archive_gpt_decision,
    archive_market_mappings,
    archive_status,
)


def test_archive_status_disabled_without_path(monkeypatch, tmp_path):
    monkeypatch.delenv("AZP_LOCAL_ARCHIVE_DIR", raising=False)
    monkeypatch.setattr("app.local_archive.DEFAULT_WINDOWS_ARCHIVE_ROOT", tmp_path / "missing")

    status = archive_status()

    assert status["enabled"] is False
    assert status["available"] is False
    assert status["path"] is None


def test_archive_gpt_decision_writes_jsonl(monkeypatch, tmp_path):
    archive_root = tmp_path / "archives"
    monkeypatch.setenv("AZP_LOCAL_ARCHIVE_DIR", str(archive_root))

    result = archive_gpt_decision(
        {"matchup": "Blue Jays vs Angels", "selections": []},
        {"prompt": "test"},
        decision_id="decision-1",
    )

    assert result["enabled"] is True
    assert result["available"] is True
    assert result["saved"] is True

    records = (archive_root / "gpt_decisions").glob("*.jsonl")
    archive_file = next(records)
    record = json.loads(archive_file.read_text(encoding="utf-8").strip())
    assert record["recordType"] == "gpt_decision"
    assert record["decisionId"] == "decision-1"
    assert record["request"]["prompt"] == "test"


def test_archive_market_mappings_writes_jsonl(monkeypatch, tmp_path):
    archive_root = tmp_path / "archives"
    monkeypatch.setenv("AZP_LOCAL_ARCHIVE_DIR", str(archive_root))

    result = archive_market_mappings(
        {
            "matchup": "Blue Jays vs Angels",
            "marketMap": [{"stakeDisplayName": "Hits"}],
        }
    )

    assert result["saved"] is True
    archive_file = next((archive_root / "market_mappings").glob("*.jsonl"))
    record = json.loads(archive_file.read_text(encoding="utf-8").strip())
    assert record["recordType"] == "market_mapping"
    assert record["marketMap"] == [{"stakeDisplayName": "Hits"}]
