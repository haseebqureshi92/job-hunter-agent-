"""
agent.py — the main brain of the job-hunter agent.

What it does each run:
1. Pulls fresh listings from every source (sources.py)
2. Keyword-filters to your skill set (full-stack / Android / mobile / AI)
3. Skips anything already seen (tracked in data/jobs.json)
4. Sends each new match to a free LLM (Google Gemini) to (a) score fit 1-10
   and (b) draft a short proposal/pitch you can copy-paste and tweak
5. Saves everything to data/jobs.json (powers the dashboard)
6. Emails you a digest of new high-fit matches (score >= EMAIL_THRESHOLD)

Run manually:  python agent.py
Run on a schedule: see .github/workflows/hunt.yml
"""

import os
import re
import json
import smtplib
import requests
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sources import fetch_all_jobs

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "jobs.json")

# --- Your skill profile — edit this to match what you actually want to find ---
SKILL_KEYWORDS = [
    "full stack", "full-stack", "fullstack",
    "android", "kotlin", "java",
    "react native", "flutter", "mobile app", "ios",
    "ai engineer", "machine learning", "llm", "openai", "genai",
    "react", "node", "next.js", "django", "flask", "python developer",
]

# Pre-compile word-boundary patterns once, so "react" never matches inside
# "proactive" or "interact" — each keyword must appear as a whole word/phrase.
_SKILL_PATTERNS = [
    re.compile(r"\b" + re.escape(kw) + r"\b") for kw in SKILL_KEYWORDS
]

EMAIL_THRESHOLD = 7  # only email you about matches scored 7+/10
# "gemini-flash-latest" is Google's official rolling alias — it always points
# to their current flash model, so it won't break every time a specific
# dated version (like gemini-2.5-flash) gets retired. Google gives 2 weeks'
# notice by email before any breaking change to what this alias points to.
GEMINI_MODEL = "gemini-flash-latest"


def load_existing():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_all(jobs_by_id):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(jobs_by_id, f, indent=2, default=str)


def matches_skills(job):
    # Only check the title and structured tags — NOT the free-text description.
    # Long descriptions (funding announcements, company bios, etc.) can contain
    # a stray tech word in passing even when the job itself is irrelevant.
    # Title + tags are a much more reliable, deliberate signal.
    text = f"{job.get('title','')} {' '.join(job.get('tags', []))}".lower()
    return any(pattern.search(text) for pattern in _SKILL_PATTERNS)


def score_and_pitch(job):
    """Ask Google Gemini's free API to score fit and draft a pitch. Falls back gracefully if no key set."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"score": 5, "pitch": "(Set GEMINI_API_KEY to enable AI scoring + auto-drafted pitches.)"}

    prompt = f"""You are helping a freelance Full-Stack / Android & Mobile / AI Engineer developer
evaluate a job lead and draft a short outreach pitch.

Job title: {job['title']}
Source: {job['source']}
Description (may be partial):
{job['description'][:1500]}

Return ONLY valid JSON, no markdown fences, in this exact shape:
{{"score": <integer 1-10, how good a fit for a full-stack/mobile/AI engineer>,
  "pitch": "<a short 80-120 word first-contact proposal message, confident and specific,
  mentioning relevant skills (full-stack web, Android/mobile apps, AI/ML) only where
  actually relevant to this job, no generic filler, no placeholders>"}}"""

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1024,
            # Force clean JSON output instead of relying on stripping markdown fences.
            "responseMimeType": "application/json",
            # Newer Gemini models spend part of the token budget on invisible
            # "thinking" before answering, which was truncating our short JSON
            # replies mid-string. This task doesn't need deep reasoning, so we
            # turn thinking off entirely and give the full budget to the answer.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    for attempt in range(2):  # one retry on a transient timeout/network error
        try:
            resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=45)
            if not resp.ok:
                print(f"[Gemini] HTTP {resp.status_code} for '{job['title']}': {resp.text[:300]}")
            resp.raise_for_status()
            content = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            content = content.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(content)
            score = int(parsed.get("score", 5))
            pitch = parsed.get("pitch", "").strip()
            return {"score": max(1, min(10, score)), "pitch": pitch}
        except Exception as e:
            print(f"[Gemini] scoring failed for '{job['title']}' (attempt {attempt + 1}/2): {e}")

    return {"score": 5, "pitch": "(AI drafting failed this run — check GEMINI_API_KEY / rate limits.)"}


def send_email_digest(new_matches):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("EMAIL_USER", "").strip()
    password = os.environ.get("EMAIL_PASS", "").strip()
    to_addr = os.environ.get("EMAIL_TO", user).strip()

    if not (user and password and to_addr):
        print("[Email] EMAIL_USER/EMAIL_PASS/EMAIL_TO not set — skipping email digest.")
        return
    if not new_matches:
        print("[Email] No high-fit new matches this run — no email sent.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔎 {len(new_matches)} new job match(es) found"
    msg["From"] = user
    msg["To"] = to_addr

    lines = []
    for job in new_matches:
        lines.append(
            f"[{job['score']}/10] {job['title']}  ({job['source']})\n"
            f"{job['url']}\n"
            f"Suggested pitch:\n{job['pitch']}\n"
            + "-" * 60
        )
    body = "\n\n".join(lines)
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())
        print(f"[Email] Digest sent to {to_addr} ({len(new_matches)} jobs).")
    except Exception as e:
        print(f"[Email] send failed: {e}")


def main():
    print(f"=== Job Hunter Agent run @ {datetime.now(timezone.utc).isoformat()} ===")
    existing = load_existing()
    raw_jobs = fetch_all_jobs()
    print(f"Fetched {len(raw_jobs)} raw listings across all sources.")

    new_matches_for_email = []
    updated = dict(existing)  # keep everything we've seen before

    for job in raw_jobs:
        if job["id"] in existing:
            continue  # already processed in a previous run
        if not matches_skills(job):
            continue

        result = score_and_pitch(job)
        job["score"] = result["score"]
        job["pitch"] = result["pitch"]
        job["status"] = "new"  # new -> pitched -> won -> in_progress -> delivered -> paid
        job["found_at"] = datetime.now(timezone.utc).isoformat()

        updated[job["id"]] = job
        if job["score"] >= EMAIL_THRESHOLD:
            new_matches_for_email.append(job)

    save_all(updated)
    print(f"Total jobs tracked: {len(updated)}. New skill-matches this run: "
          f"{sum(1 for j in updated.values() if j['id'] not in existing)}")

    send_email_digest(new_matches_for_email)


if __name__ == "__main__":
    main()
