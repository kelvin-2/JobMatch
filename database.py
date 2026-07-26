import os
import httpx
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("SUPABASE_URL").strip()
KEY = os.getenv("SUPABASE_KEY").strip()

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

TIMEOUT = 10.0


def _get(table: str, params: dict = {}) -> list:
    try:
        r = httpx.get(f"{URL}/rest/v1/{table}", headers=HEADERS, params=params, timeout=TIMEOUT)
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
        httpx.post(
            f"{URL}/rest/v1/{table}",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=data,
            timeout=TIMEOUT
        )
    except httpx.ReadTimeout:
        print(f"[DB] Timeout posting to '{table}'.")
    except Exception as e:
        print(f"[DB] Error posting to '{table}': {e}")


def _patch(table: str, data: dict, match: dict) -> None:
    try:
        params = {k: f"eq.{v}" for k, v in match.items()}
        httpx.patch(f"{URL}/rest/v1/{table}", headers=HEADERS, params=params, json=data, timeout=TIMEOUT)
    except httpx.ReadTimeout:
        print(f"[DB] Timeout patching '{table}'.")
    except Exception as e:
        print(f"[DB] Error patching '{table}': {e}")


def save_jobs(jobs: list) -> None:
    if not jobs:
        return
    filtered = [
        {
            "title":        j.get("title", ""),
            "company":      j.get("company", ""),
            "location":     j.get("location", ""),
            "salary":       j.get("salary", ""),
            "closing_date": j.get("closing_date", ""),
            "requirements": j.get("requirements", ""),
            "description":  j.get("description", ""),
            "url":          j.get("url", ""),
            "apply_url":    j.get("apply_url", ""),
            "job_type":     j.get("job_type", ""),
        }
        for j in jobs if j.get("url")
    ]
    _post("jobs", filtered)
    print(f"Saved {len(filtered)} jobs.")


def save_matches(matches: list) -> None:
    if not matches:
        return
    filtered = [
        {
            "job_url":     m.get("url", ""),
            "match_score": m.get("match_score", 0),
            "match_pct":   m.get("match_pct", "0%"),
            "job_type":    m.get("job_type", ""),
            "status":      "new",
        }
        for m in matches if m.get("url")
    ]
    _post("matched_jobs", filtered)
    print(f"Saved {len(filtered)} matches.")


def get_all_jobs() -> list:
    return _get("jobs", {"select": "*"})


def get_jobs_by_status(status: str) -> list:
    results = _get("matched_jobs", {
        "status": f"eq.{status}",
        "select": "*,jobs(*)",
        "order":  "match_score.desc"
    })
    # Flatten nested jobs data into top level
    flattened = []
    for row in results:
        job_data = row.pop("jobs", {}) or {}
        flattened.append({**job_data, **row})
    return flattened


def update_status(job_url: str, status: str) -> None:
    _patch("matched_jobs", {"status": status}, {"job_url": job_url})


def get_stats() -> dict:
    total   = _get("jobs",         {"select": "id"})
    new     = _get("matched_jobs", {"status": "eq.new",     "select": "id"})
    applied = _get("matched_jobs", {"status": "eq.applied", "select": "id"})
    saved   = _get("matched_jobs", {"status": "eq.saved",   "select": "id"})
    return {
        "total_scraped": len(total)   if isinstance(total, list) else 0,
        "new":           len(new)     if isinstance(new, list)   else 0,
        "applied":       len(applied) if isinstance(applied, list) else 0,
        "saved":         len(saved)   if isinstance(saved, list) else 0,
    }


def get_profile() -> dict:
    result = _get("profile", {"id": "eq.1"})
    return result[0] if isinstance(result, list) and result else {}


def save_profile(profile: dict) -> None:
    _post("profile", {**profile, "id": 1})