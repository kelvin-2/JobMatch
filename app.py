import os
import json
import threading
import time
import random
import traceback
import requests

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "kelvin-jobmatch-2025")

# ── Login setup ───────────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login"

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "changeme")
UPLOAD_FOLDER      = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}
APP_URL            = os.getenv("APP_URL", "http://localhost:5000")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ── Scraper state (module-level, shared across threads) ───────────────────────
scraper_running    = False
scraper_error      = None   # last error message, shown in UI
last_scrape_time   = None   # "YYYY-MM-DD HH:MM:SS"
last_scrape_stats  = {}     # {"jobs": N, "matched": M}
scraper_lock       = threading.Lock()

# ── Auth ──────────────────────────────────────────────────────────────────────
class User(UserMixin):
    id = "kelvin"

@login_manager.user_loader
def load_user(user_id):
    return User() if user_id == "kelvin" else None

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ═══════════════════════════════════════════════════════════════════════════════
#  PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline():
    """
    Full scrape → clean → match → save cycle.
    - Thread-safe (scraper_lock prevents concurrent runs).
    - Captures and stores any crash so /scraper-status can report it.
    """
    global scraper_running, scraper_error, last_scrape_time, last_scrape_stats

    # ── Guard: only one run at a time ─────────────────────────────────────────
    acquired = scraper_lock.acquire(blocking=False)
    if not acquired:
        print("[Pipeline] Already running — skipping duplicate trigger.")
        return

    scraper_running = True
    scraper_error   = None
    print("[Pipeline] ▶ Starting...")

    try:
        from scraper  import scrape_page, get_driver, CATEGORIES
        from cleaner  import clean_jobs
        from matcher  import load_profile, filter_jobs
        from database import save_jobs, save_matches

        profile       = load_profile()
        max_pages     = 50
        seen_urls     = set()
        total_jobs    = 0
        total_matched = 0

        driver = get_driver()
        try:
            for category in CATEGORIES:
                print(f"\n[Pipeline] Category: {category}")
                for page in range(1, max_pages + 1):
                    raw = scrape_page(driver, category, page, seen_urls)
                    if not raw:
                        print(f"[Pipeline]   └─ no more results on page {page}, moving to next category.")
                        break
                    cleaned  = clean_jobs(raw)
                    matched  = filter_jobs(cleaned, profile)
                    save_jobs(cleaned)
                    save_matches(matched)
                    total_jobs    += len(cleaned)
                    total_matched += len(matched)
                    print(f"[Pipeline]   Page {page}: saved {len(cleaned)}, matched {len(matched)}")
                    time.sleep(random.uniform(2, 3))
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        from datetime import datetime
        last_scrape_time  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_scrape_stats = {"jobs": total_jobs, "matched": total_matched}
        print(f"[Pipeline] ✔ Done — {total_matched} matched from {total_jobs} total.")

    except Exception as e:
        scraper_error = traceback.format_exc()
        print(f"[Pipeline] ✘ CRASHED:\n{scraper_error}")

    finally:
        scraper_running = False
        scraper_lock.release()


# ── Startup re-match ──────────────────────────────────────────────────────────
def startup_rematch():
    try:
        from matcher  import load_profile, filter_jobs
        from database import get_all_jobs, save_matches
        jobs = get_all_jobs()
        if not jobs:
            print("[Startup] No jobs in DB yet.")
            return
        profile = load_profile()
        matched = filter_jobs(jobs, profile)
        save_matches(matched)
        print(f"[Startup] Re-matched {len(matched)} of {len(jobs)} jobs.")
    except Exception as e:
        print(f"[Startup] Rematch error: {e}")


# ── Self-ping ─────────────────────────────────────────────────────────────────
def self_ping():
    try:
        r = requests.get(f"{APP_URL}/ping", timeout=10)
        print(f"[Ping] {r.status_code}")
    except Exception as e:
        print(f"[Ping] Failed: {e}")


# ── Scheduler listener ────────────────────────────────────────────────────────
def on_job_event(event):
    if event.exception:
        print(f"[Scheduler] {event.job_id} CRASHED: {event.exception}")
    else:
        print(f"[Scheduler] {event.job_id} OK.")


# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# ── Keep-alive (no auth) ──────────────────────────────────────────────────────
@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "alive": True}), 200


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == DASHBOARD_PASSWORD:
            login_user(User())
            return redirect(url_for("dashboard"))
        flash("Wrong password — try again.")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    from database import get_jobs_by_status, get_stats
    jobs  = get_jobs_by_status("new")
    stats = get_stats()
    return render_template(
        "dashboard.html",
        jobs=jobs,
        stats=stats,
        scraper_just_started=False,
        scraper_running=scraper_running,
        scraper_error=scraper_error,
        last_scrape_time=last_scrape_time,
        last_scrape_stats=last_scrape_stats,
    )


# ── Saved ─────────────────────────────────────────────────────────────────────
@app.route("/saved")
@login_required
def saved():
    from database import get_jobs_by_status, get_stats
    jobs  = get_jobs_by_status("saved")
    stats = get_stats()
    return render_template("saved.html", jobs=jobs, stats=stats)


# ── Tracker ───────────────────────────────────────────────────────────────────
@app.route("/tracker")
@login_required
def tracker():
    from database import get_jobs_by_status, get_stats
    applied = get_jobs_by_status("applied")
    saved   = get_jobs_by_status("saved")
    stats   = get_stats()
    try:
        from database import get_all_applications
        all_applications = get_all_applications()
    except Exception:
        all_applications = applied
    return render_template(
        "tracker.html",
        applied=applied,
        saved=saved,
        all_applications=all_applications,
        stats=stats,
    )


# ── All jobs (full DB) ────────────────────────────────────────────────────────
@app.route("/all-jobs")
@login_required
def all_jobs():
    from database import get_all_jobs, get_stats
    jobs  = get_all_jobs()
    stats = get_stats()
    return render_template("all_jobs.html", jobs=jobs, stats=stats)


# ── Profile ───────────────────────────────────────────────────────────────────
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        updated = {
            "name":                request.form.get("name"),
            "university":          request.form.get("university"),
            "degree":              request.form.get("degree"),
            "graduation_year":     int(request.form.get("graduation_year", 2025)),
            "location":            request.form.get("location"),
            "accept_remote":       "accept_remote"       in request.form,
            "accept_internships":  "accept_internships"  in request.form,
            "accept_learnerships": "accept_learnerships" in request.form,
            "min_match_score":     0.10,
            "skills":          [s.strip() for s in request.form.get("skills",          "").split(",") if s.strip()],
            "degree_keywords": [k.strip() for k in request.form.get("degree_keywords", "").split(",") if k.strip()],
            "required_field_keywords": [
                "software", "developer", "programming", "coding", "computer science",
                "systems", "application", "backend", "frontend", "full stack",
                "web development", "mobile development", "IT", "information technology",
                "cloud", "DevOps", "database", "SQL", "API", "machine learning", "AI",
                "artificial intelligence", "data structures", "algorithms",
                "data analyst", "data science", "data engineer", "business intelligence",
                "statistics", "statistical", "analytics", "reporting", "Power BI",
                "Tableau", "R programming", "Python", "data modelling", "quantitative",
                "cybersecurity", "cyber security", "information security", "infosec",
                "penetration testing", "pentesting", "ethical hacking", "SOC",
                "security analyst", "network security", "vulnerability", "SIEM",
                "incident response", "threat", "firewall", "encryption", "compliance",
                "risk assessment", "security operations", "blue team", "red team",
                "OSINT", "malware analysis", "digital forensics",
            ],
            "blocked_job_titles": [
                "clerk", "cashier", "driver", "cleaner", "security guard",
                "receptionist", "waiter", "waitress", "sales assistant", "store assistant",
                "picker", "packer", "admin assistant", "call centre agent", "call center",
                "domestic", "general worker", "labourer", "teller", "shelf packer",
                "merchandiser", "forklift", "warehouse", "delivery", "housekeeper",
                "petrol attendant", "plumber", "electrician", "artisan", "mechanic",
                "nursing", "caregiver", "social worker", "teacher", "educator",
            ],
            "target_job_types": [
                "graduate programme", "graduate program", "entry level",
                "entry-level", "junior", "trainee", "internship",
                "learnership", "graduate trainee", "management trainee",
                "no experience required", "fresh graduate", "recent graduate",
                "0-1 years", "0 to 1 year", "junior developer", "junior analyst",
                "junior security", "SOC analyst", "security graduate",
            ],
            "disqualifying_keywords": [
                "5 years", "5+ years", "senior", "head of", "director",
                "principal", "minimum 3 years", "minimum 5 years",
                "CISSP required", "CISM required", "10 years",
            ],
        }
        with open("profile.json", "w") as f:
            json.dump(updated, f, indent=2)
        flash("Profile saved! Changes apply on the next scrape.")
        return redirect(url_for("profile"))

    with open("profile.json") as f:
        current = json.load(f)
    return render_template("profile.html", profile=current)


