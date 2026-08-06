# Lead Radar — Job Hunter Agent

## What this actually is (plain English)

Three things working together:

1. **A small Python program** (`agent.py` + `sources.py`) that checks four
   free job sites every few hours, picks out the ones that match your
   skills (full-stack, Android/mobile, AI), asks an AI to score each one
   and write you a pitch, and saves the results to a file.
2. **A free "robot runner"** (GitHub Actions) that runs that program on a
   timer, forever, without you needing to keep a computer on.
3. **A dashboard** (`dashboard/index.html`) — a webpage that shows you the
   results in a board with columns, so you can track each lead from
   "found" to "got paid."

Where it looks for jobs:
- **RemoteOK** — free, public, no signup needed
- **We Work Remotely** — free, public, no signup needed
- **Remotive** — free, official public API, no signup needed
- **Working Nomads** — free, public feed, no signup needed
- *(Optional)* **Freelancer.com** — needs a free API key if you want it

That's it. No Upwork, no Fiverr, nothing that needs scraping or breaks
any site's rules.

## The 5 things you need to set up (all free, ~20 minutes total)

You don't need to know how to code to do this — just follow each step.

### Step 1 — Put this code on GitHub
GitHub is a free place to store code, and it's also what will *run* your
agent for you on a schedule.
1. Go to [github.com](https://github.com) and make a free account if you
   don't have one.
2. Click the **+** in the top right → **New repository**. Name it
   something like `job-hunter-agent`. Make it **Private**. Click **Create**.
3. On the new repo's page, click **uploading an existing file** and drag
   in every file/folder from this project (keep the folder structure —
   `.github/workflows/hunt.yml` must stay in that exact path).
4. Click **Commit changes**.

### Step 2 — Get a free AI key (this is what scores jobs and writes pitches)
1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   and sign in with any Google account (free, no credit card).
2. Click **Create API key**. Copy the long string it gives you — paste
   it somewhere safe for a minute, you'll need it in the next step.

### Step 3 — Give GitHub that key, securely
This lets the robot use your AI key without it being visible in your code.
1. In your GitHub repo, click **Settings** (top menu of the repo, not
   your account settings).
2. Left sidebar → **Secrets and variables** → **Actions**.
3. Click **New repository secret**.
   - Name: `GEMINI_API_KEY`
   - Value: paste the key from Step 2
   - Click **Add secret**.

### Step 4 — Turn on the free dashboard hosting
1. Still in **Settings**, click **Pages** in the left sidebar.
2. Under "Build and deployment" → **Source**, choose **GitHub Actions**.
3. That's it — nothing to click yet, it activates the first time the
   robot runs.

### Step 5 — Turn on the robot
1. Click the **Actions** tab at the top of your repo.
2. You'll see "Job Hunter Agent" listed. Click it.
3. Click **Run workflow** → **Run workflow** (green button) to run it
   right now for the first time.
4. Wait 1–2 minutes, refresh the page — you'll see a green checkmark when
   it's done.

After that, it repeats automatically every 6 hours on its own — you don't
need to touch anything.

## Where do I actually see the results?

Once Step 5 has run once successfully, your dashboard is live at:

```
https://<your-github-username>.github.io/<your-repo-name>/dashboard/
```

For example, if your username is `sara99` and your repo is called
`job-hunter-agent`, it's:
`https://sara99.github.io/job-hunter-agent/dashboard/`

Open that link (bookmark it!). You'll see columns: **New, Pitched, Won,
In Progress, Delivered, Paid**. Click any card to read the AI's suggested
pitch, copy it, and open the real job listing.

## Do I want email alerts too?

Optional. If you want an email whenever a strong match (score 7+) shows
up, add two more secrets the same way as Step 3:
- `EMAIL_USER` — a Gmail address
- `EMAIL_PASS` — a Gmail **App Password** (not your normal password —
  generate one free at
  [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
  requires 2-step verification turned on first)
- `EMAIL_TO` — where to send it (can be the same Gmail address)

## Do I want Freelancer.com jobs included too?

Optional. Get a free key at
[developers.freelancer.com](https://developers.freelancer.com), then add
it as a secret named `FREELANCER_API_KEY` the same way as Step 3.

## Making it search for exactly what you do

Open `agent.py` in GitHub (click the file, then the pencil ✏️ icon to
edit) and find this near the top:

```python
SKILL_KEYWORDS = [
    "full stack", "full-stack", "fullstack",
    "android", "kotlin", "java",
    "react native", "flutter", "mobile app", "ios",
    "ai engineer", "machine learning", "llm", "openai", "genai",
    "react", "node", "next.js", "django", "flask", "python developer",
]
```

Add, remove, or edit any of these words to match how you want to be
found, then click **Commit changes** at the bottom of the page. The next
scheduled run will use your updated list.

## Moving a lead through the pipeline

Click a card on the dashboard → change the **Stage** dropdown at the
bottom of the popup. This updates what you see immediately in your
browser. To make a stage change *permanent* (so it's still there next
time you open the page), open `data/jobs.json` in GitHub, find that job's
entry, and change its `"status"` value to match (e.g. `"pitched"`).

## Honest limitations

- Free AI usage (Gemini) has rate limits — if a run finds a lot of new
  jobs at once, a few might get a generic fallback score instead of a
  custom one. This is rare with two sources.
- This finds jobs and drafts the pitch — it doesn't send messages or
  submit proposals for you. You still do the final "send" yourself.
- If GitHub Pages or Actions ever look "stuck," check the Actions tab —
  it shows exactly what happened on the last run, including any errors.

## Fixes applied in this version

If you're upgrading from an earlier copy of this project, here's what
changed and why:

- **AI provider**: switched from Groq to Google Gemini, since Groq's
  team/org permission model was blocking key creation for some accounts.
- **Gemini model name**: switched from a hardcoded dated version to
  Google's official rolling alias, `gemini-flash-latest`. We first used
  `gemini-2.0-flash`, which was shut down June 1, 2026; its replacement
  `gemini-2.5-flash` then got blocked for new API keys ahead of its own
  official October 2026 shutdown date. Google is retiring specific dated
  model versions faster than their own published timelines — the
  `-latest` alias sidesteps this entirely, since Google keeps it pointed
  at whatever their current flash model is and gives 2 weeks' notice by
  email before any breaking change to what it resolves to.
- **Keyword matching bug**: the filter used to search full job
  descriptions, which caused false matches (a long unrelated post that
  happened to mention "React" or "Java" in passing would slip through).
  It now only checks the job title and structured tags, which is a much
  more deliberate, reliable signal.
- **We Work Remotely feed labeling**: an earlier version accidentally
  mapped a "mobile" category label to WWR's devops/sysadmin feed (which
  has nothing to do with mobile jobs). That mislabeled feed has been
  removed — the two real programming-category feeds are broad enough to
  surface mobile/AI postings by title, which the keyword filter then
  picks out correctly.
- **RemoteOK request headers**: updated to look like a standard browser
  request, reducing the chance of an occasional 403 block.
