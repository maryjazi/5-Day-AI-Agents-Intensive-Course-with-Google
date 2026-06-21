"""
job_search_server.py
=====================
A lightweight MCP server (built with FastMCP) that exposes job-search tools
for the Career Gatekeeper Agent to consume as an MCP client.

This mirrors the architecture of mcp-flight-search (ADK + MCP demo) but is
repurposed for job search, which is the actual problem this capstone solves.

REAL DATA SOURCE: this server calls the JSearch API (via RapidAPI), which
aggregates live job postings from LinkedIn, Indeed, Glassdoor, ZipRecruiter,
and other public job boards. JSearch has a free tier (200 requests/month,
no credit card required) - see README.md "Connecting a real job API" for
setup instructions.

FALLBACK: if no RAPIDAPI_KEY is set in the environment, this server falls
back to a small set of realistic mock postings so the full agent pipeline
can still be demoed end-to-end without any external credentials.

GATEKEEPER NOTE: this server is intentionally READ-ONLY. It has no tool
for submitting an application, sending a message, or writing any kind of
external state. That is a deliberate security boundary, not an oversight -
see docs/SECURITY.md.
"""

import os
import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("job-search")

JSEARCH_HOST = "jsearch.p.rapidapi.com"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")


# ---------------------------------------------------------------------------
# Fallback mock data - used only if RAPIDAPI_KEY is not set, so the agent
# pipeline remains demoable without any external credentials.
# ---------------------------------------------------------------------------
_MOCK_JOBS = [
    {
        "title": "Datenbankadministrator (m/w/d)",
        "company": "Nordic Freight Analytics",
        "location": "Berlin, Germany",
        "remote": True,
        "salary_range": "55,000-68,000 EUR",
        "required_skills": ["SQL", "MSSQL", "PostgreSQL", "Oracle", "Backup & Recovery"],
        "posted_days_ago": 2,
        "url": "https://example-jobs.local/postings/1001",
    },
    {
        "title": "IT-Systemadministrator (m/w/d)",
        "company": "GreenGrid Energy",
        "location": "Hamburg, Germany",
        "remote": False,
        "salary_range": "52,000-62,000 EUR",
        "required_skills": ["Windows Server", "Active Directory", "VMware ESXi", "Netzwerkadministration"],
        "posted_days_ago": 1,
        "url": "https://example-jobs.local/postings/1003",
    },
    {
        "title": "IT Support Specialist (2nd/3rd Level)",
        "company": "OrbitApp",
        "location": "Remote (Worldwide)",
        "remote": True,
        "salary_range": "45,000-55,000 EUR",
        "required_skills": ["Active Directory", "Ticketsysteme", "Windows Server", "IT-Support"],
        "posted_days_ago": 3,
        "url": "https://example-jobs.local/postings/1005",
    },
]


def _mock_search(query: str, location: str, max_results: int) -> list:
    """Same lightweight relevance scoring as before, used only as fallback."""
    query_terms = {t.lower() for t in query.replace(",", " ").split()}

    def score(job):
        skill_terms = set()
        for s in job["required_skills"]:
            skill_terms.update(s.lower().replace("/", " ").split())
        title_terms = set(job["title"].lower().replace("(", " ").replace(")", " ").split())
        overlap = len(query_terms & (skill_terms | title_terms))
        location_bonus = 1 if location.lower() in job["location"].lower() or job["remote"] else 0
        return overlap * 2 + location_bonus

    ranked = sorted(_MOCK_JOBS, key=score, reverse=True)
    return ranked[:max_results]


