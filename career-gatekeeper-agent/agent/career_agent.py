"""
Career Gatekeeper Agent
========================
A privacy-first personal assistant that helps a job seeker find and apply to
relevant roles, while keeping the user's resume and personal data local and
under explicit user control.

Capstone track: Gatekeeper Agents (secure, helpful personal assistant)

Concepts demonstrated:
1. Multi-agent system built with the Agent Development Kit (ADK)
   - root_agent (orchestrator)
       -> resume_analyst_agent   (parses & summarizes the resume locally)
       -> job_search_agent       (calls the MCP job-search tool)
       -> match_writer_agent     (uses the resume_job_matcher Agent Skill)
2. MCP server as a tool provider (job search / job details)
3. Agent Skill (skills/resume_job_matcher/SKILL.md) for the matching logic
4. Security / Gatekeeper guardrails:
   - resume content never leaves the local session unless the user approves
   - read-only tier for search, draft-only tier for outreach messages
   - no auto-apply / auto-send actions (everything is presented for approval)
"""

import os
import asyncio

from dotenv import load_dotenv
load_dotenv()

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    StdioServerParameters,
    StdioConnectionParams,
)
from google.genai import types


# ---------------------------------------------------------------------------
# 1. MCP connection: a local "job-search" MCP server (see mcp_server/ folder)
#    This mirrors the ADK-as-MCP-client pattern, swapped from flight search
#    to job search so the agent gains a real-world tool capability.
#
#    NOTE: as of google-adk 2.x, McpToolset is constructed directly (it is
#    not an async factory like the older from_server() pattern) and fetches
#    its tools lazily when the agent runs. It must be closed explicitly via
#    `await toolset.close()` when the run is finished. Connection params are
#    wrapped in StdioConnectionParams (the current recommended API) rather
#    than passing StdioServerParameters directly.
# ---------------------------------------------------------------------------
def get_job_search_toolset() -> McpToolset:
    """Returns an MCP toolset connected to the local job-search server."""
    # IMPORTANT: StdioServerParameters.env, if set at all, REPLACES the
    # subprocess's environment entirely (it does not merge with the
    # parent's PATH/HOME). Passing only {"RAPIDAPI_KEY": ...} here would
    # make the subprocess unable to find the `python` executable. We start
    # from the default safe environment (HOME/PATH/TERM) and layer our key
    # on top of it instead.
    from mcp.client.stdio import get_default_environment

    env = get_default_environment()
    env["RAPIDAPI_KEY"] = os.getenv("RAPIDAPI_KEY", "")

    server_params = StdioServerParameters(
        command="python",
        args=["-m", "mcp_server.job_search_server"],
        env=env,
    )
    connection_params = StdioConnectionParams(server_params=server_params, timeout=30)
    return McpToolset(connection_params=connection_params)


# ---------------------------------------------------------------------------
# 2. Sub-agent: Resume Analyst
#    Reads the resume (already in context / local file) and produces a
#    structured summary: skills, years of experience, target roles.
#    GATEKEEPER RULE: this agent never calls an external tool. It only
#    reasons over text already provided by the user in-session.
# ---------------------------------------------------------------------------
resume_analyst_agent = LlmAgent(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    name="resume_analyst_agent",
    description="Parses the user's resume into a structured skills/experience profile.",
    instruction=(
        "You are a resume analyst. Read the resume text provided by the user "
        "and extract: top 8 skills, total years of experience, most recent "
        "job title, and 3 target job titles that fit this background. "
        "Output structured JSON only. Never invent experience that is not in "
        "the resume. Do not call any tool - you only reason over the text "
        "already given to you in this session."
    ),
)


