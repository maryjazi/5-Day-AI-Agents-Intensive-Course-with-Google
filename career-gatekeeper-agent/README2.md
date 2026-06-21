# Career Gatekeeper Agent

A privacy-first personal assistant that analyzes a resume, searches live job
listings, and drafts tailored outreach — built for the **Gatekeeper Agents**
capstone track (*"secure, helpful personal assistants that simplify daily
life while keeping user data safe"*).

## What it does

1. **Reads your resume** (locally, in-session — never sent to an external tool)
2. **Searches relevant open roles** via an MCP job-search server
3. **Scores each match** and **drafts outreach messages** for you to review
   and send yourself

## Capstone concepts demonstrated

| # | Concept | Where |
|---|---|---|
| 1 | **Multi-agent system (ADK)** | `agent/career_agent.py` — a `SequentialAgent` orchestrating `resume_analyst_agent` → `job_search_agent` → `match_writer_agent` |
| 2 | **MCP server as a tool provider** | `mcp_server/job_search_server.py` — a FastMCP server exposing `search_jobs` / `get_job_details`, consumed by the agent via `MCPToolset` |
| 3 | **Agent Skill** | `skills/resume_job_matcher/SKILL.md` — a scoped, documented skill with a `when-not-to-use` clause and a deterministic scoring method |
| 4 | **Security / Gatekeeper guardrails** | `docs/SECURITY.md` — read-only search tier, draft-only outreach tier, no auto-send/auto-apply anywhere in the pipeline |

## Architecture

```
                ┌─────────────────────────┐
                │   career_gatekeeper_agent │  (SequentialAgent, ADK)
                └────────────┬─────────────┘
                             │
        ┌────────────────────┼─────────────────────┐
        ▼                    ▼                      ▼
resume_analyst_agent   job_search_agent      match_writer_agent
  (no tools;             (MCP tools:           (uses Skill:
   reasons over           search_jobs,          resume_job_matcher)
   resume text only)      get_job_details)
                             │
                             ▼
                  job_search_server.py (MCP, stdio)
                  - READ-ONLY: search + details only
                  - no apply / send / write tools exist
```

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set GOOGLE_API_KEY (ADK uses this, not GEMINI_API_KEY)

cp resume_data.py.example resume_data.py
# edit resume_data.py and paste in your real resume text
# (resume_data.py is gitignored - it will never be committed)
```

> **Note on google-adk version:** this project targets `google-adk` 2.x,
> where `McpToolset` is constructed directly (not via the older async
> `from_server()` factory) and `InMemorySessionService.create_session()` is
> a coroutine that must be awaited. If you're following an older ADK
> tutorial and see a different API shape, you're likely looking at a
> pre-2.0 version.

## Connecting a real job API (optional)

By default (no `RAPIDAPI_KEY` set), `search_jobs` returns a small set of
mock postings so the pipeline is demoable without any external account.

To get **live** job postings from LinkedIn, Indeed, Glassdoor, and
ZipRecruiter instead:

1. Go to [JSearch on RapidAPI](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
   and click **Subscribe to Test** → choose the free **Basic** plan
   (200 requests/month, no credit card required).
2. Copy your RapidAPI key from the dashboard's "X-RapidAPI-Key" header value.
3. Add it to `.env`:
   ```
   RAPIDAPI_KEY=your-rapidapi-key-here
   ```
4. Run the agent normally - `mcp_server/job_search_server.py` will
   automatically switch from mock data to live JSearch results.

**If results look wrong** (e.g. all titles show "Unknown title"), the
upstream API may have changed its field names. Run this to inspect the raw
response and adjust the `.get()` keys in `_normalize_jsearch_job()`:
```bash
python -c "from mcp_server.job_search_server import debug_jsearch_raw_response as d; d()"
```

**Country scoping:** JSearch's `country` parameter defaults to `us` if not
set explicitly - searching "in Germany" without it can silently return
zero results even though the request succeeds. `_guess_country_code()` in
`job_search_server.py` maps common country names (Germany, France, UK,
etc.) to their two-letter code automatically. If your country isn't in the
list, either add it there or pass a two-letter code directly as the
`location` argument (e.g. `location="DE"`).

## Run

```bash
python -m agent.career_agent
```

This loads your resume from `resume_data.py` (private, gitignored) and runs
it against the job-search MCP server (live JSearch data if `RAPIDAPI_KEY`
is set, otherwise mock data). To change the search location, edit the
`location=` argument in `agent/career_agent.py`'s `__main__` block.

## Project structure

```
career-gatekeeper-agent/
├── agent/
│   └── career_agent.py          # multi-agent orchestration (ADK)
├── mcp_server/
│   └── job_search_server.py     # MCP server: search_jobs, get_job_details
├── skills/
│   └── resume_job_matcher/
│       └── SKILL.md             # scoring + drafting skill
├── docs/
│   └── SECURITY.md              # Gatekeeper threat model & controls
├── requirements.txt
└── README.md
```

## Why this fits the Gatekeeper track

Job searching is a real, recurring, daily-life task — exactly the kind of
"planning, organizing, managing personal tasks" the track describes. The
sensitive asset (a resume, which contains personal history and sometimes
contact details) makes the security requirement concrete rather than
theoretical: this design shows *specifically* how user data is protected
(read-only tools, draft-only outreach, no raw resume text leaving the
session) rather than just asserting that it is.

## Limitations / next steps

- `job_search_server.py` uses real JSearch API data when `RAPIDAPI_KEY` is
  set, and falls back to mock data otherwise - see "Connecting a real job
  API" above. The free tier is capped at 200 requests/month.
- Salary data from JSearch is often `null` (most postings don't list it) -
  this is normal, not a bug.
- No persistent storage between runs — by design, for this prototype.
- Could be extended with a `LoopAgent` to re-search if no good matches are
  found above a score threshold.
