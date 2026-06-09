import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.ai.gemini import GeminiAnalyzer
from app.crawler.crawler import WebsiteCrawler
from app.models import AnalysisResponse, AnalyzeRequest, CrawlResult, EmailRequest, EmailResponse, PdfRequest, ResearchRequest
from app.pdf.report import ReportBuilder
from app.utils.config import settings


router = APIRouter()
logger = logging.getLogger(__name__)


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
    return await research_from_crawl(ResearchRequest(crawl=crawl, dom_snapshot=payload.dom_snapshot))


@router.post("/crawl", response_model=CrawlResult)
async def crawl_site(payload: AnalyzeRequest) -> CrawlResult:
    logger.warning("crawl: start %s", payload.url)
    crawler = WebsiteCrawler()
    crawl = await crawler.crawl(str(payload.url))
    logger.warning("crawl: done %s pages=%s", crawl.final_url, len(crawl.pages))
    return crawl


@router.post("/research-from-crawl", response_model=AnalysisResponse)
async def research_from_crawl(payload: ResearchRequest) -> AnalysisResponse:
    crawl = payload.crawl
    analyzer = GeminiAnalyzer()
    logger.warning("research: gemini start %s", crawl.final_url)
    try:
        analysis = await asyncio.wait_for(
            analyzer.analyze(crawl, payload.dom_snapshot),
            timeout=max(settings.gemini_timeout_seconds + 5, 10),
        )
    except asyncio.TimeoutError as exc:
        logger.exception("research: gemini timeout %s", crawl.final_url)
        raise HTTPException(status_code=504, detail="Gemini analysis timed out. Check model quota or increase the timeout.") from exc
    except RuntimeError as exc:
        logger.exception("research: gemini failed %s", crawl.final_url)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return analysis


@router.post("/generate-email", response_model=EmailResponse)
async def generate_email(payload: EmailRequest) -> EmailResponse:
    analyzer = GeminiAnalyzer()
    return await analyzer.generate_email(payload.analysis, payload.template)


@router.post("/generate-pdf")
async def generate_pdf(payload: PdfRequest) -> dict[str, str]:
    return {"pdf_url": ReportBuilder().build(payload.analysis)}
