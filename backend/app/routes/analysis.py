import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.ai.gemini import GeminiAnalyzer
from app.crawler.crawler import WebsiteCrawler
from app.models import AnalysisResponse, AnalyzeRequest, PdfRequest
from app.pdf.report import ReportBuilder
from app.utils.config import settings


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(payload: AnalyzeRequest) -> AnalysisResponse:
    logger.warning("analyze: crawl start %s", payload.url)
    crawler = WebsiteCrawler()
    crawl = await crawler.crawl(str(payload.url))
    logger.warning("analyze: crawl done %s pages=%s", crawl.final_url, len(crawl.pages))
    analyzer = GeminiAnalyzer()
    logger.warning("analyze: gemini start %s", crawl.final_url)
    try:
        analysis = await asyncio.wait_for(
            analyzer.analyze(crawl, payload.dom_snapshot),
            timeout=max(settings.gemini_timeout_seconds + 5, 10),
        )
    except asyncio.TimeoutError as exc:
        logger.exception("analyze: gemini timeout %s", crawl.final_url)
        raise HTTPException(status_code=504, detail="Gemini analysis timed out. Check model quota or increase the timeout.") from exc
    except RuntimeError as exc:
        logger.exception("analyze: gemini failed %s", crawl.final_url)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.warning("analyze: pdf start %s", crawl.final_url)
    pdf_url = ReportBuilder().build(analysis.model_dump())
    logger.warning("analyze: pdf done %s", pdf_url)
    data = analysis.model_dump()
    data["pdf_url"] = pdf_url
    return AnalysisResponse(**data)


@router.post("/generate-pdf")
async def generate_pdf(payload: PdfRequest) -> dict[str, str]:
    return {"pdf_url": ReportBuilder().build(payload.analysis)}
