import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.scraper import (
    format_url, verify_url, get_repo_title,
    get_stargazer_usernames, get_user_profile, get_user_email,
    ScraperError,
)

# In-memory job store
_jobs = {}
_lock = threading.Lock()

WORKERS = 5
PAGE_DELAY = 1.0  # seconds between page requests to avoid GitHub blocks
BATCH_DELAY = 2.0  # seconds between profile batches
EMPTY_PAGE_LIMIT = 3  # stop after this many consecutive empty pages


def create_job(repo_url, mode="full"):
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "repo_url": repo_url,
        "mode": mode,  # "full", "emails", "usernames"
        "status": "started",
        "repo_name": None,
        "phase": "validating",
        "total_usernames": 0,
        "usernames_scraped": 0,
        "profiles_scraped": 0,
        "stargazers": [],
        "error": None,
        "created_at": time.time(),
    }
    with _lock:
        _jobs[job_id] = job

    worker = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    worker.start()
    return job_id


def get_job(job_id):
    with _lock:
        return _jobs.get(job_id)


def list_jobs():
    with _lock:
        return [
            {
                "id": j["id"],
                "repo_url": j["repo_url"],
                "mode": j["mode"],
                "status": j["status"],
                "phase": j["phase"],
                "repo_name": j["repo_name"],
                "total_usernames": j["total_usernames"],
                "profiles_scraped": j["profiles_scraped"],
                "created_at": j["created_at"],
            }
            for j in _jobs.values()
        ]


def _update_job(job_id, **kwargs):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _append_results(job_id, results):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["stargazers"].extend(results)
            _jobs[job_id]["profiles_scraped"] = len(_jobs[job_id]["stargazers"])


def _run_job(job_id):
    try:
        job = get_job(job_id)
        repo_url = job["repo_url"]
        mode = job["mode"]

        # Validate URL
        url = format_url(repo_url)
        _update_job(job_id, phase="fetching_repo")

        import requests
        html = requests.get(url, timeout=10).text
        if not verify_url(html):
            _update_job(job_id, status="failed", error="Invalid repository URL")
            return

        repo_name = get_repo_title(html)
        _update_job(job_id, repo_name=repo_name, phase="scraping_usernames", status="running")

        # Phase 1: Get all stargazer usernames
        usernames = _scrape_usernames_with_progress(job_id, url)
        _update_job(job_id, total_usernames=len(usernames))

        if mode == "usernames":
            results = [{"username": u} for u in usernames]
            _append_results(job_id, results)
            _update_job(job_id, status="completed", phase="done")
            return

        # Phase 2: Scrape profiles/emails concurrently
        _update_job(job_id, phase="scraping_profiles")

        scrape_fn = get_user_profile if mode == "full" else _email_only
        _scrape_profiles_concurrent(job_id, usernames, scrape_fn)

        _update_job(job_id, status="completed", phase="done")

    except ScraperError as e:
        _update_job(job_id, status="failed", error=str(e))
    except Exception as e:
        _update_job(job_id, status="failed", error=str(e))


def _email_only(username):
    email = get_user_email(username)
    return {"username": username, "email": email}


def _scrape_usernames_with_progress(job_id, repo_url):
    """Scrape all stargazer usernames by iterating through page numbers."""
    import requests
    from bs4 import BeautifulSoup

    usernames = []
    page = 1
    empty_streak = 0

    while True:
        url = repo_url + "/stargazers?page={}".format(page)
        stargazer_html = requests.get(url, timeout=15).text
        soup = BeautifulSoup(stargazer_html, "lxml")

        found = []
        truncate_spans = soup.findAll("span", {"class": "Truncate-text"})
        for span in truncate_spans:
            a_tag = span.find("a", {"data-hovercard-type": "user"})
            if a_tag:
                href = a_tag.get("href")
                if href:
                    found.append(href.lstrip("/"))

        if found:
            usernames.extend(found)
            empty_streak = 0
        else:
            empty_streak += 1
            if empty_streak >= EMPTY_PAGE_LIMIT:
                break

        page += 1
        _update_job(job_id, usernames_scraped=len(usernames))
        time.sleep(PAGE_DELAY)

    return usernames


def _scrape_profiles_concurrent(job_id, usernames, scrape_fn):
    """Scrape profiles using a thread pool, appending results in batches."""
    batch_size = WORKERS * 2
    for i in range(0, len(usernames), batch_size):
        batch = usernames[i:i + batch_size]
        results = []

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            future_to_user = {pool.submit(scrape_fn, u): u for u in batch}
            for future in as_completed(future_to_user):
                username = future_to_user[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception:
                    results.append({"username": username, "error": "Failed to scrape"})

        _append_results(job_id, results)
        time.sleep(BATCH_DELAY)