def _normalize_jsearch_job(raw: dict) -> dict:
    """Maps a JSearch API job object to this server's stable output schema,
    so job_search_agent / resume_job_matcher don't need to know which
    upstream API the data came from.

    NOTE: JSearch field names are documented here as job_title,
    employer_name, job_min_salary, job_max_salary, job_city, etc. (the
    "job_" prefix convention used by the RapidAPI listing). If your
    response looks different, run debug_jsearch_raw_response() below to
    print the raw payload and adjust the .get() keys here accordingly -
    third-party APIs occasionally rename fields between versions.
    """
    salary_min = raw.get("job_min_salary")
    salary_max = raw.get("job_max_salary")
    currency = raw.get("job_salary_currency") or ""
    if salary_min and salary_max:
        salary_range = f"{salary_min:,.0f}-{salary_max:,.0f} {currency}".strip()
    else:
        salary_range = "Not listed"

    city = raw.get("job_city") or ""
    state = raw.get("job_state") or ""
    country = raw.get("job_country") or ""
    location = ", ".join(p for p in [city, state, country] if p) or "Not specified"

    skills = raw.get("job_required_skills") or []

    return {
        "title": raw.get("job_title", "Unknown title"),
        "company": raw.get("employer_name", "Unknown company"),
        "location": location,
        "remote": bool(raw.get("job_is_remote", False)),
        "salary_range": salary_range,
        "required_skills": skills,
        "posted_days_ago": None,  # JSearch gives a timestamp, not days-ago
        "posted_at": raw.get("job_posted_at_datetime_utc", ""),
        "url": raw.get("job_apply_link", raw.get("job_google_link", "")),
        "job_id": raw.get("job_id", ""),
        "description_snippet": (raw.get("job_description") or "")[:400],
    }


def _guess_country_code(location: str) -> str:
    """
    JSearch's 'country' parameter (ISO 3166 two-letter code) defaults to
    'us' if not specified - even when the query text mentions a different
    country. That mismatch silently returns zero results (a real bug we
    hit: searching "IT Administrator in Germany" with no country param
    returned 0 results because the API was scoped to the US).

    This is a small, deliberately incomplete lookup for common cases. Add
    more entries as needed, or pass a two-letter code directly as
    `location` (e.g. "DE") to skip guessing entirely.
    """
    if not location or location.lower() == "remote":
        return "us"
    if len(location) == 2 and location.isalpha():
        return location.lower()  # already a country code, e.g. "DE"

    loc = location.lower()
    country_map = {
        "germany": "de", "deutschland": "de",
        "united states": "us", "usa": "us",
        "united kingdom": "gb", "uk": "gb",
        "france": "fr", "spain": "es", "italy": "it",
        "netherlands": "nl", "austria": "at", "switzerland": "ch",
        "canada": "ca", "australia": "au", "india": "in",
        "poland": "pl", "sweden": "se", "ireland": "ie",
    }
    for name, code in country_map.items():
        if name in loc:
            return code
    return "us"  # fallback - matches JSearch's own default


def debug_jsearch_raw_response(query: str = "IT Administrator", location: str = "Germany") -> None:
    """
    Debug helper - NOT an MCP tool, call directly with:
        python -c "from mcp_server.job_search_server import debug_jsearch_raw_response as d; d()"

    Prints the raw, unmodified JSearch API response so you can confirm the
    actual field names if search_jobs() results look wrong (e.g. all
    titles/companies showing as "Unknown"). Requires RAPIDAPI_KEY to be set.

    NOTE: when this module runs normally (as a subprocess spawned by
    agent/career_agent.py), RAPIDAPI_KEY arrives via the subprocess env
    that career_agent.py already loaded from .env. But when you call this
    function directly with `python -c "..."` like above, nothing has
    loaded .env yet - so we load it here too, specifically for this
    standalone debug path.
    """
    import json
    from dotenv import load_dotenv

    load_dotenv()  # picks up .env in the current working directory
    key = os.getenv("RAPIDAPI_KEY", "")

    if not key:
        print(
            "RAPIDAPI_KEY is not set - nothing to debug.\n"
            "Make sure you're running this from the project root (where "
            ".env lives) and that .env contains a RAPIDAPI_KEY= line."
        )
        return

    url = f"https://{JSEARCH_HOST}/search"
    search_term = f"{query} in {location}"
    country = _guess_country_code(location)
    headers = {"x-rapidapi-key": key, "x-rapidapi-host": JSEARCH_HOST}
    response = requests.get(
        url, headers=headers,
        params={"query": search_term, "page": "1", "country": country},
        timeout=30,
    )
    print(f"HTTP {response.status_code} (country param sent: {country})")
    try:
        print(json.dumps(response.json(), indent=2)[:3000])
    except ValueError:
        # Response body wasn't valid JSON (e.g. an empty or HTML error page
        # from a 403/429) - show the raw text instead of crashing.
        print("Response body was not valid JSON. Raw text:")
        print(response.text[:1000])


