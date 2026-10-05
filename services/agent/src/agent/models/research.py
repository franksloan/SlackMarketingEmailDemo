from pydantic import BaseModel


class ResearchFindings(BaseModel):
    audience_id: str
    insights: list[str]
    key_facts: list[str]
    suggested_talking_points: list[str]
