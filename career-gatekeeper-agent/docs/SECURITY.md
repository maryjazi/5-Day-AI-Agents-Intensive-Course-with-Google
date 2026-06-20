# Security & Gatekeeper Design

This document explains how Career Gatekeeper Agent satisfies the "Gatekeeper
Agents" track requirement: *a secure, helpful personal assistant that keeps
user data safe.*

## Threat model

The sensitive asset in this system is the **resume** (personal data: name,
work history, sometimes contact info) and any **outreach content** generated
from it. The agent also touches a third-party job-search data source.

Two failure modes we explicitly design against:

1. **Data leakage** — resume content being sent somewhere the user did not
   approve (e.g. baked into a job-search query string, logged by a
   third-party tool, or auto-sent to a recruiter).
2. **Unauthorized action** — the agent taking an irreversible action (sending
   a message, submitting an application) without explicit human approval.

## Controls implemented

| Control | Where | Why |
|---|---|---|
| **Read-only tool tier for search** | `job_search_server.py` exposes only `search_jobs` and `get_job_details`. There is no `apply_to_job` or `send_message` tool. | Removing the capability at the tool layer is stronger than relying on a prompt instruction — the agent *cannot* take the action even if it tried. |
| **Draft-only tier for outreach** | `resume_job_matcher` SKILL.md explicitly states it only produces drafts and must label them as such. | Keeps a human in the loop before anything is sent externally. |
| **No resume data in the search query** | `job_search_agent` instruction restricts it to structured profile fields (skills, titles, experience) produced by `resume_analyst_agent` — not the raw resume text. | Limits what's transmitted to the MCP tool to the minimum needed (data minimization). |
| **Local-only resume parsing** | `resume_analyst_agent` has no tools at all — it can only reason over text already in the session. | Prevents the raw resume from being passed to any external system during analysis. |
| **Explicit "why this scored X" transparency** | Scoring method in the Skill is deterministic and disclosed, not a black box. | Lets the user sanity-check and trust (or override) the agent's reasoning. |
| **No auto-send, no auto-apply, anywhere in the pipeline** | Verified across all three sub-agents: none have a tool capable of an irreversible action. | Matches the "ask in chat, wait for a clear yes" principle for any side-effectful action. |

## What this agent will never do

- Submit a job application on the user's behalf
- Email or message a recruiter without the user copying/sending it themselves
- Store the resume or any personal data outside the local session
- Use the resume's raw text as a search query sent to a third-party API

## What a production hardening pass would add

This is a capstone-scale prototype. A production deployment would add:

- Encryption at rest if resume data is persisted between sessions
- Rate limiting / cost controls on the MCP job-search calls
- An audit log of every tool call (what was searched, when, by whom)
- A real OAuth-scoped API key per user instead of a shared server key
