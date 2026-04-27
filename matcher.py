import json


def load_profile(path: str = "profile.json") -> dict:
    with open(path) as f:
        return json.load(f)


def compute_match_score(job: dict, profile: dict) -> float:
    """
    Score a job against Kelvin's profile.
    Returns 0.0 – 1.0

    Breakdown:
    - Degree/field match:  0.40
    - Skills match:        0.40
    - Location match:      0.20
    """
    full_text = " ".join([
        job.get("title", ""),
        job.get("description", ""),
        job.get("requirements", ""),
        job.get("company", ""),
    ]).lower()

    score = 0.0

    # 1. Degree match (0 – 0.40)
    degree_keywords = [k.lower() for k in profile.get("degree_keywords", [])]
    matched_degree  = [k for k in degree_keywords if k in full_text]
    score += min(len(matched_degree) / max(len(degree_keywords), 1), 1.0) * 0.40

    # 2. Skills match (0 – 0.40)
    skills         = [s.lower() for s in profile.get("skills", [])]
    matched_skills = [s for s in skills if s in full_text]
    score += min(len(matched_skills) / max(len(skills), 1), 1.0) * 0.40

    # 3. Location match (0 – 0.20)
    job_location = job.get("location", "").lower()
    user_location = profile.get("location", "").lower()
    if user_location in job_location:
        score += 0.20
    elif "remote" in job_location:
        score += 0.15
    elif profile.get("accept_remote") and "remote" in full_text:
        score += 0.10

    return round(score, 2)


def filter_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    """
    Score all jobs and return sorted matched list.
    Filters out jobs below min_match_score in profile.
    """
    min_score = profile.get("min_match_score", 0.25)
    matched = []

    for job in jobs:
        # Skip job types Kelvin doesn't want
        job_type = job.get("job_type", "")
        if job_type == "Internship" and not profile.get("accept_internships"):
            continue
        if job_type == "Learnership" and not profile.get("accept_learnerships"):
            continue

        score = compute_match_score(job, profile)

        if score >= min_score:
            job["match_score"] = score
            job["match_pct"]   = f"{int(score * 100)}%"
            job["status"]      = "new"
            matched.append(job)

    # Sort best match first
    matched.sort(key=lambda x: x["match_score"], reverse=True)
    print(f"Matched {len(matched)} jobs out of {len(jobs)} scraped.")
    return matched