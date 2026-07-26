import time
import random
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

BASE_URL = "https://www.graduates24.com"

# Categories we care about for Kelvin
CATEGORIES = [
    "graduate_programmes",
    "internshipprogrammes",
    "learnerships",
    "entry_level_jobs",
]


def get_driver():
    """Create a headless Chrome browser."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    chrome_path = (
        shutil.which("chromium-browser")
        or shutil.which("chromium")
        or shutil.which("google-chrome")
    )
    if chrome_path:
        options.binary_location = chrome_path

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver


def get_job_links(driver, category: str, max_pages: int = 3) -> list:
    """Scrape job listing pages for a category and return job URLs."""
    links = []
    seen = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/jobs?view={category}&page={page}"
        print(f"Scraping {category} page {page}...")

        driver.get(url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "g24-job-card"))
            )
        except Exception:
            print(f"No job cards found on page {page} — stopping.")
            break

        soup = BeautifulSoup(driver.page_source, "lxml")
        cards = soup.select("div.g24-job-card")

        if not cards:
            print(f"No cards on page {page} — stopping.")
            break

        for card in cards:
            a = card.select_one("a.g24-card-link")
            if a and a.get("href"):
                href = str(a["href"])  # ← add str() here
                full = href if href.startswith("http") else BASE_URL + href
                if full not in seen:
                    seen.add(full)
                    links.append({"url": full, "job_type": category})

        print(f"  Found {len(cards)} cards on page {page}")
        time.sleep(random.uniform(2, 3))

    return links


def parse_job(driver, url: str, job_type: str) -> dict | None:
    """Fetch one job detail page and extract all fields."""
    time.sleep(random.uniform(1, 3))

    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "g24-show-card"))
        )
    except Exception as e:
        print(f"Failed to load {url}: {e}")
        return None

    soup = BeautifulSoup(driver.page_source, "lxml")

    def safe_text(selector: str) -> str:
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""

    # Title from header
    title = safe_text("div.g24-show-header-content h1") or safe_text("h1")

    if not title:
        print(f"Skipping {url} — no title found")
        return None

    # Right panel details — Company, Location, Closing Date, Type
    company      = ""
    location     = ""
    closing_date = ""

    # The right panel has rows with label + value
    rows = soup.select("div.g24-show-card .row [itemprop], div.g24-show-card table tr")
    for row in rows:
        text = row.get_text(strip=True).lower()
        value_el = row.select_one("td:last-child, span:last-child")
        value = value_el.get_text(strip=True) if value_el else ""
        if "company" in text:
            company = value
        elif "location" in text:
            location = value
        elif "closing" in text:
            closing_date = value

    # Fallback selectors for right panel
    if not company:
        company = safe_text("[itemprop='hiringOrganization']") or safe_text(".g24-show-header-content .company")
    if not location:
        location = safe_text("[itemprop='jobLocation']") or safe_text(".location")

    # Description
    description = safe_text("div.g24-show-description") or safe_text("div.g24-show-body")

    # Apply URL — the real external application link
    apply_el = soup.select_one("a.g24-btn-apply")
    apply_url = str(apply_el["href"]) if apply_el and apply_el.get("href") else url

    # Format job type nicely
    type_labels = {
        "graduate_programmes":    "Graduate Programme",
        "internshipprogrammes":   "Internship",
        "learnerships":           "Learnership",
        "entry_level_jobs":       "Entry Level",
    }

    return {
        "title":        title,
        "company":      company,
        "location":     location,
        "salary":       "",
        "closing_date": closing_date,
        "requirements": description[:4000],
        "description":  description[:9000],
        "url":          url,
        "apply_url":    apply_url,
        "job_type":     type_labels.get(job_type, "Entry Level"),
    }


def scrape_all(max_pages: int = 3) -> list[dict]:
    """Main entry point — scrapes all categories and returns job list."""
    driver = get_driver()
    all_jobs = []
    seen_urls = set()

    try:
        for category in CATEGORIES:
            print(f"\n=== Scraping category: {category} ===")
            job_links = get_job_links(driver, category, max_pages=max_pages)

            for item in job_links:
                url = item["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                job = parse_job(driver, url, item["job_type"])
                if job:
                    all_jobs.append(job)
                    print(f"  ✓ {job['title']} — {job['company']}")

    finally:
        driver.quit()

    print(f"\nScraping complete. {len(all_jobs)} jobs found.")
    return all_jobs

def scrape_page(driver, category: str, page: int, seen_urls: set) -> list[dict]:
    """Scrape a single category page, parse each job, return list of job dicts."""
    jobs = []
    url = f"{BASE_URL}/jobs?view={category}&page={page}"
    print(f"[Scraper] {category} — page {page}...")

    driver.get(url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "g24-job-card"))
        )
    except Exception:
        print(f"[Scraper] No job cards on page {page} — stopping category.")
        return []

    soup = BeautifulSoup(driver.page_source, "lxml")
    cards = soup.select("div.g24-job-card")
    if not cards:
        return []

    for card in cards:
        a = card.select_one("a.g24-card-link")
        if not a or not a.get("href"):
            continue
        href = str(a["href"])
        full_url = href if href.startswith("http") else BASE_URL + href
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        job = parse_job(driver, full_url, category)
        if job:
            jobs.append(job)
            print(f"  ✓ {job['title']} — {job['company']}")

        time.sleep(random.uniform(1, 2))

    return jobs