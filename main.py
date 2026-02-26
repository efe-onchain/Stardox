from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from src.jobs import create_job, get_job, list_jobs

app = FastAPI(
    title="Stardox API",
    description="GitHub stargazer intelligence API",
    version="2.0.0",
)


class ScrapeRequest(BaseModel):
    repo: str
    mode: str = "full"  # "full", "emails", "usernames"


@app.get("/")
def root():
    return {"status": "ok", "service": "stardox"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/api/stardox")
def start_scrape(req: ScrapeRequest):
    if req.mode not in ("full", "emails", "usernames"):
        raise HTTPException(status_code=400, detail="mode must be full, emails, or usernames")
    job_id = create_job(req.repo, req.mode)
    return {"job_id": job_id, "status": "started"}


@app.get("/api/stardox/{job_id}")
def get_scrape_status(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    stargazers = job["stargazers"][offset:offset + limit]

    return {
        "job_id": job["id"],
        "repo_url": job["repo_url"],
        "repo_name": job["repo_name"],
        "mode": job["mode"],
        "status": job["status"],
        "phase": job["phase"],
        "total_usernames": job["total_usernames"],
        "profiles_scraped": job["profiles_scraped"],
        "error": job["error"],
        "offset": offset,
        "limit": limit,
        "stargazers": stargazers,
    }


@app.get("/api/jobs")
def get_all_jobs():
    return {"jobs": list_jobs()}
