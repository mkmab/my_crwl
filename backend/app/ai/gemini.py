import asyncio
import json
from typing import Any

from app.models import AnalysisResponse, CrawlResult
from app.utils.config import settings


ANALYSIS_SCHEMA_KEYS = [
    "website_name",
    "short_summary",
    "detailed_summary",
    "category_analysis",
    "business_analysis",
    "branding_analysis",
    "logo_analysis",
    "ui_ux_analysis",
    "seo_analysis",
    "trust_analysis",
    "technical_analysis",
    "content_analysis",
    "competitor_estimation",
    "improvement_suggestions",
]

GEMINI_MODEL_FALLBACKS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]


class GeminiAnalyzer:
    async def analyze(self, crawl: CrawlResult, dom_snapshot: str | None = None) -> AnalysisResponse:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for AI analysis.")

        fallback = self.local_analysis(crawl)

        try:
            import google.generativeai as genai
            import traceback

            genai.configure(api_key=settings.gemini_api_key)
            response = await asyncio.wait_for(
                asyncio.to_thread(self._generate_with_available_model_sync, genai, self._prompt(crawl, dom_snapshot)),
                timeout=settings.gemini_timeout_seconds,
            )
            text = getattr(response, "text", None) or getattr(response, "output", None) or str(response)
            parsed = self._parse_json(text)
            # Normalize parsed output: fields expected as dicts should be dicts
            dict_fields = [
                "category_analysis",
                "business_analysis",
                "branding_analysis",
                "logo_analysis",
                "ui_ux_analysis",
                "seo_analysis",
                "trust_analysis",
                "technical_analysis",
                "content_analysis",
                "competitor_estimation",
                "improvement_suggestions",
            ]
            for f in dict_fields:
                if f in parsed and parsed[f] is not None and not isinstance(parsed[f], dict):
                    parsed[f] = {"details": parsed[f]}

            merged = fallback.model_dump()
            merged.update({key: parsed.get(key, merged.get(key)) for key in ANALYSIS_SCHEMA_KEYS})
            # Only set ai_source after validation succeeds
            merged_candidate = dict(merged)
            merged_candidate["ai_source"] = "gemini"
            # Ensure merged_candidate dict fields are proper dicts
            for f in dict_fields:
                if f in merged_candidate and merged_candidate[f] is not None and not isinstance(merged_candidate[f], dict):
                    merged_candidate[f] = {"details": merged_candidate[f]}
            result = AnalysisResponse(**merged_candidate)
            return result
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            raise RuntimeError(
                "Gemini analysis failed. Check the API key, model quota, billing, and model name.\n"
                f"{exc}\n{tb}"
            ) from exc

    def _generate_with_available_model_sync(self, genai, prompt: str):
        model_names = list(dict.fromkeys([settings.gemini_model, *GEMINI_MODEL_FALLBACKS]))
        errors: list[str] = []
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt)
            except Exception as exc:
                errors.append(f"{model_name}: {exc}")

        raise RuntimeError("No configured Gemini model could generate content. Tried " + "; ".join(errors))

    def local_analysis(self, crawl: CrawlResult) -> AnalysisResponse:
        primary = crawl.pages[0] if crawl.pages else None
        title = primary.title if primary else "Unknown website"
        text = " ".join(page.visible_text for page in crawl.pages)[:12000]
        category = self._infer_category(text)
        summary = self._summary(primary)
        seo_score = self._score(bool(primary and primary.title), bool(primary and primary.meta_description), len(primary.headings if primary else []))
        trust_score = min(95, 35 + len(self._emails(crawl)) * 8 + len(self._phones(crawl)) * 8 + len(self._socials(crawl)) * 4)

        return AnalysisResponse(
            website_name=title or crawl.final_url,
            website_url=crawl.final_url,
            short_summary=summary,
            detailed_summary=f"{summary} The site appears to operate in the {category.lower()} space based on its content, navigation, calls to action, and page structure.",
            category_analysis={"primary_category": category, "confidence": "medium", "signals": self._keywords(text)},
            business_analysis={
                "business_model": "Lead generation, ecommerce, subscription, or service sales depending on visible CTAs.",
                "products_services": self._offerings(crawl),
                "target_audience": "Prospective customers researching solutions, pricing, credibility, and next steps.",
            },
            branding_analysis={
                "primary_color": crawl.theme_colors[0] if crawl.theme_colors else "",
                "secondary_colors": crawl.theme_colors[1:5],
                "ui_style": "Modern marketing or product website",
                "branding_personality": self._personality(crawl.theme_colors),
            },
            logo_analysis={"logo_url": crawl.logo_url, "favicon_url": crawl.favicon_url, "og_image_url": crawl.og_image_url},
            ui_ux_analysis={"quality": "moderate", "cta_count": sum(len(page.cta_text) for page in crawl.pages), "notes": "Review hierarchy, mobile clarity, and CTA prominence."},
            seo_analysis={"quality_score": seo_score, "has_title": bool(primary and primary.title), "has_meta_description": bool(primary and primary.meta_description), "heading_count": len(primary.headings if primary else [])},
            trust_analysis={"trust_score": trust_score, "emails": self._emails(crawl), "phones": self._phones(crawl), "social_links": self._socials(crawl)},
            technical_analysis={"technologies": crawl.technologies, "pages_crawled": len(crawl.pages), "uses_dynamic_rendering": "Next.js" in crawl.technologies or "React" in crawl.technologies},
            content_analysis={"headings": primary.headings[:12] if primary else [], "cta_text": primary.cta_text[:12] if primary else [], "content_depth": len(text)},
            competitor_estimation={"likely_competitor_types": ["Direct category competitors", "local providers", "SaaS alternatives"], "positioning": "Requires Gemini or manual review for precise competitor names."},
            improvement_suggestions={
                "priority": ["Clarify above-the-fold value proposition", "Add stronger proof points", "Improve metadata and structured content", "Make primary CTA consistent"],
                "quick_wins": ["Add customer logos or testimonials", "Ensure contact methods are visible", "Compress images and improve performance"],
            },
            theme_colors=crawl.theme_colors,
            logo_url=crawl.logo_url,
            favicon_url=crawl.favicon_url,
            screenshot_url=crawl.screenshot_url,
        )

    def _prompt(self, crawl: CrawlResult, dom_snapshot: str | None) -> str:
        payload = crawl.model_dump()
        if dom_snapshot:
            payload["extension_dom_snapshot"] = dom_snapshot[:10000]
        return (
            "Analyze this website as a senior business intelligence, brand, SEO, UX, and conversion analyst. "
            "Return only valid JSON with these keys: "
            + ", ".join(ANALYSIS_SCHEMA_KEYS)
            + ". Use concise but specific recommendations. Input:\n"
            + json.dumps(payload, ensure_ascii=True)[:60000]
        )

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(cleaned)

    def _summary(self, page) -> str:
        if not page:
            return "The website could not be fully summarized from the crawled content."
        if page.meta_description:
            return page.meta_description
        if page.headings:
            return " ".join(page.headings[:2])
        return page.visible_text[:240] or "The website presents business information and conversion paths."

    def _infer_category(self, text: str) -> str:
        lower = text.lower()
        categories = {
            "Software / SaaS": ("software", "platform", "api", "workflow", "automation", "dashboard"),
            "Ecommerce": ("cart", "shop", "product", "shipping", "checkout"),
            "Agency / Services": ("agency", "consulting", "services", "strategy", "solutions"),
            "Education": ("course", "learn", "student", "training", "school"),
            "Healthcare": ("patient", "clinic", "health", "medical", "care"),
            "Finance": ("bank", "payment", "investment", "loan", "insurance"),
        }
        scores = {name: sum(token in lower for token in tokens) for name, tokens in categories.items()}
        return max(scores, key=scores.get) if max(scores.values()) else "General Business"

    def _offerings(self, crawl: CrawlResult) -> list[str]:
        phrases: list[str] = []
        for page in crawl.pages:
            phrases.extend(page.headings[:8])
            phrases.extend(page.buttons[:5])
        return list(dict.fromkeys(phrase for phrase in phrases if len(phrase) > 3))[:12]

    def _keywords(self, text: str) -> list[str]:
        words = [word.lower() for word in text.split() if len(word) > 5 and word.isalpha()]
        counts: dict[str, int] = {}
        for word in words:
            counts[word] = counts.get(word, 0) + 1
        return [word for word, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]]

    def _personality(self, colors: list[str]) -> str:
        if not colors:
            return "Content-led and functional"
        return "Polished, digital, and conversion-oriented"

    def _score(self, has_title: bool, has_meta: bool, headings: int) -> int:
        return min(100, 35 + (25 if has_title else 0) + (25 if has_meta else 0) + min(15, headings * 2))

    def _emails(self, crawl: CrawlResult) -> list[str]:
        return sorted({email for page in crawl.pages for email in page.emails})

    def _phones(self, crawl: CrawlResult) -> list[str]:
        return sorted({phone for page in crawl.pages for phone in page.phone_numbers})

    def _socials(self, crawl: CrawlResult) -> list[str]:
        return sorted({link for page in crawl.pages for link in page.social_links})
