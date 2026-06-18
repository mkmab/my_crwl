import asyncio
import json
from typing import Any

import requests

from app.models import AnalysisResponse, CrawlResult, EmailResponse
from app.utils.config import settings
from app.utils.url import extract_domain, extract_company_name


# ---------------------------------------------------------------------------
# Sentinel exception — raised internally when ALL models return 429.
# Caught in analyze() / generate_email() to return local_analysis gracefully.
# ---------------------------------------------------------------------------

class _QuotaExhaustedError(Exception):
    """All Gemini models have exhausted their free-tier daily quota."""


# ---------------------------------------------------------------------------
# Schema keys returned by Gemini
# ---------------------------------------------------------------------------

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

DICT_FIELDS = [
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

# ---------------------------------------------------------------------------
# Free-tier model list — ordered cheapest/fastest first.
# All share the same daily quota pool on the free tier (20 req/day total).
# We try them in order; on 429 we respect the retry_delay from the error.
# ---------------------------------------------------------------------------

GEMINI_MODEL_FALLBACKS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash-8b",
]

# How long (seconds) to wait between model retries when rate-limited.
# The API returns a retry_delay; we cap it so the request doesn't hang forever.
_MAX_RETRY_WAIT = 45


# ---------------------------------------------------------------------------
# Main analyser class
# ---------------------------------------------------------------------------

