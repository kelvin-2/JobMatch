import json


def load_profile(path: str = "profile.json") -> dict:
    with open(path) as f:
        return json.load(f)


def compute_match_score(job: dict, profile: dict) -> float:
    """
    Score a job against john's profile.
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
    job_location  = job.get("location", "").lower()
    user_location = profile.get("location", "").lower()
    if user_location in job_location:
        score += 0.20
    elif "remote" in job_location:
        score += 0.15
    elif profile.get("accept_remote") and "remote" in full_text:
        score += 0.10

    return round(score, 2)


def filter_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    min_score        = profile.get("min_match_score", 0.10)
    blocked_titles   = [t.lower() for t in profile.get("blocked_job_titles", [])]
    required_fields  = [k.lower() for k in profile.get("required_field_keywords", [])]
    disqualifying    = [k.lower() for k in profile.get("disqualifying_keywords", [])]
    target_job_types = [t.lower() for t in profile.get("target_job_types", [])]

    matched = []
    rejected_counts = {
        "blocked_title": 0,
        "no_field_match": 0,
        "disqualified": 0,
        "low_score": 0
    }

    for job in jobs:
        title       = job.get("title", "").lower()
        description = job.get("description", "").lower()
        combined    = title + " " + description

        # 1. Hard reject — blocked job titles
        if any(blocked in title for blocked in blocked_titles):
            rejected_counts["blocked_title"] += 1
            continue

        # 2. Hard reject — must relate to your field
        if required_fields and not any(kw in combined for kw in required_fields):
            rejected_counts["no_field_match"] += 1
            continue

        # 3. Hard reject — disqualifying keywords (too senior/experienced)
        if any(kw in combined for kw in disqualifying):
            rejected_counts["disqualified"] += 1
            continue

        # 4. Skip unwanted job types
        job_type = job.get("job_type", "").lower()
        if "internship" in job_type and not profile.get("accept_internships"):
            continue
        if "learnership" in job_type and not profile.get("accept_learnerships"):
            continue

        # 5. Compute base score
        score = compute_match_score(job, profile)

        # 5a. Boost if it matches a target job type
        if any(t in combined for t in target_job_types):
            score = min(score + 0.10, 1.0)

        # 5b. Boost if title signals relevance to your field
        title_keywords = [
            "graduate", "technology", "data", "it", "computer",
            "software", "cyber", "analytics", "digital", "risk",
            "information", "systems", "developer", "engineering"
        ]
        if any(kw in title for kw in title_keywords):
            score = min(score + 0.15, 1.0)

        # 6. Score threshold
        if score < min_score:
            rejected_counts["low_score"] += 1
            continue

        job["match_score"] = round(score, 2)
        job["match_pct"]   = f"{int(score * 100)}%"
        job["status"]      = "new"
        matched.append(job)

    matched.sort(key=lambda x: x["match_score"], reverse=True)

    print(f"[Matcher] Scraped: {len(jobs)} | Matched: {len(matched)}")
    print(f"[Matcher] Rejected → blocked title: {rejected_counts['blocked_title']} | "
          f"wrong field: {rejected_counts['no_field_match']} | "
          f"too senior: {rejected_counts['disqualified']} | "
          f"low score: {rejected_counts['low_score']}")

    return matched