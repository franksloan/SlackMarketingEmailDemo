import asyncio
import os
from typing import Literal

from agent.llm import llm
from pydantic import BaseModel, Field
from tavily import TavilyClient

from agent.models.product import ProductLookupResult, ProductMatch
from agent.models.state import AgentState
from agent.tracing import elapsed_ms, save_trace, start_timer

_llm = llm

_AWS_PRODUCTS_URL = "https://aws.amazon.com/products/"

# ---------------------------------------------------------------------------
# Internal models
# ---------------------------------------------------------------------------

class _ProductName(BaseModel):
    name: str | None = Field(
        description="The AWS product or service name extracted from the brief, or None if unrecognisable"
    )


class _ProductSelection(BaseModel):
    thinking_and_reasoning: str = Field(
        description="Step-by-step reasoning: how the catalog and search results were evaluated, why this URL was chosen as the canonical product page"
    )
    selected_name: str | None = Field(
        description="The canonical AWS product name, or None if no clear match"
    )
    selected_url: str | None = Field(
        description="The direct URL to the dedicated AWS product page, or None if no clear match"
    )
    confidence: Literal["high", "low"] = Field(
        description=(
            "high only if one result is clearly the dedicated product page "
            "(e.g. aws.amazon.com/s3/ or aws.amazon.com/ec2/); "
            "low if uncertain or multiple products could match"
        )
    )


_name_extractor = _llm.with_structured_output(_ProductName)
_page_selector = _llm.with_structured_output(_ProductSelection)

# ---------------------------------------------------------------------------
# Tavily helpers (sync — run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _extract_products_catalog() -> str:
    """Fetch the AWS products catalog page and return its text content."""
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.extract(urls=[_AWS_PRODUCTS_URL])
    results = response.get("results", [])
    if results:
        return results[0].get("raw_content", "")
    return ""


def _search_product_pages(product_name: str) -> list[dict]:
    """Targeted search for the product's dedicated page on aws.amazon.com."""
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=f"{product_name} AWS product",
        search_depth="advanced",
        include_domains=["aws.amazon.com"],
        max_results=8,
    )
    return response.get("results", [])

# ---------------------------------------------------------------------------
# URL scoring — prefer dedicated product pages over supporting content
# ---------------------------------------------------------------------------

_PENALISED_SEGMENTS = {
    "blogs", "blog", "solutions", "getting-started", "documentation",
    "whitepapers", "case-studies", "partners", "training", "events",
    "about", "resources", "marketplace", "news", "analyst-reports",
}


def _score_result(url: str, content: str, product_name: str) -> int:
    path = url.lower().replace("https://aws.amazon.com", "").replace("http://aws.amazon.com", "")
    segments = [s for s in path.strip("/").split("/") if s]
    score = 0

    if len(segments) == 1:
        score += 4
    elif len(segments) == 2:
        score += 2

    if any(s in _PENALISED_SEGMENTS for s in segments):
        score -= 5

    name_slug = product_name.lower().replace(" ", "-").replace("_", "-").replace("amazon ", "")
    if name_slug in path or name_slug.replace("-", "") in path:
        score += 3

    content_lower = content.lower()
    for keyword in ("product", "service", "features", "pricing", "get started"):
        if keyword in content_lower:
            score += 1

    return score

# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def product_lookup_node(state: AgentState) -> dict:
    # On revision runs the product is already known — skip the expensive lookup
    existing = state.get("product_lookup")
    if existing and existing.confidence == "high":
        return {}

    t0 = start_timer()
    brief = state["brief"]

    # Stage 1 — extract the product name from the brief
    identified: _ProductName = await _name_extractor.ainvoke(
        f"Extract the AWS product or service name being referenced in this brief. "
        f"Return only the product name.\n\nBrief: {brief.raw_text}"
    )

    if not identified.name:
        result = ProductLookupResult(
            confidence="low",
            clarification_message=(
                "I couldn't identify an AWS product from your brief. "
                "Could you name the specific AWS service or product you'd like to promote?"
            ),
        )
        save_trace(
            node="product_lookup",
            inputs={"brief": brief.raw_text},
            thinking_and_reasoning="No product name could be extracted from the brief.",
            outputs={"product_lookup": result},
            duration_ms=elapsed_ms(t0),
        )
        return {"product_lookup": result}

    product_name = identified.name

    # Stage 2 — in parallel: extract the AWS products catalog + search for the product page
    catalog_task = asyncio.to_thread(_extract_products_catalog)
    search_task = asyncio.to_thread(_search_product_pages, product_name)
    catalog_content, search_results = await asyncio.gather(catalog_task, search_task)

    # Score and rank the search results
    seen: dict[str, dict] = {}
    for r in search_results:
        url = r.get("url", "")
        if not url:
            continue
        score = _score_result(url, r.get("content", ""), product_name)
        if url not in seen or score > seen[url]["_score"]:
            seen[url] = {**r, "_score": score}

    ranked = sorted(seen.values(), key=lambda r: r["_score"], reverse=True)[:8]

    search_summary = "\n".join(
        f"[score {r['_score']}] {r.get('title', '')} — {r.get('url', '')}\n"
        f"  {r.get('content', '')[:200]}"
        for r in ranked
    ) if ranked else "No search results found."

    # Truncate catalog content to avoid exceeding context limits
    catalog_excerpt = catalog_content[:4000] if catalog_content else "Catalog not available."

    # Stage 3 — LLM selects the canonical product page using both sources
    selection: _ProductSelection = await _page_selector.ainvoke(
        f"You are identifying the dedicated AWS product page for a specific product.\n\n"
        f"Product being searched: {product_name}\n\n"
        f"--- AWS Products Catalog (from aws.amazon.com/products/) ---\n"
        f"{catalog_excerpt}\n\n"
        f"--- Search results (pre-scored, higher = more likely a product page) ---\n"
        f"{search_summary}\n\n"
        f"Using both sources above, identify the single direct URL to the dedicated product "
        f"landing page (e.g. aws.amazon.com/s3/ or aws.amazon.com/ec2/). "
        f"Prefer URLs found in the products catalog. "
        f"Set confidence='high' only if you are certain this is the canonical product page. "
        f"Set confidence='low' if multiple products could match or no clear product page was found."
    )

    if selection.confidence == "high" and selection.selected_url and selection.selected_name:
        result = ProductLookupResult(
            confidence="high",
            product=ProductMatch(
                name=selection.selected_name,
                url=selection.selected_url,
            ),
        )
        save_trace(
            node="product_lookup",
            inputs={"brief": brief.raw_text, "product_name": product_name, "search_summary": search_summary},
            thinking_and_reasoning=selection.thinking_and_reasoning,
            outputs={"product_lookup": result},
            duration_ms=elapsed_ms(t0),
        )
        return {"product_lookup": result}

    # Ambiguous — surface top candidates for the user to clarify
    candidates = [
        ProductMatch(name=r.get("title", r.get("url", "")), url=r.get("url", ""))
        for r in ranked[:5]
    ]
    clarification = (
        f"I found several AWS pages related to '{product_name}' but couldn't confirm "
        f"the dedicated product page. Could you clarify which one you meant?\n\n"
        + "\n".join(f"- {c.name}: {c.url}" for c in candidates)
        if candidates
        else (
            f"I couldn't find a dedicated AWS product page for '{product_name}'. "
            f"Could you double-check the product name or provide a URL?"
        )
    )

    result = ProductLookupResult(
        confidence="low",
        candidates=candidates,
        clarification_message=clarification,
    )
    save_trace(
        node="product_lookup",
        inputs={"brief": brief.raw_text, "product_name": product_name, "search_summary": search_summary},
        thinking_and_reasoning=selection.thinking_and_reasoning,
        outputs={"product_lookup": result},
        duration_ms=elapsed_ms(t0),
    )
    return {"product_lookup": result}
