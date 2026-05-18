from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_WINDOWS_ARCHIVE_ROOT = Path("D:/AZP_Data/archives")


def archive_status() -> dict[str, Any]:
    root = _archive_root()
    if root is None:
        return {
            "enabled": False,
            "available": False,
            "path": None,
            "warning": "Set AZP_LOCAL_ARCHIVE_DIR or create D:\\AZP_Data\\archives to enable local HDD archiving.",
        }

    try:
        root.mkdir(parents=True, exist_ok=True)
        _ensure_archive_dirs(root)
    except OSError as exc:
        return {
            "enabled": True,
            "available": False,
            "path": str(root),
            "warning": f"Local archive path is not writable: {exc}",
        }

    return {
        "enabled": True,
        "available": True,
        "path": str(root),
        "warning": None,
    }


def archive_gpt_decision(
    response: dict[str, Any],
    request_body: dict[str, Any],
    *,
    decision_id: str,
) -> dict[str, Any]:
    return _append_archive_record(
        folder_name="gpt_decisions",
        record={
            "recordType": "gpt_decision",
            "decisionId": decision_id,
            "capturedAt": _utc_now(),
            "request": request_body,
            "response": response,
        },
    )


def archive_market_mappings(response: dict[str, Any]) -> dict[str, Any]:
    return _append_archive_record(
        folder_name="market_mappings",
        record={
            "recordType": "market_mapping",
            "capturedAt": _utc_now(),
            "matchup": response.get("matchup"),
            "date": response.get("date"),
            "marketMap": response.get("marketMap") or [],
        },
    )


def _append_archive_record(folder_name: str, record: dict[str, Any]) -> dict[str, Any]:
    status = archive_status()
    if not status["enabled"] or not status["available"]:
        return {
            **status,
            "saved": False,
        }

    root = Path(status["path"])
    archive_file = root / folder_name / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"
    try:
        with archive_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    except OSError as exc:
        return {
            "enabled": True,
            "available": False,
            "path": str(root),
            "saved": False,
            "warning": f"Local archive write failed: {exc}",
        }

    return {
        **status,
        "saved": True,
        "file": str(archive_file),
    }


def _archive_root() -> Path | None:
    configured = os.getenv("AZP_LOCAL_ARCHIVE_DIR")
    if configured:
        return Path(configured)

    if os.name == "nt" and DEFAULT_WINDOWS_ARCHIVE_ROOT.exists():
        return DEFAULT_WINDOWS_ARCHIVE_ROOT

    return None


def _ensure_archive_dirs(root: Path) -> None:
    for folder_name in ("gpt_decisions", "market_mappings"):
        (root / folder_name).mkdir(parents=True, exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