# ── CV ────────────────────────────────────────────────────────────────────────
@app.route("/cv", methods=["GET", "POST"])
@login_required
def cv():
    cv_path = os.path.join(app.config["UPLOAD_FOLDER"], "kelvin_cv.pdf")
    if request.method == "POST":
        file = request.files.get("cv_file")
        if file and allowed_file(file.filename):
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            file.save(cv_path)
            flash("CV uploaded successfully.")
            return redirect(url_for("cv"))
        flash("Please upload a PDF file only.")
    cv_file = None
    if os.path.exists(cv_path):
        cv_file = {"name": "kelvin_cv.pdf", "size": f"{round(os.path.getsize(cv_path)/1024,1)} KB"}
    return render_template("cv.html", cv_file=cv_file)


@app.route("/download-cv")
@login_required
def download_cv():
    from flask import send_from_directory
    return send_from_directory(app.config["UPLOAD_FOLDER"], "kelvin_cv.pdf", as_attachment=True)


# ── AJAX: update job status ───────────────────────────────────────────────────
@app.route("/update-status", methods=["POST"])
@login_required
def update_status():
    from database import update_status as db_update
    data = request.get_json()
    db_update(data.get("url"), data.get("status"))
    return jsonify({"ok": True})


# ── AJAX: update notes ────────────────────────────────────────────────────────
@app.route("/update-notes", methods=["POST"])
@login_required
def update_notes():
    try:
        from database import update_notes as db_update_notes
        data = request.get_json()
        db_update_notes(data.get("url"), data.get("notes", ""))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── AJAX: scraper status poll ─────────────────────────────────────────────────
@app.route("/scraper-status")
@login_required
def scraper_status():
    """
    Polled by the frontend every N seconds.
    Returns the real scraper state — frontend must NOT trigger /run-scraper
    from inside this poll loop.
    """
    from database import get_stats
    return jsonify({
        "running":           scraper_running,
        "error":             scraper_error,
        "stats":             get_stats(),
        "last_scrape_time":  last_scrape_time,
        "last_scrape_stats": last_scrape_stats,
    })


# ── Manual scrape trigger — returns JSON, not a page re-render ────────────────
@app.route("/run-scraper", methods=["POST"])
@login_required
def run_scraper():
    """
    Called ONCE by the user clicking 'Run scraper'.
    Returns JSON so the frontend never needs to POST again while waiting.
    The frontend should switch to polling /scraper-status after this call.
    """
    if scraper_running:
        return jsonify({"started": False, "reason": "already_running"})

    if scraper_error:
        # Allow re-trigger after a previous crash
        pass

    threading.Thread(target=run_pipeline, daemon=True).start()
    # Small sleep so scraper_running has time to flip to True
    time.sleep(0.3)
    return jsonify({"started": True, "running": scraper_running})


# ── JSON API endpoints ────────────────────────────────────────────────────────
@app.route("/api/jobs")
@login_required
def api_jobs():
    from database import get_all_jobs
    return jsonify(get_all_jobs())

@app.route("/api/applied")
@login_required
def api_applied():
    from database import get_jobs_by_status
    return jsonify(get_jobs_by_status("applied"))

@app.route("/api/stats")
@login_required
def api_stats():
    from database import get_stats
    return jsonify(get_stats())


# ═══════════════════════════════════════════════════════════════════════════════
#  BOOT
# ═══════════════════════════════════════════════════════════════════════════════

threading.Thread(target=startup_rematch, daemon=True).start()

scheduler = BackgroundScheduler(timezone="Africa/Johannesburg")
scheduler.add_listener(on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

# Auto-scrape 4× daily
scheduler.add_job(
    func=run_pipeline,
    trigger="cron",
    hour="6,12,18,23",
    minute=0,
    id="auto_scrape",
    replace_existing=True,
    misfire_grace_time=300,
)

# Self-ping every 5 min to keep host awake
scheduler.add_job(
    func=self_ping,
    trigger="interval",
    minutes=5,
    id="self_ping",
    replace_existing=True,
)

scheduler.start()

if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)