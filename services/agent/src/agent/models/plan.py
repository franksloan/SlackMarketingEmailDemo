from typing import Literal

from pydantic import BaseModel, Field

from agent.models.audience import AudienceProfile


class CampaignPlan(BaseModel):
    matched_audiences: list[AudienceProfile] = Field(description="Matched audience profiles, max 4")
    primary_objective: str
    tone: str
    content_format: Literal["email", "landing_page"]
    suggested_sections: list[str]
    success_criteria: str
