from typing import Literal

from pydantic import BaseModel


class CampaignBrief(BaseModel):
    raw_text: str
    output_format: Literal["email", "landing_page"] = "email"
