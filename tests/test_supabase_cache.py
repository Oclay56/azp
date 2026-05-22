from __future__ import annotations

from datetime import datetime, timezone

from app.supabase_cache import _content_range_total, cleanup_operations


def test_cleanup_operations_only_target_local_ui_cache_rows():
    operations = cleanup_operations(
        now=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
        retention_hours=6,
        stale_running_minutes=15,
    )

    names = [operation.name for operation in operations]
    assert names == [
        "expire pending/running jobs past expires_at",
        "expire stale running jobs",
        "delete jobs past expires_at",
        "delete old completed/failed/expired jobs",
    ]
    assert operations[0].filters == {
        "status": "in.(pending,running)",
        "expires_at": "lt.2026-05-21T12:00:00Z",
    }
    assert operations[1].filters == {
        "status": "eq.running",
        "updated_at": "lt.2026-05-21T11:45:00Z",
    }
    assert operations[2].filters == {
        "expires_at": "lt.2026-05-21T12:00:00Z",
    }
    assert operations[3].filters == {
        "status": "in.(completed,failed,expired)",
        "updated_at": "lt.2026-05-21T06:00:00Z",
    }


def test_content_range_total_handles_postgrest_headers():
    assert _content_range_total("0-0/23") == 23
    assert _content_range_total("*/0") == 0
    assert _content_range_total(None) == 0
    assert _content_range_total("bad") == 0
