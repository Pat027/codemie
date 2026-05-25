# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | CodeMie backend | README.md:19 |
| Repository/package | codemie | pyproject.toml:1 |
| Project code/key | EPMCDME | README.md:162 |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Jira |
| Key/prefix | EPMCDME |
| Adapter status | configured |
| Adapter instructions | Use the Brianna/Jira workflow when a task requires ticket lookup; commit and MR skills require an `EPMCDME-####` ticket. |

## Ticket Adapter

**Status**: configured
**Adapter**: `brianna` skill — invoke via the `Skill` tool with the approved story content or file path as the argument. Do not hardcode the underlying command or assistant ID.
**Lookup**: Invoke the `brianna` skill with the ticket key or URL and request summary, description, acceptance criteria, status, assignee, issue type, and relevant links. Use `--conversation-id` for multi-turn flows.
**Create**: Invoke the `brianna` skill with the complete ticket payload or the approved story file attached. Do not use conversational references such as "as drafted" unless `--conversation-id` is used and the create call includes the full final payload.
**Multi-turn follow-up**: pass `--conversation-id <id>` returned from the first call to maintain context across calls.
**Output**: Jira ticket key and URL.

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitLab |
| Repository remote | git@gitbud.epam.com:epm-cdme/codemie.git |
| Default target branch | main |
| Review artifact type | MR |

## MR Adapter

**Status**: configured
**Adapter**: GitLab CLI (`glab`) via project MR skills
**Instructions**: Use `.ai-run/guides/standards/git-workflow.md` for branch, commit, push, and MR rules before creating review artifacts.
