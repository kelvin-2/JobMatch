import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def init_db():
    """Run this once to create all tables in Supabase."""
    print("Database connected successfully.")


def save_jobs(jobs: list[dict]):
    """Save scraped jobs — skips duplicates based on URL."""
    if not jobs:
        print("No jobs to save.")
        return
    response = supabase.table("jobs").upsert(jobs, on_conflict="url").execute()
    print(f"Saved {len(jobs)} jobs to database.")
    return response


def save_matches(matches: list[dict]):
    """Save matched jobs with score."""
    if not matches:
        print("No matches to save.")
        return
    supabase.table("matched_jobs").upsert(matches, on_conflict="job_url").execute()
    print(f"Saved {len(matches)} matches.")


def get_jobs_by_status(status: str) -> list[dict]:
    """Get matched jobs filtered by application status."""
    response = (
        supabase.table("matched_jobs")
        .select("*, jobs(*)")
        .eq("status", status)
        .order("match_score", desc=True)
        .execute()
    )
    return response.data


def update_status(job_url: str, status: str):
    """Update a job status — new / saved / applied / skipped."""
    supabase.table("matched_jobs").update({"status": status}).eq("job_url", job_url).execute()


def get_stats() -> dict:
    """Return counts for the dashboard stat chips."""
    total   = supabase.table("jobs").select("id", count="exact").execute().count
    new     = supabase.table("matched_jobs").select("id", count="exact").eq("status", "new").execute().count
    applied = supabase.table("matched_jobs").select("id", count="exact").eq("status", "applied").execute().count
    saved   = supabase.table("matched_jobs").select("id", count="exact").eq("status", "saved").execute().count

    return {
        "total_scraped": total or 0,
        "new":           new or 0,
        "applied":       applied or 0,
        "saved":         saved or 0,
    }


def save_profile(profile: dict):
    """Save updated profile from the UI."""
    supabase.table("profile").upsert({"id": 1, **profile}).execute()


def get_profile() -> dict:
    """Load Kelvin's profile."""
    response = supabase.table("profile").select("*").eq("id", 1).execute()
    return response.data[0] if response.data else {}