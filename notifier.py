import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")


def send_job_notification(matched_jobs: list):
    """Send Kelvin an email with today's matched jobs."""
    if not matched_jobs:
        print("No new jobs to notify about.")
        return

    if not GMAIL_USER or not GMAIL_PASSWORD or not NOTIFY_EMAIL:
        print("Notification skipped: email env vars are missing.")
        return

    job_rows = ""
    for job in matched_jobs[:10]:
        title = job.get("title", "")
        company = job.get("company", "")
        location = job.get("location", "")
        match = job.get("match_pct", "")
        url = job.get("url", "#")
        job_type = job.get("job_type", "")
        job_rows += f"""
        <tr>
            <td style=\"padding:12px;border-bottom:1px solid #2a2d3e;\">
                <a href=\"{url}\" style=\"color:#7c5cfc;font-weight:bold;text-decoration:none;\">{title}</a><br>
                <span style=\"color:#94a3b8;font-size:12px;\">{company} · {location}</span>
            </td>
            <td style=\"padding:12px;border-bottom:1px solid #2a2d3e;color:#4ae176;font-weight:bold;\">{match}</td>
            <td style=\"padding:12px;border-bottom:1px solid #2a2d3e;\">
                <span style=\"background:#947dff22;color:#cabeff;padding:3px 10px;border-radius:999px;font-size:11px;\">{job_type}</span>
            </td>
        </tr>"""

    html = f"""
    <html><body style=\"background:#0f1117;color:#e0e2f0;font-family:'Arial',sans-serif;padding:24px;\">
        <div style=\"max-width:640px;margin:0 auto;\">
            <h1 style=\"font-size:22px;margin-bottom:4px;\">
                <span style=\"color:#7c5cfc;\">●</span> JobMatch
            </h1>
            <p style=\"color:#94a3b8;margin-top:0;\">Morning Kelvin — here's what dropped today.</p>

            <div style=\"background:#1c1f29;border-radius:12px;padding:20px;margin:20px 0;\">
                <p style=\"font-size:18px;font-weight:bold;margin:0 0 4px;\">
                    {len(matched_jobs)} new job{'s' if len(matched_jobs) > 1 else ''} matched your profile
                </p>
                <p style=\"color:#94a3b8;margin:0;font-size:13px;\">Sorted by match score</p>
            </div>

            <table style=\"width:100%;border-collapse:collapse;background:#1c1f29;border-radius:12px;overflow:hidden;\">
                <thead>
                    <tr style=\"background:#272a34;\">
                        <th style=\"padding:12px;text-align:left;font-size:12px;color:#94a3b8;text-transform:uppercase;\">Job</th>
                        <th style=\"padding:12px;text-align:left;font-size:12px;color:#94a3b8;text-transform:uppercase;\">Match</th>
                        <th style=\"padding:12px;text-align:left;font-size:12px;color:#94a3b8;text-transform:uppercase;\">Type</th>
                    </tr>
                </thead>
                <tbody>{job_rows}</tbody>
            </table>

            <div style=\"text-align:center;margin-top:24px;\">
                <a href=\"https://your-app.onrender.com/dashboard\"
                   style=\"background:#7c5cfc;color:white;padding:12px 32px;border-radius:999px;text-decoration:none;font-weight:bold;font-size:14px;\">
                    Open Dashboard
                </a>
            </div>

            <p style=\"color:#484555;font-size:11px;text-align:center;margin-top:24px;\">
                JobMatch · Built by Kelvin Mudzingwa · Personal use only
            </p>
        </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"JobMatch — {len(matched_jobs)} new job{'s' if len(matched_jobs) > 1 else ''} for you today"
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
        print(f"Notification sent to {NOTIFY_EMAIL}")
    except Exception as e:
        print(f"Failed to send notification: {e}")