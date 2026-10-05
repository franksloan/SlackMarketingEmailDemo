from pydantic import BaseModel, Field

JUDGE_CRITERIA = [
    "pain_point_coverage",
    "brand_voice",
    "cta_quality",
    "subject_line_quality",
    "audience_specificity",
    "factual_grounding",
]


class ReviewResult(BaseModel):
    audience_id: str
    approved: bool
    overall_score: int = Field(ge=1, le=10)
    text_feedback: str
    visual_feedback: str
    layout_feedback: str
    issues: list[str]
    suggestions: list[str]
    # Judge scores (1-5 per criterion) — populated by review_node, consumed by eval judge
    judge_scores: dict[str, int] = Field(default_factory=dict)
