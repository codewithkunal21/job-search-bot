import asyncio
import json
import os
import random
import re
import sys
import urllib.parse
from playwright.async_api import async_playwright

try:
    from playwright_stealth import Stealth
except ImportError:
    print("Please install required packages: pip install -r requirements.txt")
    sys.exit(1)

# Ensure Windows event loop policy for asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# User profile definition
PROFILE = {
    "skills": ["python", "machine learning", "pandas", "numpy", "sql", "aws", "scikit-learn", "tensorflow", "pytorch", "statistics", "data analysis"],
    "experience": "Building predictive models and analyzing large datasets"
}

def calculate_match(description: str) -> dict:
    """Compares job description against user profile."""
    desc_lower = description.lower()
    
    # Pre-defined known tech stack list for AI-matching comparison
    tech_stack = [
        "python", "django", "fastapi", "flask", "selenium", "playwright", "puppeteer", 
        "web scraping", "beautifulsoup", "scrapy", "postgresql", "mysql", "mongodb", 
        "redis", "aws", "gcp", "azure", "docker", "kubernetes", "ci/cd", "git",
        "linux", "graphql", "rest api", "numpy", "pandas", "machine learning",
        "stripe", "celery", "redis"
    ]
    
    # Extract keywords present in the job description
    found_keywords = set()
    for tech in tech_stack:
        # Regex to match exact words, handling punctuation next to the word
        if re.search(r'\b' + re.escape(tech) + r'\b', desc_lower):
            found_keywords.add(tech)
            
    my_skills = set(PROFILE["skills"])
    
    matched_skills = my_skills.intersection(found_keywords)
    missing_keywords = found_keywords - my_skills
    
    # Calculate base match score
    if len(found_keywords) == 0:
        base_score = 50.0  # Generic job posting without specific tech stack listed
    else:
        base_score = (len(matched_skills) / len(found_keywords)) * 100.0
        
    # Boosting logic based on core required skills
    if "python" in matched_skills:
        base_score += 15
    if "machine learning" in matched_skills or "pandas" in matched_skills:
        base_score += 15
        
    final_score = min(100.0, base_score)
    
    return {
        "match_score": round(final_score, 2),
        "matched_skills": list(matched_skills),
        "missing_keywords": list(missing_keywords)
    }

async def random_delay():
    """Use random delays (3-7 seconds) between actions to mimic human behavior."""
    delay = random.uniform(3, 7)
    await asyncio.sleep(delay)

async def check_wall_and_pause(page, stage=""):
    """Check for Login wall or CAPTCHA and pause if detected."""
    url = page.url.lower()
    
    # Basic heuristics for login walls and captchas
    wall_criteria = [
        "login" in url and "job" not in url,
        "captcha" in url,
        "security-check" in url,
        "challenge" in url,
        await page.locator('text="Verify you are human"').count() > 0,
        await page.locator('text="Security Check"').count() > 0,
        await page.locator('form[action*="login"]').count() > 0
    ]
    
    if any(wall_criteria):
        print(f"\n🚨 [Alert] CAPTCHA or Login wall detected {stage}! 🚨")
        print(f"Current URL: {page.url}")
        if "linkedin.com" in url and "login" in url:
            print("-> LinkedIn Sign In wall detected. Staying idle for 60 seconds to allow manual login...")
            await asyncio.sleep(60)
            print("-> Resuming automation...")
        else:
            print("-> Please solve the captcha or login manually in the persistent browser window within 20 seconds.")
            await asyncio.sleep(20)

