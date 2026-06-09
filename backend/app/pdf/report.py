from io import BytesIO
from typing import Any

import requests
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils.storage import public_url, storage_path


class ReportBuilder:
    def build(self, analysis: dict[str, Any]) -> str:
        path = storage_path("reports", ".pdf")
        doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
        styles = getSampleStyleSheet()
        # Paragraph style used inside table cells to allow wrapping and splitting
        styles.add(ParagraphStyle(name="TableBody", parent=styles["BodyText"], fontSize=10, leading=12, spaceBefore=0, spaceAfter=0))
        styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontSize=28, leading=34, alignment=TA_CENTER, textColor=colors.HexColor("#111827")))
        styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=15, leading=20, textColor=colors.HexColor("#0f172a"), spaceBefore=12))
        # prepare cover rendering data
        self.cover_analysis = analysis

        # start story with a PageBreak so the cover page is drawn by onFirstPage
        story = [PageBreak()]

        story.append(Paragraph("Executive Summary", styles["Section"]))
        story.append(Paragraph(str(analysis.get("detailed_summary") or analysis.get("short_summary") or ""), styles["BodyText"]))
        story.append(Spacer(1, 0.15 * inch))
        story.extend(self._palette(analysis.get("theme_colors", [])))

        sections = [
            ("Category Analysis", analysis.get("category_analysis", {})),
            ("Business Analysis", analysis.get("business_analysis", {})),
            ("Branding Analysis", analysis.get("branding_analysis", {})),
            ("SEO Analysis", analysis.get("seo_analysis", {})),
            ("UX Analysis", analysis.get("ui_ux_analysis", {})),
            ("Trust Analysis", analysis.get("trust_analysis", {})),
            ("Technical Analysis", analysis.get("technical_analysis", {})),
            ("Recommendations", analysis.get("improvement_suggestions", {})),
            ("Generated Cold Email", analysis.get("cold_email", {})),
        ]
        for title, value in sections:
            story.append(Paragraph(title, styles["Section"]))
            story.append(self._dict_table(value, styles))

        # store ai usage flag for page styling
        self.ai_used = bool(analysis.get("ai_source") and analysis.get("ai_source") != "local_fallback")
        doc.build(story, onFirstPage=self._cover_page, onLaterPages=self._page_style)
        return public_url(path)

    def _cover_page(self, canvas, doc) -> None:
        analysis = getattr(self, "cover_analysis", {}) or {}
        # determine primary color
        primary = None
        try:
            primary = analysis.get("branding_analysis", {}).get("primary_color")
        except Exception:
            primary = None
        if not primary:
            palette = analysis.get("theme_colors") or []
            primary = palette[0] if palette else "#111827"
        try:
            bg_color = colors.HexColor(primary)
        except Exception:
            bg_color = colors.HexColor("#111827")

        # fill background with a light tint of primary color
        canvas.setFillColor(bg_color)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)

        # draw logo centered near top
        logo_url = analysis.get("logo_url") or analysis.get("favicon_url")
        if logo_url:
            try:
                from reportlab.lib.utils import ImageReader
                import requests
                from io import BytesIO

                resp = requests.get(logo_url, timeout=6)
                resp.raise_for_status()
                img_buf = BytesIO(resp.content)
                reader = ImageReader(img_buf)
                img_w = 1.2 * inch
                img_h = 1.2 * inch
                canvas.drawImage(reader, (A4[0] - img_w) / 2, A4[1] - 1.6 * inch, img_w, img_h, mask='auto')
            except Exception:
                pass

        # title centered
        title = f"{analysis.get('website_name', 'Website')} Audit Report"
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 28)
        canvas.drawCentredString(A4[0] / 2, A4[1] / 2 + 40, title)

        # subtitle / url
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.whitesmoke)
        canvas.drawCentredString(A4[0] / 2, A4[1] / 2 + 20, analysis.get("website_url", ""))

        # bottom social links and small footer
        social_links = analysis.get("trust_analysis", {}).get("social_links") or []
        x = 42
        y = 36
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.whitesmoke)
        for link in social_links:
            canvas.drawString(x, y, str(link))
            x += 180

        # small color stripe at bottom using primary (darker)
        try:
            stripe = colors.HexColor(primary)
        except Exception:
            stripe = colors.HexColor("#0f172a")
        canvas.setFillColor(stripe)
        canvas.rect(0, 0, A4[0], 22, fill=1, stroke=0)

    def _dict_table(self, data: Any, styles) -> Table:
        def _wrap(text: Any, styles) -> Paragraph:
            return Paragraph(self._stringify(text), styles["TableBody"])

        if not isinstance(data, dict):
            data = {"details": data}
        # Special-case improvement suggestions when provided as a list of {area, suggestion}
        if "details" in data and isinstance(data["details"], list) and data["details"] and isinstance(data["details"][0], dict):
            # build a table with Area | Suggestion
            rows = [["Area", "Suggestion"]]
            for item in data["details"]:
                area = item.get("area") or item.get("metric") or ""
                suggestion = item.get("suggestion") or item.get("finding") or item.get("details") or ""
                rows.append([Paragraph(str(area), getSampleStyleSheet()["BodyText"]), Paragraph(str(suggestion), styles["TableBody"])])
            table = Table(rows, colWidths=[1.6 * inch, 4.8 * inch], repeatRows=1)
        else:
            rows = [["Metric", "Finding"]]
            for key, value in data.items():
                rows.append([Paragraph(self._label(key), getSampleStyleSheet()["BodyText"]), _wrap(value, styles)])
            table = Table(rows, colWidths=[1.8 * inch, 4.6 * inch], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        table.splitByRow = 1
        table.splitInRow = 1
        return table

    def _palette(self, palette: list[str]) -> list[Any]:
        if not palette:
            return []
        rows = [["Color", "Hex"]] + [["", color] for color in palette[:8]]
        table = Table(rows, colWidths=[0.9 * inch, 1.3 * inch])
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ]
        for index, color in enumerate(palette[:8], start=1):
            try:
                style.append(("BACKGROUND", (0, index), (0, index), colors.HexColor(color)))
            except Exception:
                pass
        table.setStyle(TableStyle(style))
        return [Paragraph("Color Palette", getSampleStyleSheet()["Heading3"]), table, Spacer(1, 0.15 * inch)]

    def _image_block(self, url: str | None, width: float, height: float) -> list[Any]:
        if not url:
            return []
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            img.thumbnail((int(width), int(height)))
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            return [PdfImage(buffer, width=img.width, height=img.height), Spacer(1, 0.2 * inch)]
        except Exception:
            return []

    def _page_style(self, canvas, doc) -> None:
        canvas.setFillColor(colors.HexColor("#eef2ff"))
        canvas.rect(0, A4[1] - 18, A4[0], 18, fill=1, stroke=0)
        # AI usage badge on the top-left of the header band
        ai_used = getattr(self, "ai_used", False)
        badge_x = 60
        badge_y = A4[1] - 9
        if ai_used:
            canvas.setFillColor(colors.HexColor("#16a34a"))
        else:
            canvas.setFillColor(colors.HexColor("#9ca3af"))
        canvas.circle(badge_x, badge_y, 6, stroke=0, fill=1)
        # draw a simple check or cross
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(1.5)
        if ai_used:
            canvas.line(badge_x - 3, badge_y, badge_x - 0.5, badge_y - 3)
            canvas.line(badge_x - 0.5, badge_y - 3, badge_x + 3.5, badge_y + 3)
            label = "AI used"
        else:
            canvas.line(badge_x - 3, badge_y + 3, badge_x + 3, badge_y - 3)
            canvas.line(badge_x - 3, badge_y - 3, badge_x + 3, badge_y + 3)
            label = "AI not used"

        canvas.setFillColor(colors.HexColor("#0f172a"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(badge_x + 12, badge_y - 3, label)

        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 42, 22, f"Page {doc.page}")

    def _label(self, key: str) -> str:
        return key.replace("_", " ").title()

    def _stringify(self, value: Any) -> str:
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value[:12])
            return self._truncate(rendered)
        if isinstance(value, dict):
            rendered = "; ".join(f"{self._label(str(k))}: {self._stringify(v)}" for k, v in value.items())
            return self._truncate(rendered)
        return self._truncate(str(value))

    def _truncate(self, text: str, limit: int = 1200) -> str:
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + " ..."
