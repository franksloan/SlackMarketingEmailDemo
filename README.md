# SlackMarketingEmailDemo

A Python agent that receives Slack slash commands or events and generates marketing email content using an AI agent.

## Configuration

The agent service expects a `.env` file with:

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
GOOGLE_API_KEY=...
TAVILY_API_KEY=...
```

## Getting Started

Note that this can't be connected to slack when running locally without use of ngrok.

```bash
cd services/agent
uv sync
uv run python -m agent
```

## Architecture

The agent service is a FastAPI app that:

1. Receives Slack events/commands via a webhook endpoint
2. Verifies the Slack request signature
3. Runs an AI agent to generate or refine marketing email content
4. Posts the result back to the originating Slack channel

## Services

### agent (FastAPI) — `services/agent`

Handles the Slack webhook and AI agent orchestration.

**Endpoints:**
- `POST /slack/events` — Slack Events API handler
- `POST /slack/commands` — Slack slash command handler

## Slack examples

1. Slack thread once a draft has been generated
![img.png](good_score.png)

2. Specific warning about the quality being poor
![img.png](review_issue.png)

## Email examples

For a CTO
![img.png](email_example.png)

Reject and use feedback (from the review on slack ex 1)
![img.png](better_cta_button_text.png)

## Diagram
(from diagram.md)

This covers UX, agent outline, storage, integrations

![slack_email_marketer_workflow.png](slack_email_marketer_workflow.png)