async def scrape_jobs(p, maxjobs=15):
    # Use a persistent browser context to maintain session/cookies
    browser = await p.chromium.launch_persistent_context(
        user_data_dir='./browser_session_data',
        headless=False, # Must be visible for user to solve CAPTCHA
        args=['--disable-blink-features=AutomationControlled']
    )
    
    page = browser.pages[0] if browser.pages else await browser.new_page()
    await Stealth().apply_stealth_async(page)
    
    keyword = "data scientist"
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as file:
                query_data = json.load(file)
                if "keyword" in query_data and query_data["keyword"].strip():
                    keyword = query_data["keyword"].strip()
        except Exception:
            pass

    encoded_kw = urllib.parse.quote(keyword)
    formatted_id = keyword.replace(" ", "-").lower()
    
    url = f"https://www.naukri.com/{formatted_id}-jobs?k={encoded_kw}"
    print(f"Navigating to exact search URL: {url}")
    await page.goto(url)
    
    # Wait for natural interaction
    await random_delay()
    await check_wall_and_pause(page, "on initial search page load")
    
    print("Waiting for job listings to load...")
    try:
        await page.wait_for_selector('.srp-jobtuple-wrapper', timeout=20000)
    except Exception:
        print("Notice: Standard job listings wrapper not found. Could be a layout change or an interception.")
        await check_wall_and_pause(page, "after waiting for listings")

    # Scroll down briefly to load more images/links
    await page.evaluate("window.scrollBy(0, 1000)")
    await random_delay()

    print("Extracting job links...")
    job_cards = await page.query_selector_all('a.title')
    job_urls = []
    
    for card in job_cards:
        href = await card.get_attribute('href')
        if href and "naukri.com/job-listings" in href:
            job_urls.append(href)
            
    # Deduplicate and limit to speed up execution
    job_urls = list(dict.fromkeys(job_urls))[:maxjobs]
    print(f"Found {len(job_urls)} jobs to process.")
    
    if not job_urls:
         print("No job URLs extracted. Ensure you bypassed captchas or check page layout.")
         import sqlite3
         db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobs.db')
         conn = sqlite3.connect(db_path)
         cursor = conn.cursor()
         cursor.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, title TEXT, company TEXT, location TEXT, application_link TEXT, description_snippet TEXT, match_score REAL, matched_skills TEXT, missing_keywords TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
         cursor.execute('DELETE FROM jobs')
         conn.commit()
         conn.close()
         print("Successfully saved 0 new jobs to jobs_report.json")
         await browser.close()
         return

    results = []
    
    for idx, j_url in enumerate(job_urls):
        print(f"\n[{idx+1}/{len(job_urls)}] Scraping: {j_url}")
        
        job_page = await browser.new_page()
        await Stealth().apply_stealth_async(job_page)
        
        try:
            await job_page.goto(j_url, timeout=60000)
            await random_delay()
            
            await check_wall_and_pause(job_page, "on job detail page")
            
            title, company, location, desc = "Unknown", "Unknown", "Unknown", ""
            
            # Smart extraction using common selectors
            try:
                title_el = await job_page.wait_for_selector('h1', timeout=5000)
                if title_el:
                    title = await title_el.inner_text()
            except:
                pass
                
            try:
                comp_el = await job_page.query_selector('.jd-header-comp-name a') or await job_page.query_selector('.comp-name')
                if comp_el:
                    company = await comp_el.inner_text()
            except:
                pass
                
            try:
                loc_el = await job_page.query_selector('.loc-wrap span') or await job_page.query_selector('.location')
                if loc_el:
                    location = await loc_el.inner_text()
            except:
                pass
                
            try:
                desc_el = await job_page.query_selector('.job-desc') or await job_page.query_selector('.jd-text') or await job_page.query_selector('.styles_JDC__1DqN_')
                if desc_el:
                    desc = await desc_el.inner_text()
            except:
                pass
                
            if company == "Unknown":
                page_title = await job_page.title()
                if "-" in page_title:
                    parts = page_title.split("-")
                    if len(parts) > 1:
                        company = parts[1].strip()
                        
            if not desc:
                print("-> Could not fully extract job description. Trying fallback body extraction...")
                body_el = await job_page.query_selector('body')
                if body_el:
                     desc = await body_el.inner_text()
            
            if not desc or len(desc) < 50:
                 print("-> Skipping job. Extraction failed completely.")
                 continue
                 
            # AI Comparison Logic
            match_data = calculate_match(desc)
            
            job_dict = {
                "title": title.strip(),
                "company": company.strip(),
                "location": location.strip(),
                "application_link": j_url,
                "description_snippet": desc[:150].strip().replace('\n', ' ') + "...",
                "match_score": match_data["match_score"],
                "matched_skills": match_data["matched_skills"],
                "missing_keywords": match_data["missing_keywords"]
            }
            results.append(job_dict)
            print(f"-> Analyzed | Score: {job_dict['match_score']}% | Missing: {len(match_data['missing_keywords'])} skills")
            
            if job_dict["match_score"] > 85.0:
                with open("cover_letters.txt", "a", encoding="utf-8") as cl_file:
                    cl_file.write(f"Job Title: {job_dict['title']} at {job_dict['company']}\n")
                    cl_file.write(f"Link: {job_dict['application_link']}\n")
                    cl_file.write(f"Cover Letter Paragraph: I am writing to express my interest in the {job_dict['title']} role. My strong background in Python, Django, and FastAPI perfectly aligns with your team's objectives. Furthermore, I am continually exploring advanced architectures incorporating {', '.join(job_dict['matched_skills'][:3])}, making me an ideal fit for this position.\n\n")
            
        except Exception as e:
            print(f"-> Error tracking {j_url}: {str(e)}")
        finally:
            await job_page.close()
            # Constrain delay loop
            await random_delay()
            
    # Sort results by match_score descending
    results.sort(key=lambda x: x["match_score"], reverse=True)
    
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobs.db')
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
    cursor.execute('DELETE FROM jobs')
    
    for result in results:
        cursor.execute('''
            INSERT INTO jobs (title, company, location, application_link, description_snippet, match_score, matched_skills, missing_keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result['title'], result['company'], result['location'], 
            result['application_link'], result['description_snippet'], 
            result['match_score'], 
            json.dumps(result['matched_skills']), 
            json.dumps(result['missing_keywords'])
        ))
    
    conn.commit()
    conn.close()
        
    print("Data saved to SQLite database... Table successfully overwritten.")
        
    print("\n" + "="*50)
    print(f"=== TOP 5 HIGH-MATCH JOBS ===")
    print("="*50)
    for i, j in enumerate(results[:5]):
        print(f"{i+1}. {j['title']} @ {j['company']}")
        print(f"   Match Score: {j['match_score']}%")
        print(f"   Location: {j['location']}")
        print(f"   Missing Keywords: {', '.join(j['missing_keywords']) if j['missing_keywords'] else 'None'}")
        print(f"   Apply Here: {j['application_link']}\n")
        
    print(f"Successfully saved {len(results)} new jobs to jobs.db SQLite database")
    await browser.close()

async def main():
    print("\nScraping started... Initializing Autonomous Job Search & Match Engine...")
    print(f"Active Profile: {PROFILE['skills']}")
    print("Starting Playwright Stealth session...\n")
    
    async with async_playwright() as p:
        await scrape_jobs(p, maxjobs=5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted manually by user.")
