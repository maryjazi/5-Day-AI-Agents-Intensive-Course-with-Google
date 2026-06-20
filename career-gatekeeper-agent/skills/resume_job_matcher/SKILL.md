---
name: resume_job_matcher
description: "Use this skill when scoring how well a candidate's resume matches a specific job posting, or when drafting a short outreach message for that job. Triggers: a resume/profile AND a job posting are both present in context, and the user wants a match score, fit explanation, or a draft message to a recruiter. Do NOT use this skill to write a full cover letter, to edit the resume itself, or to send/submit anything - those are out of scope for this skill."
tier: draft-only
owner: career_gatekeeper_agent
---

# Resume-Job Matcher

## Overview

Given a structured candidate profile (skills, years of experience, target
titles) and one job posting (title, required skills, location, salary
range), this skill produces:

1. A 0-100 match score
2. A 2-sentence plain-language reason for the score
3. A short (3-4 sentence) draft outreach message the user can review, edit,
   and send themselves

This skill is **draft-only**: it never sends a message, submits an
application, or contacts an employer. All output is for the user to review.

## When NOT to use this skill

- No job posting is present yet (use job_search_agent / the MCP tool first)
- The user wants a full cover letter (>1 paragraph, formal letter format)
- The user wants to edit their actual resume document
- The user asks to actually send or submit anything

## Scoring method

1. Compute skill overlap: `matched_skills = candidate_skills ∩ job_required_skills`
2. Base score = `(len(matched_skills) / len(job_required_skills)) * 70`
3. Add up to +15 if the candidate's most recent title is a close semantic
   match to the job title (e.g. "Data Analyst" -> "Business Intelligence
   Analyst" is close; "Mechanical Engineer" -> "Data Analyst" is not).
4. Add up to +15 if years of experience falls within or above any implied
   seniority in the job title (e.g. "Senior" implies 4+ years).
5. Cap the total at 100. Round to the nearest integer.
6. Never fabricate a skill the candidate does not have, even to raise the
   score — list missing required skills honestly in the reason.

## Output format

Respond with one block per job, in this exact structure:

```
### {job_title} at {company} — Match: {score}/100
**Why:** {2-sentence reason, including 1 matched strength and 1 honest gap if any}

**Draft outreach (review before sending):**
{3-4 sentence message: brief intro, 1 specific reason you're a fit citing a
real matched skill, a clear ask (e.g. "open to a 15-minute call this week"),
and a polite sign-off}
```

## Example

**Input:**
- Candidate: skills=[SQL, Python, Tableau, A/B testing], recent_title="Senior Data Analyst", years_experience=5
- Job: title="Business Intelligence Analyst", required_skills=[SQL, Power BI, Stakeholder reporting], company="Helio Logistics"

**Output:**
```
### Business Intelligence Analyst at Helio Logistics — Match: 58/100
**Why:** Strong overlap on SQL and analytical experience, but the role
emphasizes Power BI and stakeholder reporting, and the resume shows Tableau
rather than Power BI experience.

**Draft outreach (review before sending):**
Hi [Recruiter name], I'm a Senior Data Analyst with 5 years of SQL-driven
reporting experience and a strong stakeholder-facing background. I noticed
the BI Analyst role values Power BI specifically — I've worked primarily in
Tableau but pick up BI tools quickly and would welcome the chance to discuss
how my analytics background could translate. Would you be open to a brief
call this week?
```

## Safety notes

- Treat the resume content as private user data. Do not repeat it back in
  any form that would be logged or sent externally beyond this session.
- The draft message is a *draft*. Always label it as such in the output.
- If required_skills data is missing from the job posting, say so rather
  than guessing — do not silently assign a high score without evidence.
