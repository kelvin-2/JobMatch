import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import json
import threading
import time
import random

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "kelvin-jobmatch-2025")

# ── Login setup ───────────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login"

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "changeme")
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ── Scraper state ─────────────────────────────────────────────────────────────
scraper_running = False


class User(UserMixin):
    id = "kelvin"


@login_manager.user_loader
def load_user(user_id):
    return User() if user_id == "kelvin" else None


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Pipeline ──────────────────────────────────────────────────────────────────
def run_pipeline():
    global scraper_running
    scraper_running = True
    print("[Pipeline] Starting...")
    try:
        from scraper import scrape_page, get_driver, CATEGORIES
        from cleaner import clean_jobs
        from matcher import load_profile, filter_jobs
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
                        break
                    cleaned = clean_jobs(raw)
                    matched = filter_jobs(cleaned, profile)
                    save_jobs(cleaned)
                    save_matches(matched)
                    total_jobs    += len(cleaned)
                    total_matched += len(matched)
                    print(f"[Pipeline] Page {page} saved — {len(matched)}/{len(cleaned)} matched.")
                    time.sleep(random.uniform(2, 3))
        finally:
            driver.quit()

        print(f"[Pipeline] Done. {total_matched} matched from {total_jobs} total jobs.")
    except Exception as e:
        print(f"[Pipeline] Error: {e}")
    finally:
        scraper_running = False


# ── Startup rematch ───────────────────────────────────────────────────────────
def startup_rematch():
    try:
        from matcher import load_profile, filter_jobs
        from database import get_all_jobs, save_matches

        jobs = get_all_jobs()
        if not jobs:
            print("[Startup] No jobs in DB yet.")
            return
        profile = load_profile()
        matched = filter_jobs(jobs, profile)
        save_matches(matched)
        print(f"[Startup] Re-matched {len(matched)} jobs from {len(jobs)} in DB.")
    except Exception as e:
        print(f"[Startup] Rematch error: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

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


@app.route("/dashboard")
@login_required
def dashboard():
    from database import get_jobs_by_status, get_stats
    jobs  = get_jobs_by_status("new")
    stats = get_stats()
    return render_template("dashboard.html", jobs=jobs, stats=stats, scraper_just_started=False)


@app.route("/saved")
@login_required
def saved():
    from database import get_jobs_by_status, get_stats
    jobs  = get_jobs_by_status("saved")
    stats = get_stats()
    return render_template("saved.html", jobs=jobs, stats=stats)


@app.route("/tracker")
@login_required
def tracker():
    from database import get_jobs_by_status, get_stats
    applied = get_jobs_by_status("applied")
    saved   = get_jobs_by_status("saved")
    stats   = get_stats()
    return render_template("tracker.html", applied=applied, saved=saved, stats=stats)


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
            "accept_remote":       "accept_remote" in request.form,
            "accept_internships":  "accept_internships" in request.form,
            "accept_learnerships": "accept_learnerships" in request.form,
            "min_match_score":     0.10,
            "skills":              [s.strip() for s in request.form.get("skills", "").split(",") if s.strip()],
            "degree_keywords":     [k.strip() for k in request.form.get("degree_keywords", "").split(",") if k.strip()],
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
                "OSINT", "malware analysis", "digital forensics"
            ],
            "blocked_job_titles": [
                "clerk", "cashier", "driver", "cleaner", "security guard",
                "receptionist", "waiter", "waitress", "sales assistant", "store assistant",
                "picker", "packer", "admin assistant", "call centre agent", "call center",
                "domestic", "general worker", "labourer", "teller", "shelf packer",
                "merchandiser", "forklift", "warehouse", "delivery", "housekeeper",
                "petrol attendant", "plumber", "electrician", "artisan", "mechanic",
                "nursing", "caregiver", "social worker", "teacher", "educator"
            ],
            "target_job_types": [
                "graduate programme", "graduate program", "entry level",
                "entry-level", "junior", "trainee", "internship",
                "learnership", "graduate trainee", "management trainee",
                "no experience required", "fresh graduate", "recent graduate",
                "0-1 years", "0 to 1 year", "junior developer", "junior analyst",
                "junior security", "SOC analyst", "security graduate"
            ],
            "disqualifying_keywords": [
                "5 years", "5+ years", "senior", "head of", "director",
                "principal", "minimum 3 years", "minimum 5 years",
                "CISSP required", "CISM required", "10 years"
            ]
        }
        with open("profile.json", "w") as f:
            json.dump(updated, f, indent=2)
        flash("Profile saved! Changes apply on the next scrape.")
        return redirect(url_for("profile"))

    with open("profile.json") as f:
        current = json.load(f)
    return render_template("profile.html", profile=current)


@app.route("/cv", methods=["GET", "POST"])
@login_required
def cv():
    cv_file = None
    cv_path = os.path.join(app.config["UPLOAD_FOLDER"], "kelvin_cv.pdf")

    if request.method == "POST":
        file = request.files.get("cv_file")
        if file and allowed_file(file.filename):
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], "kelvin_cv.pdf"))
            flash("CV uploaded successfully.")
            return redirect(url_for("cv"))
        flash("Please upload a PDF file only.")

    if os.path.exists(cv_path):
        cv_file = {"name": "kelvin_cv.pdf", "size": f"{round(os.path.getsize(cv_path) / 1024, 1)} KB"}

    return render_template("cv.html", cv_file=cv_file)


@app.route("/download-cv")
@login_required
def download_cv():
    from flask import send_from_directory
    return send_from_directory(app.config["UPLOAD_FOLDER"], "kelvin_cv.pdf", as_attachment=True)


@app.route("/update-status", methods=["POST"])
@login_required
def update_status():
    from database import update_status as db_update
    data = request.get_json()
    db_update(data.get("url"), data.get("status"))
    return jsonify({"ok": True})


@app.route("/scraper-status")
@login_required
def scraper_status():
    from database import get_stats
    return jsonify({"running": scraper_running, "stats": get_stats()})


@app.route("/run-scraper", methods=["POST"])
@login_required
def run_scraper():
    from database import get_jobs_by_status, get_stats
    if not scraper_running:
        threading.Thread(target=run_pipeline, daemon=True).start()
    return render_template("dashboard.html",
        jobs=get_jobs_by_status("new"),
        stats=get_stats(),
        scraper_just_started=True
    )


# ── Startup + Scheduler ───────────────────────────────────────────────────────
threading.Thread(target=startup_rematch, daemon=True).start()

scheduler = BackgroundScheduler()
scheduler.add_job(func=run_pipeline, trigger="cron", hour=23, minute=0,
                  id="night_scrape", replace_existing=True)
scheduler.start()

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, port=5000, use_reloader=False)