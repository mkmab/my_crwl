from fastapi import APIRouter

from app.ai.gemini import GeminiAnalyzer
from app.crawler.crawler import WebsiteCrawler
from app.models import AnalysisResponse, AnalyzeRequest, PdfRequest
from app.pdf.report import ReportBuilder


router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(payload: AnalyzeRequest) -> AnalysisResponse:
    crawler = WebsiteCrawler()
    crawl = await crawler.crawl(str(payload.url))
    analyzer = GeminiAnalyzer()
    analysis = await analyzer.analyze(crawl, payload.dom_snapshot)
    pdf_url = ReportBuilder().build(analysis.model_dump())
    data = analysis.model_dump()
    data["pdf_url"] = pdf_url
    return AnalysisResponse(**data)


@router.post("/generate-pdf")
async def generate_pdf(payload: PdfRequest) -> dict[str, str]:
    return {"pdf_url": ReportBuilder().build(payload.analysis)}
