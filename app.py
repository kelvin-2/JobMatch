import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import json

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


class User(UserMixin):
    id = "kelvin"


@login_manager.user_loader
def load_user(user_id):
    return User() if user_id == "kelvin" else None


# ── Helper ────────────────────────────────────────────────────────────────────
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Pipeline ──────────────────────────────────────────────────────────────────
def run_pipeline():
    """Full scrape → clean → match → save pipeline."""
    print("Pipeline starting...")
    try:
        from scraper import scrape_all
        from cleaner import clean_jobs
        from matcher import load_profile, filter_jobs
        from database import save_jobs, save_matches

        raw      = scrape_all(max_pages=3)
        cleaned  = clean_jobs(raw)
        profile  = load_profile()
        matched  = filter_jobs(cleaned, profile)

        save_jobs(cleaned)
        save_matches(matched)
        print(f"Pipeline complete. {len(matched)} jobs matched.")
    except Exception as e:
        print(f"Pipeline error: {e}")


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
    return render_template("dashboard.html", jobs=jobs, stats=stats)


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
        # Read form data
        updated = {
            "name":                request.form.get("name"),
            "university":          request.form.get("university"),
            "degree":              request.form.get("degree"),
            "graduation_year":     int(request.form.get("graduation_year", 2025)),
            "location":            request.form.get("location"),
            "accept_remote":       "accept_remote" in request.form,
            "accept_internships":  "accept_internships" in request.form,
            "accept_learnerships": "accept_learnerships" in request.form,
            "min_match_score":     0.25,
            "skills":              [s.strip() for s in request.form.get("skills", "").split(",") if s.strip()],
            "degree_keywords":     [k.strip() for k in request.form.get("degree_keywords", "").split(",") if k.strip()],
            "target_job_types": [
                "graduate programme", "graduate program", "entry level",
                "entry-level", "junior", "trainee", "internship",
                "learnership", "graduate trainee", "management trainee",
                "no experience required", "fresh graduate", "recent graduate",
                "0-1 years", "0 to 1 year"
            ],
            "disqualifying_keywords": [
                "5 years", "5+ years", "senior", "head of",
                "director", "principal", "minimum 3 years", "minimum 5 years"
            ]
        }
        # Save to profile.json
        with open("profile.json", "w") as f:
            json.dump(updated, f, indent=2)
        flash("Profile saved! Changes apply on the next scrape.")
        return redirect(url_for("profile"))

    # Load current profile
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
            filename = "kelvin_cv.pdf"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            flash("CV uploaded successfully.")
            return redirect(url_for("cv"))
        flash("Please upload a PDF file only.")

    if os.path.exists(cv_path):
        size_kb = round(os.path.getsize(cv_path) / 1024, 1)
        cv_file = {
            "name": "kelvin_cv.pdf",
            "size": f"{size_kb} KB",
        }

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
    data   = request.get_json()
    url    = data.get("url")
    status = data.get("status")
    db_update(url, status)
    return jsonify({"ok": True})


@app.route("/run-scraper", methods=["POST"])
@login_required
def run_scraper():
    run_pipeline()
    flash("Scraper ran successfully. New jobs are ready.")
    return redirect(url_for("dashboard"))


# ── Scheduler ─────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=run_pipeline,
    trigger="cron",
    hour=7,
    minute=0,
    id="morning_scrape",
    replace_existing=True,
)
scheduler.start()

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, port=5000)