def _jsearch_search(query: str, location: str, max_results: int) -> list:
    """
    Calls the real JSearch API (RapidAPI) for live job postings.

    KNOWN ISSUE (confirmed via testing): JSearch's `country` parameter has
    inconsistent coverage - e.g. country="de" (Germany) reliably returns
    zero results even for broad queries like "developer", while the same
    query with country="fr" (France) or no country param at all returns
    real results. This isn't a bug in our code; it's a data-coverage gap
    in the underlying API for certain countries.

    Mitigation: if the first search (with an explicit country code) comes
    back empty, we retry once without the country parameter, relying on
    the query text itself (e.g. "developer in Germany") to scope the
    search. This trades a bit of precision for actually getting results.
    """
    url = f"https://{JSEARCH_HOST}/search"
    search_term = f"{query} in {location}" if location and location.lower() != "remote" else query
    country = _guess_country_code(location)
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": JSEARCH_HOST,
    }

    params = {"query": search_term, "page": "1", "num_pages": "1", "country": country}
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    results = payload.get("data", [])

    if not results and country != "us":
        # Retry without forcing a country code - let the query text alone
        # ("... in Germany") do the scoping. See docstring above.
        params_no_country = {"query": search_term, "page": "1", "num_pages": "1"}
        response = requests.get(url, headers=headers, params=params_no_country, timeout=30)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("data", [])

    normalized = [_normalize_jsearch_job(r) for r in results]
    return normalized[:max_results]


@mcp.tool()
def search_jobs(query: str, location: str = "remote", max_results: int = 5) -> list:
    """
    Search open job listings by free-text query and location.

    Uses the JSearch API (live data from LinkedIn, Indeed, Glassdoor,
    ZipRecruiter, etc.) when RAPIDAPI_KEY is set. Falls back to a small
    set of mock postings otherwise, so the pipeline stays demoable without
    external credentials.

    Args:
        query: free text describing the role/skills to search for
                (e.g. "data analyst SQL Python").
        location: desired city/country, or "remote".
        max_results: maximum number of results to return (default 5).

    Returns:
        A list of job postings (dicts) with title, company, location,
        salary_range, required_skills, url, etc.
        This tool is READ-ONLY: it never submits or modifies anything.
    """
    if not RAPIDAPI_KEY:
        return _mock_search(query, location, max_results)

    try:
        return _jsearch_search(query, location, max_results)
    except requests.RequestException as e:
        # Fail soft: real-API errors (rate limit, network) shouldn't crash
        # the agent pipeline - fall back to mock data and flag it clearly.
        return [{
            "error": f"Live job search failed ({e}); showing mock data instead.",
            **job,
        } for job in _mock_search(query, location, max_results)]


@mcp.tool()
def get_job_details(job_url: str) -> dict:
    """
    Fetch full details for a single job posting by its URL or job_id.
    READ-ONLY: does not submit an application or contact the employer.

    Note: JSearch's job-details endpoint requires a job_id (returned by
    search_jobs as the 'job_id' field), not the apply URL. If RAPIDAPI_KEY
    is not set, this looks up the job in the mock data by URL instead.
    """
    if not RAPIDAPI_KEY:
        for job in _MOCK_JOBS:
            if job["url"] == job_url:
                return job
        return {"error": "Job not found in mock data"}

    url = f"https://{JSEARCH_HOST}/job-details"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": JSEARCH_HOST,
    }
    try:
        response = requests.get(
            url, headers=headers, params={"job_id": job_url}, timeout=30
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("data", [])
        if not results:
            return {"error": "Job not found"}
        return _normalize_jsearch_job(results[0])
    except requests.RequestException as e:
        return {"error": f"Live job lookup failed: {e}"}


if __name__ == "__main__":
    # Run as a stdio MCP server (consumed by McpToolset in
    # agent/career_agent.py), matching the ADK-as-MCP-client pattern.
    mcp.run(transport="stdio")
