"""
sources.py — pulls raw job/project listings from each platform.

Every function returns a list of dicts with a common shape:
{
    "id": "unique-id",
    "source": "RemoteOK" | "WeWorkRemotely" | "Remotive" | "WorkingNomads" | "Freelancer",
    "title": "...",
    "company": "...",
    "url": "...",
    "description": "...",
    "posted": "ISO date string or raw string",
    "tags": ["python", "react", ...],
}
"""

import os
import re
import requests
import feedparser
from html import unescape
from html.parser import HTMLParser


class _TextStripper(HTMLParser):
    """Strips HTML tags down to plain text (no external deps needed)."""
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return unescape(" ".join(self.parts)).strip()


def strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    stripper = _TextStripper()
    try:
        stripper.feed(raw_html)
        return stripper.get_text()
    except Exception:
        return re.sub("<[^<]+?>", "", raw_html)


# ---------------------------------------------------------------------------
# RemoteOK — free public JSON API, no key required
# ---------------------------------------------------------------------------
def fetch_remoteok():
    url = "https://remoteok.com/api"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    jobs = []
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[RemoteOK] fetch failed: {e}")
        return jobs

    # First element is metadata, skip it
    for item in data[1:]:
        if not isinstance(item, dict) or "id" not in item:
            continue
        jobs.append({
            "id": f"remoteok-{item.get('id')}",
            "source": "RemoteOK",
            "title": item.get("position", "Untitled"),
            "company": item.get("company", ""),
            "url": item.get("url") or f"https://remoteok.com/l/{item.get('id')}",
            "description": strip_html(item.get("description", ""))[:2000],
            "posted": item.get("date", ""),
            "tags": item.get("tags", []) or [],
        })
    return jobs


# ---------------------------------------------------------------------------
# We Work Remotely — free public RSS feeds per category.
# WWR doesn't have a dedicated "mobile" or "AI" category feed, so we pull the
# two broad programming categories and let the title/tag keyword filter in
# agent.py pick out the Android/Flutter/AI-relevant postings from within them.
# ---------------------------------------------------------------------------
WWR_FEEDS = {
    "programming": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "full-stack": "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
}


def fetch_weworkremotely():
    jobs = []
    seen = set()
    for category, feed_url in WWR_FEEDS.items():
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"[WeWorkRemotely:{category}] fetch failed: {e}")
            continue

        for entry in parsed.entries:
            uid = entry.get("id") or entry.get("link")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            jobs.append({
                "id": f"wwr-{uid}",
                "source": "WeWorkRemotely",
                "title": entry.get("title", "Untitled"),
                "company": "",
                "url": entry.get("link", ""),
                "description": strip_html(entry.get("summary", ""))[:2000],
                "posted": entry.get("published", ""),
                "tags": [category],
            })
    return jobs


# ---------------------------------------------------------------------------
# Freelancer.com — official API, needs a free API key
# Get one at: https://developers.freelancer.com/
# ---------------------------------------------------------------------------
def fetch_freelancer(query="full stack developer"):
    api_key = os.environ.get("FREELANCER_API_KEY", "").strip()
    jobs = []
    if not api_key:
        print("[Freelancer] FREELANCER_API_KEY not set — skipping this source.")
        return jobs

    url = "https://www.freelancer.com/api/projects/0.1/projects/active/"
    params = {"query": query, "limit": 30, "job_details": "true"}
    headers = {"freelancer-oauth-v1": api_key}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Freelancer] fetch failed: {e}")
        return jobs

    for item in data.get("result", {}).get("projects", []):
        jobs.append({
            "id": f"freelancer-{item.get('id')}",
            "source": "Freelancer",
            "title": item.get("title", "Untitled"),
            "company": "",
            "url": f"https://www.freelancer.com/projects/{item.get('seo_url', item.get('id'))}",
            "description": strip_html(item.get("preview_description", ""))[:2000],
            "posted": str(item.get("submitdate", "")),
            "tags": [j.get("name") for j in item.get("jobs", []) or []],
        })
    return jobs


# ---------------------------------------------------------------------------
# Remotive — official free public API, no key required.
# Per Remotive's own terms: link back to the job's Remotive URL and credit
# Remotive as the source (we already do both — see the job dict below), and
# don't poll more than ~4x/day (the workflow schedule respects this).
# ---------------------------------------------------------------------------
def fetch_remotive():
    url = "https://remotive.com/api/remote-jobs"
    params = {"category": "software-dev"}
    jobs = []
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Remotive] fetch failed: {e}")
        return jobs

    for item in data.get("jobs", []):
        jobs.append({
            "id": f"remotive-{item.get('id')}",
            "source": "Remotive",
            "title": item.get("title", "Untitled"),
            "company": item.get("company_name", ""),
            "url": item.get("url", ""),
            "description": strip_html(item.get("description", ""))[:2000],
            "posted": item.get("publication_date", ""),
            "tags": item.get("tags", []) or [],
        })
    return jobs


# ---------------------------------------------------------------------------
# Working Nomads — free public JSON feed, no key required.
# ---------------------------------------------------------------------------
def fetch_workingnomads():
    url = "https://www.workingnomads.co/api/exposed_jobs/"
    jobs = []
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[WorkingNomads] fetch failed: {e}")
        return jobs

    # The feed returns a plain list of job objects.
    for item in data if isinstance(data, list) else []:
        job_id = item.get("id") or item.get("url") or item.get("title")
        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        jobs.append({
            "id": f"workingnomads-{job_id}",
            "source": "WorkingNomads",
            "title": item.get("title", "Untitled"),
            "company": item.get("company_name", ""),
            "url": item.get("url", ""),
            "description": strip_html(item.get("description", ""))[:2000],
            "posted": item.get("pub_date", ""),
            "tags": tags + ([item.get("category_name")] if item.get("category_name") else []),
        })
    return jobs


def fetch_all_jobs():
    jobs = []
    jobs += fetch_remoteok()
    jobs += fetch_weworkremotely()
    jobs += fetch_remotive()
    jobs += fetch_workingnomads()
    jobs += fetch_freelancer()
    return jobs
