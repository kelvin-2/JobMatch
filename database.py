import os
import httpx
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("SUPABASE_URL").strip()
KEY = os.getenv("SUPABASE_KEY").strip()

HEADERS = {
    "apikey":        KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

TIMEOUT = 15.0   # slightly more generous for slow Supabase cold starts


# ═══════════════════════════════════════════════════════════════════════════════
#  LOW-LEVEL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _get(table: str, params: dict = {}) -> list:
    try:
        r = httpx.get(
            f"{URL}/rest/v1/{table}",
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except httpx.ReadTimeout:
        print(f"[DB] Timeout fetching '{table}'")
        return []
    except httpx.HTTPStatusError as e:
        print(f"[DB] HTTP {e.response.status_code} fetching '{table}': {e}")
        return []
    except Exception as e:
        print(f"[DB] Unexpected error fetching '{table}': {e}")
        return []


def _post(table: str, data) -> None:
    try:
        r = httpx.post(
            f"{URL}/rest/v1/{table}",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=data,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except httpx.ReadTimeout:
        print(f"[DB] Timeout posting to '{table}'.")
    except httpx.HTTPStatusError as e:
        print(f"[DB] HTTP {e.response.status_code} posting to '{table}': {e.response.text}")
    except Exception as e:
        print(f"[DB] Error posting to '{table}': {e}")


def _patch(table: str, data: dict, match: dict) -> None:
    try:
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = httpx.patch(
            f"{URL}/rest/v1/{table}",
            headers=HEADERS,
            params=params,
            json=data,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except httpx.ReadTimeout:
        print(f"[DB] Timeout patching '{table}'.")
    except httpx.HTTPStatusError as e:
        print(f"[DB] HTTP {e.response.status_code} patching '{table}': {e.response.text}")
    except Exception as e:
        print(f"[DB] Error patching '{table}': {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  JOBS
# ═══════════════════════════════════════════════════════════════════════════════

def save_jobs(jobs: list) -> None:
    if not jobs:
        return
    filtered = [
        {
            "title":        j.get("title",        ""),
            "company":      j.get("company",      ""),
            "location":     j.get("location",     ""),
            "salary":       j.get("salary",       ""),
            "closing_date": j.get("closing_date", ""),
            "requirements": j.get("requirements", ""),
            "description":  j.get("description",  ""),
            "url":          j.get("url",          ""),
            "apply_url":    j.get("apply_url",    ""),
            "job_type":     j.get("job_type",     ""),
        }
        for j in jobs if j.get("url")
    ]
    if filtered:
        _post("jobs", filtered)
        print(f"[DB] Saved {len(filtered)} jobs.")


def get_all_jobs() -> list:
    """Return every job in the jobs table, newest first."""
    return _get("jobs", {"select": "*", "order": "id.desc"})


# ═══════════════════════════════════════════════════════════════════════════════
#  MATCHED JOBS
# ═══════════════════════════════════════════════════════════════════════════════

def save_matches(matches: list) -> None:
    if not matches:
        return
    filtered = [
        {
            "job_url":     m.get("url",         ""),
            "match_score": m.get("match_score", 0),
            "match_pct":   m.get("match_pct",   "0%"),
            "job_type":    m.get("job_type",    ""),
            "status":      "new",
        }
        for m in matches if m.get("url")
    ]
    if filtered:
        _post("matched_jobs", filtered)
        print(f"[DB] Saved {len(filtered)} matches.")


def get_jobs_by_status(status: str) -> list:
    """
    Return matched_jobs rows for a given status, with their parent job data
    joined in and flattened to a single dict per row.
    """
    results = _get("matched_jobs", {
        "status": f"eq.{status}",
        "select": "*,jobs(*)",
        "order":  "match_score.desc",
    })
    flattened = []
    for row in results:
        job_data = row.pop("jobs", {}) or {}
        flattened.append({**job_data, **row})
    return flattened


def update_status(job_url: str, status: str) -> None:
    """Change the status of a matched job (new → saved → applied → rejected)."""
    _patch("matched_jobs", {"status": status}, {"job_url": job_url})


def update_notes(job_url: str, notes: str) -> None:
    """
    Save free-text notes against a matched job.
    Requires a `notes` TEXT column in the matched_jobs table.

    Run this once in Supabase SQL editor if the column doesn't exist:
        ALTER TABLE matched_jobs ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT '';
    """
    _patch("matched_jobs", {"notes": notes}, {"job_url": job_url})


# ═══════════════════════════════════════════════════════════════════════════════
#  APPLICATION TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_applications() -> list:
    """
    Return all jobs the user has applied to or saved, joined with job details,
    ordered by most-recently updated first.

    Requires an `updated_at` column in matched_jobs (auto-managed by Supabase
    if you enable it, or add manually):
        ALTER TABLE matched_jobs
          ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
        CREATE OR REPLACE FUNCTION update_updated_at()
          RETURNS TRIGGER LANGUAGE plpgsql AS $$
          BEGIN NEW.updated_at = now(); RETURN NEW; END;
          $$;
        DROP TRIGGER IF EXISTS set_updated_at ON matched_jobs;
        CREATE TRIGGER set_updated_at
          BEFORE UPDATE ON matched_jobs
          FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """
    results = _get("matched_jobs", {
        "status":  "in.(applied,saved)",
        "select":  "*,jobs(*)",
        "order":   "updated_at.desc.nullslast",
    })
    flattened = []
    for row in results:
        job_data = row.pop("jobs", {}) or {}
        flattened.append({**job_data, **row})
    return flattened


def get_applied_jobs() -> list:
    """Shortcut — only the applied subset."""
    return get_jobs_by_status("applied")


def get_saved_jobs() -> list:
    """Shortcut — only the saved subset."""
    return get_jobs_by_status("saved")


# ═══════════════════════════════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════════════════════════════

def get_stats() -> dict:
    """
    Return counts for the dashboard stat bar.
    Uses HEAD requests with count=exact to avoid fetching all rows.
    """
    def _count(table: str, params: dict = {}) -> int:
        try:
            r = httpx.get(
                f"{URL}/rest/v1/{table}",
                headers={**HEADERS, "Prefer": "count=exact"},
                params={"select": "id", **params},
                timeout=TIMEOUT,
            )
            # Supabase returns count in the Content-Range header: "0-9/42"
            cr = r.headers.get("content-range", "0/0")
            return int(cr.split("/")[-1])
        except Exception:
            return 0

    return {
        "total_scraped": _count("jobs"),
        "new":           _count("matched_jobs", {"status": "eq.new"}),
        "saved":         _count("matched_jobs", {"status": "eq.saved"}),
        "applied":       _count("matched_jobs", {"status": "eq.applied"}),
        "rejected":      _count("matched_jobs", {"status": "eq.rejected"}),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  PROFILE  (stored in Supabase so it survives redeploys)
# ═══════════════════════════════════════════════════════════════════════════════

def get_profile() -> dict:
    result = _get("profile", {"id": "eq.1"})
    return result[0] if isinstance(result, list) and result else {}


def save_profile(profile: dict) -> None:
    _post("profile", {**profile, "id": 1})