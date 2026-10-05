import asyncio
import os
from typing import TypedDict

from agent.llm import llm
from langgraph.types import Command, Send
from pydantic import BaseModel, Field
from tavily import TavilyClient

from agent.models.audience import AudienceProfile
from agent.models.plan import CampaignPlan
from agent.models.product import ProductLookupResult
from agent.models.research import ResearchFindings
from agent.tracing import elapsed_ms, save_trace, start_timer

_llm = llm


class _SynthesisOutput(BaseModel):
    thinking_and_reasoning: str = Field(
        description="Step-by-step reasoning: which search results were most relevant, why these insights and talking points were chosen for this specific audience"
    )
    insights: list[str]
    key_facts: list[str]
    suggested_talking_points: list[str]


_structured = _llm.with_structured_output(_SynthesisOutput)


# Payload shape passed via Send from the orchestrator
class ResearchTask(TypedDict, total=False):
    plan: CampaignPlan
    product_lookup: ProductLookupResult
    audience: AudienceProfile
    feedback: str  # threaded through for revision regenerate runs


def _run_search(query: str) -> list[dict]:
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=query,
        search_depth="advanced",
        include_domains=["aws.amazon.com"],
        max_results=5,
    )
    return response.get("results", [])


async def internal_research_node(task: ResearchTask) -> dict:
    t0 = start_timer()
    product = task["product_lookup"].product
    audience = task["audience"]
    plan = task["plan"]

    query = (
        f"{product.name} {audience.title} "
        f"{audience.pain_points[0] if audience.pain_points else ''}"
    )
    results = await asyncio.to_thread(_run_search, query)

    search_results = "\n\n".join(
        f"Title: {r.get('title')}\nURL: {r.get('url')}\nContent: {r.get('content', '')}"
        for r in results
    )

    # LLM synthesises the search results into structured findings for this audience
    prompt = (
        f"You are a research analyst. Synthesise the following AWS website content into "
        f"structured research findings for the audience below.\n\n"
        f"Audience: {audience.title}\n"
        f"Pain points: {', '.join(audience.pain_points)}\n"
        f"What AWS offers them: {audience.what_aws_offers}\n"
        f"Campaign objective: {plan.primary_objective}\n\n"
        f"AWS search results:\n{search_results}"
    )
    synthesis: _SynthesisOutput = await _structured.ainvoke(prompt)

    findings = ResearchFindings(
        audience_id=audience.id,
        insights=synthesis.insights,
        key_facts=synthesis.key_facts,
        suggested_talking_points=synthesis.suggested_talking_points,
    )
    save_trace(
        node="internal_research",
        inputs={"audience_id": audience.id, "product": product.model_dump(), "query": query, "search_results": search_results},
        thinking_and_reasoning=synthesis.thinking_and_reasoning,
        outputs={"research_findings": findings},
        duration_ms=elapsed_ms(t0),
        label=audience.id,
    )
    draft_task: dict = {"plan": plan, "audience": audience, "research": findings}
    if task.get("feedback"):
        draft_task["feedback"] = task["feedback"]
    return Command(
        update={"research_findings": [findings]},
        goto=Send("drafting", draft_task),
    )
