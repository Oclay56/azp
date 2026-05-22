from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_LOCAL_UI_JOB_TABLE = "local_ui_jobs"
DEFAULT_JOB_RETENTION_HOURS = 6.0
DEFAULT_STALE_RUNNING_MINUTES = 15.0


@dataclass(frozen=True)
class CleanupOperation:
    name: str
    method: str
    filters: dict[str, str]
    payload: dict[str, Any] | None = None


def cleanup_operations(
    *,
    now: datetime,
    retention_hours: float = DEFAULT_JOB_RETENTION_HOURS,
    stale_running_minutes: float = DEFAULT_STALE_RUNNING_MINUTES,
) -> list[CleanupOperation]:
    now_text = _utc_iso(now)
    stale_cutoff = _utc_iso(now - timedelta(minutes=max(stale_running_minutes, 1.0)))
    old_cutoff = _utc_iso(now - timedelta(hours=max(retention_hours, 0.25)))
    expired_payload = {
        "status": "expired",
        "error_message": "Expired by AZP Supabase cache cleanup.",
        "completed_at": now_text,
        "updated_at": now_text,
    }

    return [
        CleanupOperation(
            name="expire pending/running jobs past expires_at",
            method="PATCH",
            filters={
                "status": "in.(pending,running)",
                "expires_at": f"lt.{now_text}",
            },
            payload=expired_payload,
        ),
        CleanupOperation(
            name="expire stale running jobs",
            method="PATCH",
            filters={
                "status": "eq.running",
                "updated_at": f"lt.{stale_cutoff}",
            },
            payload=expired_payload,
        ),
        CleanupOperation(
            name="delete jobs past expires_at",
            method="DELETE",
            filters={
                "expires_at": f"lt.{now_text}",
            },
        ),
        CleanupOperation(
            name="delete old completed/failed/expired jobs",
            method="DELETE",
            filters={
                "status": "in.(completed,failed,expired)",
                "updated_at": f"lt.{old_cutoff}",
            },
        ),
    ]


def run_cleanup(
    *,
    supabase_url: str,
    service_key: str,
    table_name: str = DEFAULT_LOCAL_UI_JOB_TABLE,
    retention_hours: float = DEFAULT_JOB_RETENTION_HOURS,
    stale_running_minutes: float = DEFAULT_STALE_RUNNING_MINUTES,
    dry_run: bool = False,
) -> dict[str, Any]:
    table_url = f"{supabase_url.rstrip('/')}/rest/v1/{table_name}"
    headers = _headers(service_key)
    operations = cleanup_operations(
        now=datetime.now(timezone.utc),
        retention_hours=retention_hours,
        stale_running_minutes=stale_running_minutes,
    )
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        for operation in operations:
            matched = _count_rows(client, table_url, headers, operation.filters)
            changed = 0
            if not dry_run and matched:
                _apply_operation(client, table_url, headers, operation)
                changed = matched
            results.append(
                {
                    "operation": operation.name,
                    "method": operation.method,
                    "matched": matched,
                    "changed": changed,
                }
            )

    return {
        "table": table_name,
        "dryRun": dry_run,
        "retentionHours": retention_hours,
        "staleRunningMinutes": stale_running_minutes,
        "expiredJobs": sum(item["changed"] for item in results if item["method"] == "PATCH"),
        "deletedJobs": sum(item["changed"] for item in results if item["method"] == "DELETE"),
        "operations": results,
    }


def _count_rows(
    client: httpx.Client,
    table_url: str,
    headers: dict[str, str],
    filters: dict[str, str],
) -> int:
    response = client.get(
        table_url,
        params={"select": "job_id", **filters},
        headers={
            **headers,
            "Prefer": "count=exact",
            "Range": "0-0",
        },
    )
    _raise_for_supabase_error(response, "count")
    return _content_range_total(response.headers.get("content-range"))


def _apply_operation(
    client: httpx.Client,
    table_url: str,
    headers: dict[str, str],
    operation: CleanupOperation,
) -> None:
    request_headers = {**headers, "Prefer": "return=minimal"}
    if operation.method == "PATCH":
        response = client.patch(
            table_url,
            params=operation.filters,
            headers=request_headers,
            json=operation.payload or {},
        )
    elif operation.method == "DELETE":
        response = client.delete(
            table_url,
            params=operation.filters,
            headers=request_headers,
        )
    else:
        raise ValueError(f"Unsupported cleanup method: {operation.method}")
    _raise_for_supabase_error(response, operation.name)


def _headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def _content_range_total(value: str | None) -> int:
    if not value or "/" not in value:
        return 0
    total = value.rsplit("/", 1)[-1].strip()
    if total == "*":
        return 0
    try:
        return int(total)
    except ValueError:
        return 0


def _raise_for_supabase_error(response: httpx.Response, action: str) -> None:
    if response.status_code < 400:
        return
    raise RuntimeError(
        f"Supabase cache cleanup failed during {action}: "
        f"{response.status_code} {response.text}"
    )


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path.cwd() / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(
        description="Clean old AZP local UI bridge rows from Supabase.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count rows without deleting.")
    parser.add_argument(
        "--retention-hours",
        type=float,
        default=_env_float("AZP_SUPABASE_JOB_RETENTION_HOURS", DEFAULT_JOB_RETENTION_HOURS),
        help="Keep completed/failed/expired UI jobs newer than this many hours.",
    )
    parser.add_argument(
        "--stale-running-minutes",
        type=float,
        default=_env_float(
            "AZP_SUPABASE_STALE_JOB_MINUTES",
            DEFAULT_STALE_RUNNING_MINUTES,
        ),
        help="Mark running UI jobs older than this many minutes as expired.",
    )
    parser.add_argument(
        "--table",
        default=os.getenv("AZP_LOCAL_UI_JOB_TABLE", DEFAULT_LOCAL_UI_JOB_TABLE),
        help="Supabase local UI job table name.",
    )
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not service_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required in .env.")
        return 1

    result = run_cleanup(
        supabase_url=supabase_url,
        service_key=service_key,
        table_name=args.table,
        retention_hours=args.retention_hours,
        stale_running_minutes=args.stale_running_minutes,
        dry_run=args.dry_run,
    )

    print("AZP Supabase cache cleanup")
    print("--------------------------")
    print(f"Table: {result['table']}")
    print(f"Mode: {'dry run' if result['dryRun'] else 'cleanup'}")
    print(f"Retention: {result['retentionHours']} hours")
    print(f"Stale running cutoff: {result['staleRunningMinutes']} minutes")
    print()
    for operation in result["operations"]:
        verb = "would change" if result["dryRun"] else "changed"
        print(
            f"- {operation['operation']}: matched {operation['matched']}, "
            f"{verb} {operation['changed']}"
        )
    print()
    print(f"Expired jobs: {result['expiredJobs']}")
    print(f"Deleted jobs: {result['deletedJobs']}")
    print("Kept: pending fresh jobs and GPT decision ledger rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
