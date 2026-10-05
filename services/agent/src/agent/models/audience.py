from pydantic import BaseModel


class AudienceMessaging(BaseModel):
    primary_headline: str
    secondary_headline: str
    body_themes: list[str]


class AudienceProfile(BaseModel):
    id: str
    title: str
    description: str
    pain_points: list[str]
    what_aws_offers: str
    messaging: AudienceMessaging
