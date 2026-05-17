import json
import os
import subprocess
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import sqlite3

app = FastAPI(title="Job Bot Dashboard")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if not os.path.exists(TEMPLATES_DIR):
    os.makedirs(TEMPLATES_DIR)

templates = Jinja2Templates(directory=TEMPLATES_DIR)

def init_db():
    db_path = os.path.join(BASE_DIR, "jobs.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            location TEXT,
            application_link TEXT,
            description_snippet TEXT,
            match_score REAL,
            matched_skills TEXT,
            missing_keywords TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

is_scraping = False

def run_scraper_task():
    global is_scraping
    
    print("Scraping started... Delegating write execution to scraper.py, saving to SQLite database.")
        
    try:
        # Run the scraper in background pool
        subprocess.run(["python", "scraper.py"], cwd=BASE_DIR)
        print("Data safely stored to SQLite database jobs.db... Scraping task completed successfully.")
    except Exception as e:
        print(f"Scraping task encountered an error: {e}")
    finally:
        is_scraping = False

class SearchConfig(BaseModel):
    keyword: str

@app.post("/api/update_search")
def update_search(data: SearchConfig):
    config_path = os.path.join(BASE_DIR, "search_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"keyword": data.keyword}, f)
    return {"status": "success", "keyword": data.keyword}

@app.post("/api/scrape")
def trigger_scrape(background_tasks: BackgroundTasks):
    global is_scraping
    if is_scraping:
        return {"status": "already_running", "message": "Scraper is already active."}
    
    is_scraping = True
    background_tasks.add_task(run_scraper_task)
    return {"status": "started", "message": "Scraping successfully triggered in the background."}

@app.get("/api/scrape/status")
def scrape_status():
    global is_scraping
    return {"is_scraping": is_scraping}

@app.get("/api/jobs")
def serve_jobs_db():
    db_path = os.path.join(BASE_DIR, "jobs.db")
    if not os.path.exists(db_path):
        return JSONResponse(content=[])
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM jobs ORDER BY match_score DESC')
    rows = cursor.fetchall()
    
    jobs = []
    for row in rows:
        job = dict(row)
        try:
            job['matched_skills'] = json.loads(job['matched_skills'])
            job['missing_keywords'] = json.loads(job['missing_keywords'])
        except:
            job['matched_skills'] = []
            job['missing_keywords'] = []
        jobs.append(job)
    conn.close()
    
    return JSONResponse(content=jobs)

@app.get("/")
def read_root(request: Request):
    last_updated = "Never"
    db_path = os.path.join(BASE_DIR, "jobs.db")
    
    if os.path.exists(db_path):
        # Calculate timestamp for the UI render
        mtime = os.path.getmtime(db_path)
        last_updated = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %I:%M:%S %p')
        
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"last_updated": last_updated}
    )
import uvicorn
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )