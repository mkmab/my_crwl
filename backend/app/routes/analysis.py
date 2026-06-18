import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException

from app.ai.gemini import GeminiAnalyzer
from app.ai.huggingface import HuggingFaceAnalyzer
from app.crawler.crawler import WebsiteCrawler
from app.models import AnalysisResponse, AnalyzeRequest, CrawlResult, EmailRequest, EmailResponse, PdfRequest, ResearchRequest
from app.pdf.report import ReportBuilder
from app.utils.config import settings


router = APIRouter()
TASKS: dict[str, asyncio.Task] = {}
logger = logging.getLogger(__name__)
ProviderName = Literal["gemini", "huggingface"]


def _provider_order(ai_choice: str | None) -> list[ProviderName]:
    choice = (ai_choice or "auto").lower()
    if choice == "huggingface":
        return ["huggingface", "gemini"]
    return ["gemini", "huggingface"]


def _make_analyzer(provider: ProviderName):
    return GeminiAnalyzer() if provider == "gemini" else HuggingFaceAnalyzer()


def _timeout_for(provider: ProviderName) -> int:
    if provider == "gemini":
        return max(settings.gemini_timeout_seconds + 5, 10)
    return max(settings.huggingface_timeout_seconds + 5, 10)


async def _run_analysis_with_fallbacks(payload: ResearchRequest) -> AnalysisResponse:
    crawl = payload.crawl
    last_result: AnalysisResponse | None = None
    provider_errors: list[str] = []

    for provider in _provider_order(payload.ai_model):
        analyzer = _make_analyzer(provider)
        logger.warning("research: %s start %s", provider, crawl.final_url)
        try:
            task = asyncio.create_task(analyzer.analyze(crawl, payload.dom_snapshot))
            TASKS[crawl.final_url] = task
            result = await asyncio.wait_for(task, timeout=_timeout_for(provider))
            TASKS.pop(crawl.final_url, None)
            if result.ai_source != "local_fallback":
                return result
            last_result = result
            provider_errors.append(f"{provider}: returned local fallback")
        except asyncio.TimeoutError:
            logger.exception("research: %s timeout %s", provider, crawl.final_url)
            TASKS.pop(crawl.final_url, None)
            provider_errors.append(f"{provider}: timed out")
        except RuntimeError as exc:
            logger.exception("research: %s failed %s", provider, crawl.final_url)
            TASKS.pop(crawl.final_url, None)
            provider_errors.append(f"{provider}: {exc}")
        except Exception as exc:
            logger.exception("research: %s unexpected failure %s", provider, crawl.final_url)
            TASKS.pop(crawl.final_url, None)
            provider_errors.append(f"{provider}: {exc}")

    if last_result is not None:
        if provider_errors:
            data = last_result.model_dump()
            data["ai_failure_reason"] = f"AI providers unavailable: {'; '.join(provider_errors[:2])}."
            data["short_summary"] = (
                f"[AI providers unavailable: {'; '.join(provider_errors[:2])}. Showing local analysis.] "
                + (last_result.short_summary or "")
            )[:900]
            return AnalysisResponse(**data)
        return last_result

    fallback = GeminiAnalyzer().local_analysis(crawl)
    data = fallback.model_dump()
    data["ai_source"] = "local_fallback"
    data["ai_failure_reason"] = (
        f"All AI providers failed: {'; '.join(provider_errors)}."
    )
    data["short_summary"] = (
        "[All AI providers failed. Showing local analysis.] "
        + (fallback.short_summary or "")
    )[:900]
    return AnalysisResponse(**data)


async def _run_email_with_fallbacks(payload: EmailRequest) -> EmailResponse:
    last_result: EmailResponse | None = None

    for provider in _provider_order(payload.ai_model):
        analyzer = _make_analyzer(provider)
        try:
            result = await analyzer.generate_email(payload.analysis, payload.template)
            if result.ai_source != "local_fallback":
                return result
            last_result = result
        except Exception:
            logger.exception("email: %s failed", provider)

    return last_result or GeminiAnalyzer().local_email(payload.analysis, payload.template)


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(payload: AnalyzeRequest) -> AnalysisResponse:
    analysis = await research(payload)
    logger.warning("analyze: pdf start %s", analysis.website_url)
    pdf_url = ReportBuilder().build(analysis.model_dump())
    logger.warning("analyze: pdf done %s", pdf_url)
    data = analysis.model_dump()
    data["pdf_url"] = pdf_url
    return AnalysisResponse(**data)


@router.post("/research", response_model=AnalysisResponse)
async def research(payload: AnalyzeRequest) -> AnalysisResponse:
    crawl = await crawl_site(payload)
    return await research_from_crawl(
        ResearchRequest(
            crawl=crawl,
            dom_snapshot=payload.dom_snapshot,
            ai_model=payload.ai_model,
        )
    )


@router.post("/crawl", response_model=CrawlResult)
async def crawl_site(payload: AnalyzeRequest) -> CrawlResult:
    logger.warning("crawl: start %s", payload.url)
    crawler = WebsiteCrawler()
    crawl = await crawler.crawl(str(payload.url))
    logger.warning("crawl: done %s pages=%s", crawl.final_url, len(crawl.pages))
    return crawl


@router.post("/research-from-crawl", response_model=AnalysisResponse)
async def research_from_crawl(payload: ResearchRequest) -> AnalysisResponse:
    return await _run_analysis_with_fallbacks(payload)


@router.post("/generate-email", response_model=EmailResponse)
async def generate_email(payload: EmailRequest) -> EmailResponse:
    return await _run_email_with_fallbacks(payload)


@router.post("/stop")
async def stop_analysis(payload: dict) -> dict:
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    task = TASKS.get(str(url))
    if not task:
        return {"stopped": False, "reason": "no active task"}
    task.cancel()
    TASKS.pop(str(url), None)
    logger.warning("stop: cancelled %s", url)
    return {"stopped": True}


@router.post("/generate-pdf")
async def generate_pdf(payload: PdfRequest) -> dict[str, str]:
    return {"pdf_url": ReportBuilder().build(payload.analysis)}
