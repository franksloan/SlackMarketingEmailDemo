from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.models.state import AgentState
from agent.nodes import (
    drafting_node,
    editor_node,
    html_check_node,
    html_generator_node,
    image_selector_node,
    internal_research_node,
    planning_node,
    product_lookup_node,
    review_node,
    revision_planner_node,
)

# ---------------------------------------------------------------------------
# Graph definition
#
# Stage 0:  product_lookup ──► (high) ──► planning
#                          └── (low)  ──► END
#
# Stage 1:  planning ──► image_selector ──► END  (stores selected_image in state)
#                    └── Send("internal_research") × N
#
# Stages 2-4 per audience (Command routing — each audience chain is independent):
#   internal_research ──► drafting ──► review ──► html_generator ──► html_check ──► END
#
# review uses Command(goto="html_generator") — NOT Send — so html_generator receives
# the full accumulated graph state, which includes selected_image from image_selector
# (image_selector always completes before the much slower research/draft/review chain).
# ---------------------------------------------------------------------------


def _route_product_lookup(state: AgentState) -> str:
    return "planning" if state["product_lookup"].confidence == "high" else END


def _route_planning(state: AgentState) -> str | list:
    """Route to END with clarification if no audiences matched, otherwise fan out."""
    if state.get("plan_clarification"):
        return END
    target_ids = state.get("target_audience_ids")
    feedback = state.get("feedback")
    audiences = [
        a for a in state["plan"].matched_audiences
        if not target_ids or a.id in target_ids
    ]
    payload_base: dict = {
        "plan": state["plan"],
        "product_lookup": state["product_lookup"],
    }
    if feedback:
        payload_base["feedback"] = feedback
    return ["image_selector"] + [
        Send("internal_research", {**payload_base, "audience": audience})
        for audience in audiences
    ]


_builder = StateGraph(AgentState)

_builder.add_node("product_lookup", product_lookup_node)
_builder.add_node("planning", planning_node)
_builder.add_node("image_selector", image_selector_node)
_builder.add_node("internal_research", internal_research_node)
_builder.add_node("drafting", drafting_node)
_builder.add_node("review", review_node)
_builder.add_node("html_generator", html_generator_node)
_builder.add_node("html_check", html_check_node)

_builder.add_edge(START, "product_lookup")
_builder.add_conditional_edges("product_lookup", _route_product_lookup)
_builder.add_conditional_edges("planning", _route_planning, ["image_selector", "internal_research", END])

# image_selector ends here — result is stored in accumulated state for html_generator to read
_builder.add_edge("image_selector", END)

# per-audience chain: review → html_generator via Command (review_node), then
# html_generator → html_check via Send (html_generator_node) — no static edge needed here
_builder.add_edge("html_check", END)

graph = _builder.compile()


# ---------------------------------------------------------------------------
# Revision graph
#
# START → revision_planner
#   "edit"       → editor ──────────────────────► html_generator → html_check → END
#   "regenerate" → Send("internal_research") × N
#                  each chains: internal_research → drafting → review
#                               → html_generator (via Command) → html_check → END
#
# image_selector is not re-run on revision — selected_image carries over from state.
# ---------------------------------------------------------------------------

def _route_revision(state: AgentState) -> str | list[Send]:
    if state.get("revision_action") == "edit":
        return "editor"
    target_ids = state.get("target_audience_ids")
    feedback = state.get("feedback")
    audiences = [
        a for a in state["plan"].matched_audiences
        if not target_ids or a.id in target_ids
    ]
    payload_base: dict = {
        "plan": state["plan"],
        "product_lookup": state["product_lookup"],
    }
    if feedback:
        payload_base["feedback"] = feedback
    return [
        Send("internal_research", {**payload_base, "audience": audience})
        for audience in audiences
    ]


_rev_builder = StateGraph(AgentState)

_rev_builder.add_node("revision_planner", revision_planner_node)
_rev_builder.add_node("editor", editor_node)
_rev_builder.add_node("internal_research", internal_research_node)
_rev_builder.add_node("drafting", drafting_node)
_rev_builder.add_node("review", review_node)
_rev_builder.add_node("html_generator", html_generator_node)
_rev_builder.add_node("html_check", html_check_node)

_rev_builder.add_edge(START, "revision_planner")
_rev_builder.add_conditional_edges("revision_planner", _route_revision, ["editor", "internal_research"])

# edit path
_rev_builder.add_edge("editor", "html_generator")

# regenerate path: review → html_generator via Command (see review_node)
# html_generator → html_check via Send (html_generator_node) — no static edge needed here
_rev_builder.add_edge("html_check", END)

revision_graph = _rev_builder.compile()
