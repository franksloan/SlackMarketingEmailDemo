import operator
from typing import Annotated, Literal, TypedDict

from agent.models.brief import CampaignBrief
from agent.models.draft import ContentDraft
from agent.models.plan import CampaignPlan
from agent.models.product import ProductLookupResult
from agent.models.research import ResearchFindings
from agent.models.review import ReviewResult


class AgentState(TypedDict, total=False):
    brief: CampaignBrief
    product_lookup: ProductLookupResult
    plan: CampaignPlan
    # Annotated with operator.add so parallel node writes are appended, not overwritten
    research_findings: Annotated[list[ResearchFindings], operator.add]
    drafts: Annotated[list[ContentDraft], operator.add]
    reviews: Annotated[list[ReviewResult], operator.add]
    plan_clarification: str
    reviewed_drafts: Annotated[list[ContentDraft], operator.add]
    selected_image: dict | None
    image_alternatives: list[dict]
    html_file_paths: Annotated[list[str], operator.add]
    html_check_results: Annotated[list[dict], operator.add]
    # Revision fields — set when re-running after a marketer rejection
    feedback: str                     # marketer's rejection feedback for this revision
    previous_trace_path: str          # path to the trace JSON from the previous run
    target_audience_ids: list[str]    # if set, only research/draft for these audience IDs
    existing_draft: ContentDraft      # the draft being revised (used by editor node)
    revision_action: Literal["edit", "regenerate"]  # decision from revision_planner
