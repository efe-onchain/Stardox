from fastapi import FastAPI, HTTPException, Query
from src.scraper import scrape_full, scrape_emails, ScraperError

app = FastAPI(
    title="Stardox API",
    description="GitHub stargazer intelligence API",
    version="1.0.0",
)


@app.get("/")
def root():
    return {"status": "ok", "service": "stardox"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/stardox")
def api_stardox(repo: str = Query(..., description="GitHub repository URL")):
    try:
        return scrape_full(repo)
    except ScraperError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/emails")
def api_emails(repo: str = Query(..., description="GitHub repository URL")):
    try:
        return scrape_emails(repo)
    except ScraperError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
