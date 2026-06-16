from io import BytesIO
from typing import Any

import requests
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.utils.storage import public_url, storage_path


# ---------------------------------------------------------------------------
# Colour palette used across the report
# ---------------------------------------------------------------------------

NAVY    = colors.HexColor("#0f172a")
SLATE   = colors.HexColor("#334155")
MUTED   = colors.HexColor("#64748b")
LIGHT   = colors.HexColor("#f1f5f9")
WHITE   = colors.white
ACCENT  = colors.HexColor("#3b82f6")   # default brand accent (overridden per site)
GREEN   = colors.HexColor("#16a34a")
GREY    = colors.HexColor("#9ca3af")
BORDER  = colors.HexColor("#e2e8f0")


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

class ReportBuilder:

    def build(self, analysis: dict[str, Any]) -> str:
        path = storage_path("reports", ".pdf")
        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            rightMargin=42,
            leftMargin=42,
            topMargin=48,
            bottomMargin=48,
        )
        styles = self._make_styles()

        # Derive site-wide accent colour from branding data
        try:
            primary_hex = (
                (analysis.get("branding_analysis") or {}).get("primary_color")
                or (analysis.get("theme_colors") or [None])[0]
                or "#3b82f6"
            )
            self._accent = colors.HexColor(primary_hex)
        except Exception:
            self._accent = ACCENT

        self.cover_analysis = analysis
        self.ai_used = bool(
            analysis.get("ai_source") and analysis.get("ai_source") != "local_fallback"
        )

        story: list[Any] = [PageBreak()]   # cover is drawn by onFirstPage

        # ---------- Executive Summary ----------
        story.append(Paragraph("Executive Summary", styles["Section"]))
        summary_text = str(
            analysis.get("detailed_summary")
            or analysis.get("short_summary")
            or "No summary available."
        )
        story.append(Paragraph(summary_text, styles["Body"]))
        story.append(Spacer(1, 0.12 * inch))

        # ---------- Owner / Contact Intelligence ----------
        owner_name  = analysis.get("owner_name") or ""
        owner_email = analysis.get("owner_email") or ""
        owner_first = analysis.get("owner_first_name") or ""
        owner_last  = analysis.get("owner_last_name") or ""
        if owner_name or owner_email:
            story.append(Paragraph("Owner / Contact Intelligence", styles["Section"]))
            owner_data = {}
            if owner_name:
                owner_data["Owner Name"] = owner_name
            if owner_first:
                owner_data["First Name"] = owner_first
            if owner_last:
                owner_data["Last Name"] = owner_last
            if owner_email:
                owner_data["Owner Email"] = owner_email
            story.append(self._kv_table(owner_data, styles))
            story.append(Spacer(1, 0.12 * inch))

        # ---------- Colour Palette ----------
        palette = analysis.get("theme_colors") or []
        story.extend(self._palette_section(palette, styles))

        # ---------- Main Analysis Sections ----------
        sections = [
            ("Category Analysis",     analysis.get("category_analysis", {})),
            ("Business Analysis",     analysis.get("business_analysis", {})),
            ("Branding Analysis",     analysis.get("branding_analysis", {})),
            ("SEO Analysis",          analysis.get("seo_analysis", {})),
            ("UX Analysis",           analysis.get("ui_ux_analysis", {})),
            ("Trust Analysis",        analysis.get("trust_analysis", {})),
            ("Technical Analysis",    analysis.get("technical_analysis", {})),
            ("Content Analysis",      analysis.get("content_analysis", {})),
            ("Competitor Estimation", analysis.get("competitor_estimation", {})),
            ("Improvement Suggestions", analysis.get("improvement_suggestions", {})),
        ]

        for title, value in sections:
            story.append(Paragraph(title, styles["Section"]))
            story.append(self._dict_table(value, styles))
            story.append(Spacer(1, 0.1 * inch))

        # ---------- Generated Cold Email ----------
        cold_email = analysis.get("cold_email")
        if cold_email:
            story.append(Paragraph("Generated Cold Email", styles["Section"]))
            story.append(self._dict_table(cold_email, styles))

        doc.build(
            story,
            onFirstPage=self._cover_page,
            onLaterPages=self._page_style,
        )
        return public_url(path)

    # ------------------------------------------------------------------
    # Cover page
    # ------------------------------------------------------------------

    def _cover_page(self, canvas, doc) -> None:
        analysis = getattr(self, "cover_analysis", {}) or {}

        # Background: dark navy
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)

        # Accent bar at top
        try:
            canvas.setFillColor(self._accent)
        except Exception:
            canvas.setFillColor(ACCENT)
        canvas.rect(0, A4[1] - 6, A4[0], 6, fill=1, stroke=0)

        # Logo
        logo_url = analysis.get("logo_url") or analysis.get("favicon_url")
        logo_y = A4[1] - 1.8 * inch
        if logo_url:
            try:
                from reportlab.lib.utils import ImageReader
                resp = requests.get(logo_url, timeout=6)
                resp.raise_for_status()
                reader = ImageReader(BytesIO(resp.content))
                iw, ih = 1.1 * inch, 1.1 * inch
                canvas.drawImage(
                    reader,
                    (A4[0] - iw) / 2,
                    logo_y,
                    iw, ih,
                    mask="auto",
                )
            except Exception:
                logo_y = A4[1] - 1.2 * inch   # shift down if logo failed

        # Website name
        website_name = analysis.get("website_name") or "Website"
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 26)
        canvas.drawCentredString(A4[0] / 2, A4[1] / 2 + 55, website_name)

        # "Audit Report" subtitle
        canvas.setFont("Helvetica", 13)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawCentredString(A4[0] / 2, A4[1] / 2 + 32, "Website Audit Report")

        # URL
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawCentredString(A4[0] / 2, A4[1] / 2 + 14, str(analysis.get("website_url") or ""))

        # Divider line
        canvas.setStrokeColor(colors.HexColor("#1e293b"))
        canvas.setLineWidth(1)
        canvas.line(42, A4[1] / 2 + 5, A4[0] - 42, A4[1] / 2 + 5)

        # Short summary
        short_summary = str(analysis.get("short_summary") or "")[:180]
        if short_summary:
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(colors.HexColor("#94a3b8"))
            self._draw_wrapped_text(canvas, short_summary, 60, A4[1] / 2 - 12, A4[0] - 120, 12)

        # Owner badge
        owner_name  = analysis.get("owner_name") or ""
        owner_email = analysis.get("owner_email") or ""
        if owner_name or owner_email:
            badge_y = 110
            canvas.setFillColor(colors.HexColor("#1e293b"))
            canvas.roundRect(42, badge_y - 14, A4[0] - 84, 42, 4, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#94a3b8"))
            canvas.setFont("Helvetica", 8)
            canvas.drawString(52, badge_y + 18, "OWNER / DECISION-MAKER")
            canvas.setFillColor(WHITE)
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(52, badge_y + 4, owner_name or owner_email)
            if owner_name and owner_email:
                canvas.setFont("Helvetica", 9)
                canvas.setFillColor(colors.HexColor("#94a3b8"))
                canvas.drawString(52, badge_y - 8, owner_email)

        # Social links
        social_links = []
        trust = analysis.get("trust_analysis") or {}
        if isinstance(trust, dict):
            social_links = trust.get("social_links") or []
        x = 42
        y = 52
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        for link in social_links[:4]:
            canvas.drawString(x, y, str(link)[:45])
            x += 135

        # Bottom accent bar
        try:
            canvas.setFillColor(self._accent)
        except Exception:
            canvas.setFillColor(ACCENT)
        canvas.rect(0, 0, A4[0], 22, fill=1, stroke=0)

    # ------------------------------------------------------------------
    # Page header / footer for all non-cover pages
    # ------------------------------------------------------------------

    def _page_style(self, canvas, doc) -> None:
        # Header bar
        canvas.setFillColor(LIGHT)
        canvas.rect(0, A4[1] - 22, A4[0], 22, fill=1, stroke=0)

        # AI badge
        ai_used = getattr(self, "ai_used", False)
        bx, by = 56, A4[1] - 11
        canvas.setFillColor(GREEN if ai_used else GREY)
        canvas.circle(bx, by, 5, stroke=0, fill=1)
        canvas.setStrokeColor(WHITE)
        canvas.setLineWidth(1.2)
        if ai_used:
            canvas.line(bx - 2.5, by, bx - 0.5, by - 2.5)
            canvas.line(bx - 0.5, by - 2.5, bx + 3, by + 2.5)
            label = "AI-powered analysis"
        else:
            canvas.line(bx - 2.5, by + 2.5, bx + 2.5, by - 2.5)
            canvas.line(bx - 2.5, by - 2.5, bx + 2.5, by + 2.5)
            label = "Local analysis"

        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(bx + 9, by - 2.5, label)

        # Site name in header
        analysis = getattr(self, "cover_analysis", {}) or {}
        site_name = str(analysis.get("website_name") or "")
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(NAVY)
        canvas.drawCentredString(A4[0] / 2, A4[1] - 13, site_name)

        # Page number
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - 42, 18, f"Page {doc.page}")

        # Footer line
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(42, 28, A4[0] - 42, 28)

    # ------------------------------------------------------------------
    # Table builders
    # ------------------------------------------------------------------

    def _dict_table(self, data: Any, styles) -> Any:
        """Render any dict (or value) as a two-column metric/finding table."""

        def wrap(text: Any) -> Paragraph:
            return Paragraph(self._stringify(text), styles["TableBody"])

        def label(key: str) -> Paragraph:
            return Paragraph(self._label(key), styles["TableLabel"])

        if not isinstance(data, dict):
            data = {"details": data}

        # Special case: improvement_suggestions with priority / quick_wins lists
        if any(
            k in data and isinstance(data[k], list) and data[k] and isinstance(data[k][0], dict)
            for k in ("priority", "quick_wins", "details")
        ):
            rows = [
                [
                    Paragraph("Area", styles["TableHeader"]),
                    Paragraph("Suggestion / Finding", styles["TableHeader"]),
                ]
            ]
            for section_key in ("priority", "quick_wins", "details"):
                items = data.get(section_key) or []
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict):
                        area = item.get("area") or item.get("metric") or ""
                        suggestion = (
                            item.get("suggestion")
                            or item.get("finding")
                            or item.get("details")
                            or ""
                        )
                    else:
                        area = ""
                        suggestion = str(item)
                    rows.append([
                        Paragraph(str(area), styles["TableBody"]),
                        Paragraph(str(suggestion)[:400], styles["TableBody"]),
                    ])
            table = Table(rows, colWidths=[1.5 * inch, 4.9 * inch], repeatRows=1)
        else:
            rows = [
                [
                    Paragraph("Metric", styles["TableHeader"]),
                    Paragraph("Finding", styles["TableHeader"]),
                ]
            ]
            for key, value in data.items():
                rows.append([label(key), wrap(value)])
            table = Table(rows, colWidths=[1.75 * inch, 4.65 * inch], repeatRows=1)

        table.setStyle(self._table_style())
        table.splitByRow = 1
        table.splitInRow = 1
        return table

    def _kv_table(self, data: dict[str, Any], styles) -> Any:
        """Simple key-value table used for owner info."""
        rows = [
            [
                Paragraph("Field", styles["TableHeader"]),
                Paragraph("Value", styles["TableHeader"]),
            ]
        ]
        for key, value in data.items():
            rows.append([
                Paragraph(key, styles["TableBody"]),
                Paragraph(str(value), styles["TableBody"]),
            ])
        table = Table(rows, colWidths=[1.75 * inch, 4.65 * inch], repeatRows=1)
        table.setStyle(self._table_style())
        return table

    def _palette_section(self, palette: list[str], styles) -> list[Any]:
        if not palette:
            return []
        rows = [["Swatch", "Hex Code"]]
        for color in palette[:8]:
            rows.append(["", color])
        table = Table(rows, colWidths=[0.9 * inch, 1.4 * inch])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        for idx, color in enumerate(palette[:8], start=1):
            try:
                style_cmds.append(("BACKGROUND", (0, idx), (0, idx), colors.HexColor(color)))
            except Exception:
                pass
        table.setStyle(TableStyle(style_cmds))
        return [
            Paragraph("Colour Palette", styles["SubSection"]),
            table,
            Spacer(1, 0.15 * inch),
        ]

    def _table_style(self) -> TableStyle:
        return TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  NAVY),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0),  9),
            ("BACKGROUND",   (0, 1), (-1, -1), LIGHT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, WHITE]),
            ("GRID",         (0, 0), (-1, -1), 0.25, BORDER),
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",     (0, 1), (-1, -1), 9),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ])

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    def _make_styles(self):
        styles = getSampleStyleSheet()
        add = styles.add

        add(ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontSize=13,
            leading=18,
            spaceBefore=16,
            spaceAfter=6,
            textColor=NAVY,
            fontName="Helvetica-Bold",
        ))
        add(ParagraphStyle(
            name="SubSection",
            parent=styles["Heading3"],
            fontSize=10,
            leading=14,
            spaceBefore=8,
            spaceAfter=4,
            textColor=SLATE,
            fontName="Helvetica-Bold",
        ))
        add(ParagraphStyle(
            name="Body",
            parent=styles["BodyText"],
            fontSize=9,
            leading=13,
            spaceBefore=2,
            spaceAfter=4,
            textColor=SLATE,
        ))
        add(ParagraphStyle(
            name="TableBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
            textColor=SLATE,
        ))
        add(ParagraphStyle(
            name="TableLabel",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
            textColor=NAVY,
            fontName="Helvetica-Bold",
        ))
        add(ParagraphStyle(
            name="TableHeader",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
            textColor=WHITE,
            fontName="Helvetica-Bold",
        ))
        return styles

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _draw_wrapped_text(
        self, canvas, text: str, x: float, y: float, max_width: float, line_height: float
    ) -> None:
        """Naive word-wrap for canvas.drawString calls on the cover page."""
        words = text.split()
        line = ""
        for word in words:
            test = f"{line} {word}".strip()
            if canvas.stringWidth(test, "Helvetica", 9) < max_width:
                line = test
            else:
                canvas.drawCentredString(x + max_width / 2, y, line)
                y -= line_height
                line = word
        if line:
            canvas.drawCentredString(x + max_width / 2, y, line)

    def _label(self, key: str) -> str:
        return key.replace("_", " ").title()

    def _stringify(self, value: Any, limit: int = 900) -> str:
        if isinstance(value, list):
            # If list of dicts, show as "key: value; ..."
            if value and isinstance(value[0], dict):
                parts = []
                for item in value[:10]:
                    parts.append(
                        ", ".join(f"{self._label(str(k))}: {v}" for k, v in item.items())
                    )
                return self._truncate("; ".join(parts), limit)
            return self._truncate(", ".join(str(v) for v in value[:15]), limit)
        if isinstance(value, dict):
            rendered = "; ".join(
                f"{self._label(str(k))}: {self._stringify(v, 200)}"
                for k, v in value.items()
            )
            return self._truncate(rendered, limit)
        return self._truncate(str(value), limit)

    def _truncate(self, text: str, limit: int = 900) -> str:
        return text if len(text) <= limit else text[:limit].rstrip() + " …"