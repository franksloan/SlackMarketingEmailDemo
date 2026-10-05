from pydantic import BaseModel, Field


class BodySection(BaseModel):
    heading: str = Field(description="Section heading — use an empty string if this section has no heading")
    body: str = Field(description="Section body text — 2-4 sentences")


class ContentDraft(BaseModel):
    audience_id: str
    subject_line: str
    headline: str
    subheadline: str
    body_sections: list[BodySection] = Field(
        description="3-5 body sections, each with a heading and body text"
    )
    primary_cta_text: str
    primary_cta_url: str
    secondary_cta_text: str | None = None
    secondary_cta_url: str | None = None
    secondary_body: str | None = Field(
        default=None,
        description="1-2 sentence intro to the secondary CTA — should explain what the reader will find at the link (e.g. customer stories, a demo, a guide) and why it's relevant to them"
    )
    sign_off: str | None = None