class GeminiAnalyzer:

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, crawl: CrawlResult, dom_snapshot: str | None = None) -> AnalysisResponse:
        if not settings.gemini_api_key:
            return self.local_analysis(crawl)

        fallback = self.local_analysis(crawl)

        try:
            prompt = self._prompt(crawl, dom_snapshot)
            text = await asyncio.wait_for(
                asyncio.to_thread(
                    self._generate_with_available_model_sync,
                    prompt,
                    2200,
                    True,
                ),
                timeout=settings.gemini_timeout_seconds,
            )
            parsed = self._parse_json(text)
            if not self._looks_like_analysis_payload(parsed):
                raise RuntimeError("Gemini returned unusable analysis JSON.")

            for f in DICT_FIELDS:
                if f in parsed and parsed[f] is not None and not isinstance(parsed[f], dict):
                    parsed[f] = {"details": parsed[f]}

            merged = fallback.model_dump()
            merged.update({key: parsed.get(key, merged.get(key)) for key in ANALYSIS_SCHEMA_KEYS})
            merged["ai_source"] = "gemini"

            for f in DICT_FIELDS:
                if f in merged and merged[f] is not None and not isinstance(merged[f], dict):
                    merged[f] = {"details": merged[f]}

            return AnalysisResponse(**merged)

        except _QuotaExhaustedError as exc:
            result = fallback.model_dump()
            result["ai_source"] = "local_fallback"
            result["ai_failure_reason"] = "Gemini free-tier quota exhausted for today."
            result["short_summary"] = (
                "[Gemini free-tier quota exhausted for today. Showing local analysis.] "
                + (fallback.short_summary or "")
            )
            return AnalysisResponse(**result)

        except Exception as exc:
            result = fallback.model_dump()
            result["ai_source"] = "local_fallback"
            result["ai_failure_reason"] = f"Gemini analysis failed: {exc}"
            result["short_summary"] = (
                f"[Gemini analysis failed: {exc}. Showing local analysis.] "
                + (fallback.short_summary or "")
            )[:900]
            return AnalysisResponse(**result)

    async def generate_email(self, analysis: dict[str, Any], template: str) -> EmailResponse:
        fallback = self.local_email(analysis, template)
        if not settings.gemini_api_key:
            return fallback

        try:
            prompt = self._email_prompt(analysis, template)
            text = await asyncio.wait_for(
                asyncio.to_thread(
                    self._generate_with_available_model_sync,
                    prompt,
                    400,
                    True,
                ),
                timeout=settings.gemini_timeout_seconds,
            )
            parsed = self._parse_json(text)
            if not self._looks_like_email_payload(parsed):
                raise RuntimeError("Gemini returned unusable email JSON.")

            subject = str(parsed.get("subject") or fallback.subject).strip()
            body = str(parsed.get("body") or fallback.body).strip()
            return EmailResponse(subject=subject[:120], body=body, ai_source="gemini")

        except _QuotaExhaustedError:
            fb = fallback.model_dump()
            fb["ai_source"] = "local_fallback"
            return EmailResponse(**fb)

        except Exception:
            return fallback

    # ------------------------------------------------------------------
    # Prompt builders — the most important part
    # ------------------------------------------------------------------

    def _prompt(self, crawl: CrawlResult, dom_snapshot: str | None) -> str:
        """
        Build a focused, token-efficient prompt.
        We deliberately do NOT dump the entire crawl — we extract only
        what Gemini needs so it can think clearly and return accurate JSON.
        """
        primary = crawl.pages[0] if crawl.pages else None
        domain = extract_domain(crawl.final_url)

        # Collect all emails and phones across all pages
        all_emails = list(dict.fromkeys(e for p in crawl.pages for e in p.emails))
        all_phones = list(dict.fromkeys(ph for p in crawl.pages for ph in p.phone_numbers))
        all_socials = list(dict.fromkeys(s for p in crawl.pages for s in p.social_links))
        all_ctas = list(dict.fromkeys(c for p in crawl.pages for c in p.cta_text))

        # Combine headings from all pages (most signal-rich content)
        all_headings = []
        for p in crawl.pages:
            all_headings.extend(p.headings[:12])
        all_headings = list(dict.fromkeys(all_headings))[:40]

        # Best paragraphs from primary + one other page
        paragraphs = []
        for p in crawl.pages[:3]:
            paragraphs.extend(p.paragraphs[:8])
        paragraphs = list(dict.fromkeys(paragraphs))[:20]

        focused = {
            "url": crawl.final_url,
            "domain": domain,
            "pages_crawled": [p.url for p in crawl.pages],
            "title": primary.title if primary else "",
            "meta_description": primary.meta_description if primary else "",
            "all_headings": all_headings,
            "sample_paragraphs": paragraphs,
            "cta_buttons": all_ctas[:15],
            "navigation": [lnk["text"] for lnk in (primary.navigation_links if primary else [])[:20]],
            "footer_text": (primary.footer or "")[:400] if primary else "",
            "emails": all_emails[:8],
            "phones": all_phones[:4],
            "social_links": all_socials[:10],
            "technologies": crawl.technologies,
            "theme_colors": crawl.theme_colors[:6],
            "owner_name": crawl.owner_name,
            "owner_email": crawl.owner_email,
            "logo_url": crawl.logo_url,
            "screenshot_url": crawl.screenshot_url,
        }

        if dom_snapshot:
            focused["dom_snapshot"] = dom_snapshot[:6000]

        schema_description = """
Return ONLY valid JSON with these exact keys. Each key that is an object should have
clearly named sub-keys with specific findings — no vague one-liners.

{
  "website_name": "string — business name inferred from site",
  "short_summary": "string — 1 sentence, what the business does and who it serves",
  "detailed_summary": "string — 3–5 sentence paragraph covering the business model, audience, value prop, and site quality",
  "category_analysis": {
    "primary_category": "e.g. SaaS / Agency / Ecommerce / Healthcare ...",
    "sub_category": "more specific niche",
    "confidence": "high | medium | low",
    "signals": ["list of words/phrases that led to this conclusion"]
  },
  "business_analysis": {
    "business_model": "how they make money",
    "products_or_services": ["list of main offerings"],
    "target_audience": "who they sell to",
    "geographic_focus": "local / national / global",
    "pricing_visible": true or false,
    "lead_gen_present": true or false
  },
  "branding_analysis": {
    "primary_color": "#hexcode",
    "secondary_colors": ["#hexcodes"],
    "brand_personality": "e.g. Professional, Playful, Minimalist ...",
    "brand_consistency": "strong | moderate | weak — with reason",
    "logo_quality": "professional | basic | missing"
  },
  "logo_analysis": {
    "logo_url": "url or empty",
    "favicon_url": "url or empty",
    "og_image_url": "url or empty",
    "assessment": "brief quality note"
  },
  "ui_ux_analysis": {
    "overall_quality": "excellent | good | moderate | poor",
    "mobile_readiness": "likely responsive or not based on framework",
    "cta_count": number,
    "cta_clarity": "clear | vague | missing",
    "navigation_quality": "clean | cluttered | missing",
    "trust_signals_visible": ["e.g. testimonials, certifications, logos"],
    "key_issues": ["top 3 UX problems visible"]
  },
  "seo_analysis": {
    "quality_score": 0-100,
    "has_title": true/false,
    "has_meta_description": true/false,
    "title_quality": "descriptive | generic | missing",
    "heading_count": number,
    "heading_quality": "well structured | flat | missing",
    "keyword_signals": ["words used that signal intent"],
    "quick_wins": ["top 3 SEO improvements"]
  },
  "trust_analysis": {
    "trust_score": 0-100,
    "emails_found": ["list"],
    "phones_found": ["list"],
    "social_links": ["list"],
    "has_testimonials": true/false,
    "has_case_studies": true/false,
    "has_certifications": true/false,
    "trust_gaps": ["what is missing that reduces trust"]
  },
  "technical_analysis": {
    "technologies": ["list"],
    "pages_crawled": number,
    "uses_dynamic_rendering": true/false,
    "performance_notes": "any observations from HTML structure",
    "security_notes": "e.g. forms present, no obvious issues"
  },
  "content_analysis": {
    "content_depth": "thin | moderate | rich",
    "tone_of_voice": "e.g. formal, conversational, technical",
    "value_proposition_clarity": "strong | moderate | weak",
    "key_messages": ["top 3 messages communicated"],
    "content_gaps": ["what is missing that visitors likely want"]
  },
  "competitor_estimation": {
    "likely_competitor_types": ["types of businesses that compete"],
    "positioning": "how this site compares at a glance",
    "differentiation_opportunities": ["where they could stand out"]
  },
  "improvement_suggestions": {
    "priority": [
      {"area": "e.g. Homepage", "suggestion": "specific actionable fix"},
      {"area": "SEO", "suggestion": "specific actionable fix"},
      {"area": "Trust", "suggestion": "specific actionable fix"}
    ],
    "quick_wins": [
      {"area": "...", "suggestion": "..."}
    ]
  }
}"""

        return (
            "You are a senior website analyst with expertise in conversion rate optimisation, "
            "SEO, UX, branding, and sales intelligence.\n\n"
            "Analyse the website data below and return ONLY valid JSON — no preamble, no markdown fences.\n\n"
            "Rules:\n"
            "- Be specific. Reference actual content you see (headings, CTAs, tech, colors).\n"
            "- Do NOT invent facts. If you cannot determine something, say 'unclear from available data'.\n"
            "- Every improvement suggestion must be actionable and page-specific.\n"
            "- Keep all string values under 300 characters unless it's a list.\n\n"
            f"JSON schema to follow:\n{schema_description}\n\n"
            f"Website data:\n{json.dumps(focused, ensure_ascii=True)}"
        )

    def _email_prompt(self, analysis: dict[str, Any], template: str) -> str:
        """
        Build a prompt that produces a short, specific, human cold email.
        """
        owner_name = analysis.get("owner_name") or ""
        first_name = analysis.get("owner_first_name") or ""
        website_name = analysis.get("website_name") or analysis.get("website_url") or ""
        domain = extract_domain(str(analysis.get("website_url") or ""))

        # Pull the single most impactful issue to reference in the email
        suggestions = analysis.get("improvement_suggestions", {})
        top_issue = ""
        if isinstance(suggestions, dict):
            priority = suggestions.get("priority") or []
            if isinstance(priority, list) and priority:
                first = priority[0]
                if isinstance(first, dict):
                    top_issue = f"{first.get('area', '')}: {first.get('suggestion', '')}"
                else:
                    top_issue = str(first)

        # Identify something positive from the site to open with
        category = ""
        cat = analysis.get("category_analysis", {})
        if isinstance(cat, dict):
            category = str(cat.get("primary_category") or cat.get("sub_category") or "")

        payload = {
            "website_name": website_name,
            "website_url": analysis.get("website_url"),
            "domain": domain,
            "owner_name": owner_name,
            "owner_first_name": first_name,
            "category": category,
            "top_improvement_issue": top_issue,
            "business_summary": analysis.get("short_summary"),
            "trust_score": (analysis.get("trust_analysis") or {}).get("trust_score"),
            "seo_score": (analysis.get("seo_analysis") or {}).get("quality_score"),
            "ux_quality": (analysis.get("ui_ux_analysis") or {}).get("overall_quality"),
            "key_issues": (analysis.get("ui_ux_analysis") or {}).get("key_issues", []),
            "content_gaps": (analysis.get("content_analysis") or {}).get("content_gaps", []),
            "trust_gaps": (analysis.get("trust_analysis") or {}).get("trust_gaps", []),
        }

        greeting = f"Hi {first_name}" if first_name else ("Hi there" if not owner_name else f"Hi {owner_name.split()[0]}")

        return (
            "You write short, specific, human cold emails for a website development and practical AI services business.\n\n"
            "RULES — follow all of these strictly:\n"
            f"1. Open with: '{greeting},' — never use 'Dear' or generic salutations.\n"
            "2. Reference ONE specific thing you noticed on their actual website (from the data below).\n"
            "3. Follow the selected template structure, but replace placeholders only with known facts from the analysis data.\n"
            "4. If a template placeholder cannot be verified, rewrite that sentence naturally instead of inventing names, events, results, or mutual contacts.\n"
            "5. Keep the email under 130 words total.\n"
            "6. End with a single easy yes/no question.\n"
            "7. Never claim specific ROI numbers, revenue figures, or results you cannot prove.\n"
            "8. Never use: 'leverage', 'synergy', 'game-changer', 'revolutionize', 'skyrocket', 'transform'.\n"
            "9. Sound like a helpful human expert, not a marketing bot.\n"
            "10. The subject line must be 6 words or fewer and feel personal, not promotional.\n\n"
            "Return ONLY valid JSON with keys: subject (string) and body (string with \\n for line breaks).\n\n"
            "User's preferred email style/template to follow:\n"
            + template[:3000]
            + "\n\nWebsite analysis data:\n"
            + json.dumps(payload, ensure_ascii=True)
        )

    # ------------------------------------------------------------------
    # Local fallback (no API key / API failure)
    # ------------------------------------------------------------------

    def local_analysis(self, crawl: CrawlResult) -> AnalysisResponse:
        primary = crawl.pages[0] if crawl.pages else None
        title = primary.title if primary else extract_company_name(crawl.final_url)
        full_text = " ".join(p.visible_text for p in crawl.pages)[:15000]
        category = self._infer_category(full_text)
        summary = self._summary(primary)

        seo_score = self._score(
            bool(primary and primary.title),
            bool(primary and primary.meta_description),
            len(primary.headings) if primary else 0,
        )
        all_emails = self._emails(crawl)
        all_phones = self._phones(crawl)
        all_socials = self._socials(crawl)
        trust_score = min(95, 30 + len(all_emails) * 10 + len(all_phones) * 10 + len(all_socials) * 5)

        owner_name = getattr(crawl, "owner_name", None)
        owner_email = getattr(crawl, "owner_email", None)
        first_name, last_name = self._split_name(owner_name)

        all_headings = list(dict.fromkeys(h for p in crawl.pages for h in p.headings[:12]))[:35]
        all_ctas = list(dict.fromkeys(c for p in crawl.pages for c in p.cta_text[:10]))[:20]
        tech = crawl.technologies

        return AnalysisResponse(
            website_name=title or crawl.final_url,
            website_url=crawl.final_url,
            short_summary=summary,
            detailed_summary=(
                f"{summary} The site appears to operate in the {category.lower()} space. "
                f"It uses {', '.join(tech[:3]) if tech else 'undetected technologies'}, "
                f"crawled {len(crawl.pages)} page(s), and has "
                f"{'some' if all_emails else 'no'} visible contact methods."
            ),
            category_analysis={
                "primary_category": category,
                "confidence": "medium",
                "signals": self._keywords(full_text),
            },
            business_analysis={
                "business_model": "To be confirmed — appears service or product focused.",
                "products_or_services": self._offerings(crawl),
                "target_audience": "Prospective customers reviewing options, pricing, and credibility.",
                "geographic_focus": "unclear",
                "pricing_visible": any("pricing" in p.url.lower() for p in crawl.pages),
                "lead_gen_present": bool(all_emails or any(p.cta_text for p in crawl.pages)),
            },
            branding_analysis={
                "primary_color": crawl.theme_colors[0] if crawl.theme_colors else "",
                "secondary_colors": crawl.theme_colors[1:5],
                "brand_personality": self._personality(crawl.theme_colors),
                "brand_consistency": "moderate — requires visual review",
                "logo_quality": "present" if crawl.logo_url else "missing",
            },
            logo_analysis={
                "logo_url": crawl.logo_url,
                "favicon_url": crawl.favicon_url,
                "og_image_url": crawl.og_image_url,
                "assessment": "Logo detected." if crawl.logo_url else "No logo found in crawled HTML.",
            },
            ui_ux_analysis={
                "overall_quality": "moderate",
                "mobile_readiness": "likely responsive" if any(t in tech for t in ("React", "Next.js", "Vue", "Tailwind", "Bootstrap")) else "unknown",
                "cta_count": sum(len(p.cta_text) for p in crawl.pages),
                "cta_clarity": "present" if all_ctas else "missing",
                "navigation_quality": "present" if primary and primary.navigation_links else "unknown",
                "trust_signals_visible": [],
                "key_issues": [
                    "Above-the-fold value proposition may be unclear",
                    "CTA prominence and consistency not verified",
                    "Social proof / testimonials not detected",
                ],
            },
            seo_analysis={
                "quality_score": seo_score,
                "has_title": bool(primary and primary.title),
                "has_meta_description": bool(primary and primary.meta_description),
                "title_quality": "present" if primary and primary.title else "missing",
                "heading_count": len(primary.headings) if primary else 0,
                "heading_quality": "present" if all_headings else "missing",
                "keyword_signals": self._keywords(full_text)[:8],
                "quick_wins": [
                    "Add or improve meta description",
                    "Ensure H1 clearly states value proposition",
                    "Add structured data / schema markup",
                ],
            },
            trust_analysis={
                "trust_score": trust_score,
                "emails_found": all_emails,
                "phones_found": all_phones,
                "social_links": all_socials,
                "has_testimonials": False,
                "has_case_studies": False,
                "has_certifications": False,
                "trust_gaps": [
                    "No verified testimonials found",
                    "No visible certifications or awards",
                    "Limited social proof",
                ],
            },
            technical_analysis={
                "technologies": tech,
                "pages_crawled": len(crawl.pages),
                "uses_dynamic_rendering": any(t in tech for t in ("React", "Next.js", "Vue", "Angular")),
                "performance_notes": "Not assessed — requires Lighthouse or PageSpeed data.",
                "security_notes": "HTTPS assumed if URL is https://",
            },
            content_analysis={
                "headings": all_headings[:15],
                "cta_text": all_ctas[:10],
                "content_depth": "rich" if len(full_text) > 6000 else ("moderate" if len(full_text) > 2000 else "thin"),
                "tone_of_voice": "unknown — requires Gemini analysis",
                "value_proposition_clarity": "unclear — requires Gemini analysis",
                "key_messages": all_headings[:3],
                "content_gaps": ["FAQ section", "About/Team page", "Case studies or portfolio"],
            },
            competitor_estimation={
                "likely_competitor_types": ["Direct category competitors", "Local providers", "SaaS alternatives"],
                "positioning": "Requires full AI analysis for accurate assessment.",
                "differentiation_opportunities": ["Requires Gemini analysis"],
            },
            improvement_suggestions={
                "priority": [
                    {"area": "Homepage", "suggestion": "Clarify above-the-fold value proposition"},
                    {"area": "SEO", "suggestion": "Add or improve meta description and structured headings"},
                    {"area": "Trust", "suggestion": "Add testimonials, case studies, or client logos"},
                    {"area": "CTA", "suggestion": "Make primary CTA consistent and prominent on all pages"},
                ],
                "quick_wins": [
                    {"area": "Contact", "suggestion": "Ensure email and phone are visible in header or hero"},
                    {"area": "Images", "suggestion": "Compress images to improve page load time"},
                    {"area": "Social proof", "suggestion": "Add at least 3 client testimonials above the fold"},
                ],
            },
            theme_colors=crawl.theme_colors,
            logo_url=crawl.logo_url,
            favicon_url=crawl.favicon_url,
            screenshot_url=crawl.screenshot_url,
            owner_name=owner_name,
            owner_email=owner_email,
            owner_first_name=first_name,
            owner_last_name=last_name,
        )

    def local_email(self, analysis: dict[str, Any], template: str) -> EmailResponse:
        website_url = str(analysis.get("website_url") or "")
        domain = extract_domain(website_url) or str(analysis.get("website_name") or "your site")
        first_name = analysis.get("owner_first_name") or ""
        owner_name = analysis.get("owner_name") or ""
        recipient = first_name or (owner_name.split()[0] if owner_name else "there")
        greeting = f"Hi {recipient}"

        category = self._email_value(analysis.get("category_analysis", {}), "primary_category", "business")

        suggestions = analysis.get("improvement_suggestions", {})
        top_issue = "a clearer value proposition"
        if isinstance(suggestions, dict):
            priority = suggestions.get("priority") or []
            if isinstance(priority, list) and priority:
                first = priority[0]
                top_issue = (
                    f"{first.get('area', '')}: {first.get('suggestion', '')}"
                    if isinstance(first, dict)
                    else str(first)
                )

        website_name = str(analysis.get("website_name") or domain)
        context = {
            "name": recipient,
            "first_name": recipient,
            "company": website_name,
            "company name": website_name,
            "prospect company": website_name,
            "website": domain,
            "industry": category,
            "top_issue": top_issue,
            "process": "lead generation",
            "priority": "website conversions",
            "goal": "more qualified leads",
            "content_topic": "website growth",
            "content_name": "website audit",
            "signature": "Best,",
            "your_name": "",
            "your_company": "",
            "service": "website development and AI services",
        }

        subject = self._extract_template_field(template, "subject") or f"quick note about {domain}"
        body = self._extract_template_field(template, "body")

        if body:
            subject = self._replace_template_placeholders(subject, context).strip() or f"quick note about {domain}"
            body = self._replace_template_placeholders(body, context).strip()
            if body and not body.lower().startswith(("hi ", "hello ")):
                body = f"{greeting},\n\n{body}"
            return EmailResponse(subject=subject[:120], body=body, ai_source="local_fallback")

        subject = f"quick note about {domain}"
        body = (
            f"{greeting},\n\n"
            f"I was looking at {domain} and noticed {top_issue.lower()}.\n\n"
            f"For a {category.lower()} website, that often means visitors leave before getting in touch.\n\n"
            "I help businesses improve websites and add practical AI systems so more of their existing traffic turns into leads. Want me to send over a quick teardown?\n\n"
            "Best,"
        )
        return EmailResponse(subject=subject, body=body, ai_source="local_fallback")

    def _extract_template_field(self, template: str, field: str) -> str:
        import re

        if not template:
            return ""
        if field == "subject":
            match = re.search(r"(?im)^\s*Subject:\s*(.+)$", template)
            return match.group(1).strip() if match else ""
        match = re.search(r"(?is)^\s*Body:\s*(.+)$", template)
        return match.group(1).strip() if match else ""

    def _replace_template_placeholders(self, text: str, context: dict[str, str]) -> str:
        import re

        def replace(match) -> str:
            key = match.group(1).strip().lower().replace("-", "_")
            return context.get(key) or context.get(key.replace("_", " ")) or ""

        rendered = re.sub(r"\{\{\s*([^}]+?)\s*\}\}", replace, text)
        rendered = re.sub(r"\{\s*([^}]+?)\s*\}", replace, rendered)
        rendered = re.sub(r"\[[^\]]+\]", "", rendered)
        rendered = re.sub(r"[ \t]+\n", "\n", rendered)
        rendered = re.sub(r"\n{3,}", "\n\n", rendered)
        rendered = re.sub(r" +", " ", rendered)
        return rendered.strip()
    # ------------------------------------------------------------------
    # Gemini model runner with fallbacks + rate-limit handling
    # ------------------------------------------------------------------

    def _generate_with_available_model_sync(self, prompt: str, max_output_tokens: int = 2048, json_mode: bool = True) -> str:
        import time

        model_names = list(dict.fromkeys([settings.gemini_model, *GEMINI_MODEL_FALLBACKS]))
        errors: list[str] = []
        all_quota_errors = 0

        for model_name in model_names:
            try:
                return self._call_generate_content(model_name, prompt, max_output_tokens, json_mode)
            except Exception as exc:
                exc_str = str(exc)
                errors.append(f"{model_name}: {exc_str}")

                if self._is_quota_error(exc_str):
                    all_quota_errors += 1
                    wait = self._parse_retry_delay(exc_str)
                    if wait and wait <= _MAX_RETRY_WAIT:
                        time.sleep(wait + 1)
                    continue
                continue

        if all_quota_errors == len(model_names):
            raise _QuotaExhaustedError(
                f"Gemini free-tier daily quota exhausted across all models. "
                f"Resets at midnight Pacific Time. Errors: {'; '.join(errors)}"
            )

        raise RuntimeError(
            "No Gemini model could generate content. Errors: " + "; ".join(errors)
        )

    @staticmethod
    def _is_quota_error(error_str: str) -> bool:
        """Detect Gemini 429 / quota-exceeded errors."""
        markers = (
            "429",
            "quota",
            "RESOURCE_EXHAUSTED",
            "exceeded your current quota",
            "free_tier_requests",
            "GenerateRequestsPerDay",
            "rate limit",
            "rateLimitExceeded",
        )
        low = error_str.lower()
        return any(m.lower() in low for m in markers)

    @staticmethod
    def _parse_retry_delay(error_str: str) -> int | None:
        """
        Extract the retry delay in seconds from a Gemini 429 error string.
        The API includes: retry_delay { seconds: 41 }
        """
        import re
        match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", error_str)
        if match:
            return int(match.group(1))
        # Also handle plain "retry after N seconds"
        match = re.search(r"retry after (\d+)", error_str, re.I)
        if match:
            return int(match.group(1))
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_generate_content(self, model_name: str, prompt: str, max_output_tokens: int, json_mode: bool) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "x-goog-api-key": settings.gemini_api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.9,
                "maxOutputTokens": max_output_tokens,
            },
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=settings.gemini_timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(self._gemini_error_message(model_name, response))

        data = response.json()
        text = self._extract_response_text(data)
        if not text.strip():
            raise RuntimeError(f"{model_name}: Gemini returned an empty response")
        return text

    def _extract_response_text(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if text:
                    return str(text)
        return ""

    def _gemini_error_message(self, model_name: str, response: requests.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            payload = {"error": {"message": response.text}}
        message = payload.get("error", {}).get("message") or response.text or f"HTTP {response.status_code}"
        return f"{model_name}: {message}"

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = (
            text.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            import re
            fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if not match:
                    return {}
                candidate = re.sub(r",\s*([}\]])", r"\1", match.group(0))
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return {}

    def _looks_like_analysis_payload(self, parsed: dict[str, Any]) -> bool:
        if not isinstance(parsed, dict):
            return False
        if not str(parsed.get("website_name") or "").strip():
            return False
        if not str(parsed.get("short_summary") or "").strip():
            return False
        object_fields = [key for key in DICT_FIELDS if isinstance(parsed.get(key), dict) and parsed.get(key)]
        return len(object_fields) >= 4

    def _looks_like_email_payload(self, parsed: dict[str, Any]) -> bool:
        if not isinstance(parsed, dict):
            return False
        subject = str(parsed.get("subject") or "").strip()
        body = str(parsed.get("body") or "").strip()
        if len(subject) < 3 or len(body) < 40:
            return False
        return not self._contains_template_placeholders(subject + "\n" + body)

    def _contains_template_placeholders(self, text: str) -> bool:
        import re
        lowered = text.lower()
        if re.search(r"\[[^\]]+\]", text):
            return True
        placeholder_markers = (
            "their domain",
            "type of business",
            "specific thing",
            "consequence",
            "lost revenue",
            "free thing",
        )
        return any(marker in lowered for marker in placeholder_markers)

    def _summary(self, page) -> str:
        if not page:
            return "The website could not be fully summarised from the crawled content."
        if page.meta_description:
            return page.meta_description
        if page.headings:
            return " — ".join(page.headings[:2])
        return page.visible_text[:240] or "The website presents business information."

    def _infer_category(self, text: str) -> str:
        lower = text.lower()
        categories = {
            "Software / SaaS": ("software", "platform", "api", "workflow", "automation", "dashboard", "subscription"),
            "Ecommerce": ("cart", "shop", "product", "shipping", "checkout", "buy now", "add to cart"),
            "Agency / Services": ("agency", "consulting", "services", "strategy", "solutions", "we help"),
            "Education": ("course", "learn", "student", "training", "school", "enroll", "lesson"),
            "Healthcare": ("patient", "clinic", "health", "medical", "care", "doctor", "therapy"),
            "Finance": ("bank", "payment", "investment", "loan", "insurance", "financial", "wealth"),
            "Real Estate": ("property", "real estate", "listing", "mortgage", "rent", "buy home"),
            "Hospitality": ("hotel", "restaurant", "booking", "reservation", "menu", "dining"),
            "Non-profit": ("donate", "charity", "non-profit", "mission", "volunteer", "cause"),
        }
        scores = {
            name: sum(token in lower for token in tokens)
            for name, tokens in categories.items()
        }
        best_score = max(scores.values())
        return max(scores, key=scores.get) if best_score > 0 else "General Business"

    def _offerings(self, crawl: CrawlResult) -> list[str]:
        phrases: list[str] = []
        for page in crawl.pages:
            phrases.extend(page.headings[:10])
            phrases.extend(page.buttons[:6])
        return list(dict.fromkeys(p for p in phrases if len(p) > 3))[:15]

    def _keywords(self, text: str) -> list[str]:
        stop = {"the", "and", "for", "that", "this", "with", "your", "from", "have", "more", "will", "our"}
        words = [
            w.lower() for w in text.split()
            if len(w) > 5 and w.isalpha() and w.lower() not in stop
        ]
        counts: dict[str, int] = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1
        return [w for w, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:12]]

    def _personality(self, colors: list[str]) -> str:
        if not colors:
            return "Content-led and functional"
        return "Polished, digital, and conversion-oriented"

    def _score(self, has_title: bool, has_meta: bool, headings: int) -> int:
        return min(100, 30 + (25 if has_title else 0) + (25 if has_meta else 0) + min(20, headings * 2))

    def _split_name(self, owner_name: str | None) -> tuple[str | None, str | None]:
        if not owner_name:
            return None, None
        parts = [p for p in owner_name.split() if p]
        first = parts[0] if parts else None
        last = parts[-1] if len(parts) > 1 else None
        return first, last

    def _email_value(self, data: Any, key: str, default: str) -> str:
        if isinstance(data, dict):
            value = data.get(key)
            if value:
                return str(value)
        return default

    def _emails(self, crawl: CrawlResult) -> list[str]:
        return sorted({e for p in crawl.pages for e in p.emails})

    def _phones(self, crawl: CrawlResult) -> list[str]:
        return sorted({ph for p in crawl.pages for ph in p.phone_numbers})

    def _socials(self, crawl: CrawlResult) -> list[str]:
        return sorted({s for p in crawl.pages for s in p.social_links})

