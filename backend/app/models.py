from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class PageContent(BaseModel):
    url: str
    title: str = ""
    meta_description: str = ""
    headings: list[str] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    navigation_links: list[dict[str, str]] = Field(default_factory=list)
    footer: str = ""
    cta_text: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    social_links: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    visible_text: str = ""


class CrawlResult(BaseModel):
    requested_url: str
    final_url: str
    pages: list[PageContent]
    logo_url: str = ""
    favicon_url: str = ""
    og_image_url: str = ""
    screenshot_url: str = ""
    theme_colors: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    owner_name: str | None = None
    owner_email: str | None = None
    owner_first_name: str | None = None
    owner_last_name: str | None = None


class AnalyzeRequest(BaseModel):
    url: HttpUrl
    dom_snapshot: str | None = None
    ai_model: str | None = "auto"


class ResearchRequest(BaseModel):
    crawl: CrawlResult
    dom_snapshot: str | None = None
    ai_model: str | None = "auto"


class PdfRequest(BaseModel):
    analysis: dict[str, Any]


class EmailRequest(BaseModel):
    analysis: dict[str, Any]
    template: str
    ai_model: str | None = "auto"


class StopRequest(BaseModel):
    url: HttpUrl


class EmailResponse(BaseModel):
    subject: str
    body: str
    ai_source: str = "local_fallback"


class AnalysisResponse(BaseModel):
    website_name: str
    website_url: str
    short_summary: str
    detailed_summary: str
    category_analysis: dict[str, Any]
    business_analysis: dict[str, Any]
    branding_analysis: dict[str, Any]
    logo_analysis: dict[str, Any]
    ui_ux_analysis: dict[str, Any]
    seo_analysis: dict[str, Any]
    trust_analysis: dict[str, Any]
    technical_analysis: dict[str, Any]
    content_analysis: dict[str, Any]
    competitor_estimation: dict[str, Any]
    improvement_suggestions: dict[str, Any]
    theme_colors: list[str]
    logo_url: str
    favicon_url: str = ""
    screenshot_url: str = ""
    pdf_url: str = ""
    ai_source: str = "local_fallback"
    owner_name: str | None = None
    owner_email: str | None = None
    owner_first_name: str | None = None
    owner_last_name: str | None = None
