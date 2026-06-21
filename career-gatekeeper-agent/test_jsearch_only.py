"""
test_jsearch_only.py
======================
A standalone, minimal test that checks ONLY the JSearch (RapidAPI) connection
- no Gemini, no ADK, no agent pipeline, no resume_data.py needed.

Run it directly:
    python test_jsearch_only.py

This isolates exactly one variable (is JSearch reachable and working?) so
you don't have to wade through ADK/Gemini errors to find out.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
JSEARCH_HOST = "jsearch.p.rapidapi.com"


def main():
    print("=" * 60)
    print("JSearch API standalone test")
    print("=" * 60)

    # --- Step 1: is the key even present? ---
    if not RAPIDAPI_KEY:
        print("\n[FAIL] RAPIDAPI_KEY is empty or not found in .env")
        print("       Make sure .env (in this same folder) contains:")
        print("       RAPIDAPI_KEY=your-actual-key-here")
        sys.exit(1)

    masked = RAPIDAPI_KEY[:6] + "..." + RAPIDAPI_KEY[-4:] if len(RAPIDAPI_KEY) > 10 else "(too short?)"
    print(f"\n[OK] RAPIDAPI_KEY loaded: {masked} (length: {len(RAPIDAPI_KEY)})")

    # --- Step 2: make the simplest possible request ---
    url = f"https://{JSEARCH_HOST}/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": JSEARCH_HOST,
    }
    params = {
        "query": "developer",  # deliberately broad - should always have results
        "page": "1",
        "num_pages": "1",
        "country": "us",  # deliberately the simplest, most-likely-to-work case
    }

    print(f"\nSending request to {url}")
    print(f"Params: {params}")
    print("Waiting for response (up to 30 seconds)...\n")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.exceptions.Timeout:
        print("[FAIL] Request timed out after 30 seconds.")
        print("       This usually means a network/firewall issue, not an API problem.")
        print("       Try: a different network, disabling VPN, or checking firewall settings.")
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        print(f"[FAIL] Could not connect at all: {e}")
        print("       Check your internet connection.")
        sys.exit(1)

    print(f"HTTP status code: {response.status_code}")

    # --- Step 3: interpret the result clearly ---
    if response.status_code == 401:
        print("\n[FAIL] 401 Unauthorized - your RAPIDAPI_KEY is invalid or expired.")
        print("       Go to https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch")
        print("       and copy a fresh key from the 'X-RapidAPI-Key' field.")
        sys.exit(1)

    if response.status_code == 403:
        print("\n[FAIL] 403 Forbidden - you are not subscribed to this API,")
        print("       or your subscription doesn't include this endpoint.")
        print("       Go to https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch")
        print("       and make sure you clicked 'Subscribe to Test' and selected")
        print("       the free 'Basic' plan. Check 'My Apps' > 'Subscriptions' in")
        print("       your RapidAPI dashboard to confirm it's active.")
        print(f"\n       Raw response: {response.text[:500]}")
        sys.exit(1)

    if response.status_code == 429:
        print("\n[FAIL] 429 Too Many Requests - you've hit RapidAPI's rate limit")
        print("       (likely the free tier's monthly cap of 200 requests, or a")
        print("       per-second burst limit from repeated testing).")
        print(f"\n       Raw response: {response.text[:500]}")
        sys.exit(1)

    if response.status_code != 200:
        print(f"\n[FAIL] Unexpected status code {response.status_code}")
        print(f"       Raw response: {response.text[:500]}")
        sys.exit(1)

    # --- Step 4: status 200 - check if there's actual data ---
    try:
        payload = response.json()
    except ValueError:
        print("\n[FAIL] Got HTTP 200 but the response wasn't valid JSON.")
        print(f"       Raw response: {response.text[:500]}")
        sys.exit(1)

    print(f"\n[OK] Got valid JSON response.")
    print(f"     API status field: {payload.get('status')}")

    results = payload.get("data", [])
    print(f"     Number of jobs returned: {len(results)}")

    if not results:
        print("\n[WARNING] HTTP 200 and valid JSON, but zero job results for")
        print("          query='developer', country='us' - this is a very broad")
        print("          search, so getting zero results here suggests an issue")
        print("          with the API subscription itself (e.g. plan not fully")
        print("          activated yet) rather than a query-specific problem.")
        print(f"\n     Full response: {json.dumps(payload, indent=2)[:1500]}")
    else:
        print("\n[SUCCESS] JSearch is working correctly. Sample result:")
        first = results[0]
        print(f"     Title:   {first.get('job_title')}")
        print(f"     Company: {first.get('employer_name')}")
        print(f"     Location: {first.get('job_city')}, {first.get('job_country')}")

    print("\n" + "=" * 60)
    print("Test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