# ---------------------------------------------------------------------------
# 3. Sub-agent: Job Search
#    Uses the MCP job-search tool. READ-ONLY tier: it can query job listings
#    but cannot submit applications or send messages on the user's behalf.
# ---------------------------------------------------------------------------
def build_job_search_agent(toolset: McpToolset):
    return LlmAgent(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        name="job_search_agent",
        description="Searches live job listings via the job-search MCP server.",
        instruction=(
            "You are a job search agent. Given a structured candidate profile "
            "(skills, target titles, experience level), call the job search "
            "tool to find the 5 most relevant, currently open roles. "
            "READ-ONLY: you may only fetch/search job data. You must never "
            "attempt to submit an application, send a message, or take any "
            "action that modifies external state - that capability does not "
            "exist on the tools you have, and you should not imply otherwise."
        ),
        tools=[toolset],
    )


# ---------------------------------------------------------------------------
# 4. Sub-agent: Match Writer (uses the Agent Skill)
#    DRAFT-ONLY tier: produces a tailored summary + outreach draft for the
#    user to review and send themselves. Never sends anything automatically.
# ---------------------------------------------------------------------------
match_writer_agent = LlmAgent(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    name="match_writer_agent",
    description="Applies the resume_job_matcher skill to score and draft outreach for each job.",
    instruction=(
        "Follow the resume_job_matcher Skill exactly as written in "
        "skills/resume_job_matcher/SKILL.md. For each job found by "
        "job_search_agent, output: a 0-100 match score, a 2-sentence reason, "
        "and a short draft outreach message. DRAFT-ONLY: clearly label all "
        "outreach text as a draft for the user to review, edit, and send "
        "themselves. Never claim a message has been sent."
    ),
)


# ---------------------------------------------------------------------------
# 5. Orchestrator: SequentialAgent runs the three sub-agents in order,
#    passing state forward. This is the "multi-agent system built with ADK"
#    requirement for the capstone.
# ---------------------------------------------------------------------------
def build_root_agent(toolset: McpToolset):
    job_search_agent = build_job_search_agent(toolset)
    return SequentialAgent(
        name="career_gatekeeper_agent",
        description=(
            "Orchestrates resume analysis, job search, and match/draft "
            "writing in a single safe pipeline."
        ),
        sub_agents=[resume_analyst_agent, job_search_agent, match_writer_agent],
    )


# ---------------------------------------------------------------------------
# 6. Entrypoint
# ---------------------------------------------------------------------------
async def async_main(resume_text: str, location: str = "remote"):
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        state={}, app_name="career_gatekeeper_app", user_id="local_user"
    )

    toolset = get_job_search_toolset()
    root_agent = build_root_agent(toolset)

    runner = Runner(
        app_name="career_gatekeeper_app",
        agent=root_agent,
        session_service=session_service,
    )

    query = (
        f"Here is my resume:\n\n{resume_text}\n\n"
        f"Find matching jobs in: {location}. "
        f"Score and draft outreach for each."
    )
    content = types.Content(role="user", parts=[types.Part(text=query)])

    print("Running Career Gatekeeper Agent...\n")
    try:
        async for event in runner.run_async(
            session_id=session.id, user_id=session.user_id, new_message=content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        print(part.text)
    finally:
        # GATEKEEPER NOTE: always release the MCP connection, even if the
        # run raised an error, so the subprocess never leaks.
        await toolset.close()


if __name__ == "__main__":
    # Make sure the project root (parent of this agent/ folder) is on
    # sys.path, so `from resume_data import MY_RESUME` works no matter how
    # this script is invoked. Plain `python agent/career_agent.py` only
    # puts agent/ itself on sys.path, not the project root where
    # resume_data.py actually lives - without this fix, the import below
    # fails even when resume_data.py exists and is correctly filled in.
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from resume_data import MY_RESUME
    except ImportError:
        raise SystemExit(
            "resume_data.py not found. Create it (see resume_data.py.example) "
            "with your real resume in a MY_RESUME variable. This file is "
            "gitignored on purpose - never commit real personal data."
        )

    # Change this to wherever you're job hunting.
    asyncio.run(async_main(MY_RESUME, location="Germany"))
