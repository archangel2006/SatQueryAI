from __future__ import annotations

import uuid
from io import BytesIO

from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report


def create_change_overlay(
    after_png: bytes | None,
    overlay_png: bytes | None,
) -> bytes | None:
    """
    Places the detected-change highlight on top of the after image.

    The overlay returned by the change detector is treated as a mask:
    near-white pixels are made transparent, while highlighted regions
    remain visible.
    """

    if not after_png:
        return overlay_png

    if not overlay_png:
        return after_png

    after = PILImage.open(BytesIO(after_png)).convert("RGBA")
    overlay = PILImage.open(BytesIO(overlay_png)).convert("RGBA")

    overlay = overlay.resize(after.size, PILImage.Resampling.LANCZOS)

    pixels = overlay.load()

    for y in range(overlay.height):
        for x in range(overlay.width):
            r, g, b, a = pixels[x, y]

            # Treat white/near-white background as transparent.
            if r > 245 and g > 245 and b > 245:
                pixels[x, y] = (r, g, b, 0)
            else:
                # Keep detected regions visible but allow the satellite
                # image underneath to remain visible.
                pixels[x, y] = (r, g, b, min(a, 190))

    combined = PILImage.alpha_composite(after, overlay)

    output = BytesIO()
    combined.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def create_analysis_report(
    *,
    title: str,
    analysis_text: str,
    change_pct: float | None,
    score: float | None,
    method: str | None,
    before_png: bytes | None = None,
    after_png: bytes | None = None,
    overlay_png: bytes | None = None,
) -> bytes:

    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        leading=23,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        spaceBefore=4,
        spaceAfter=5,
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontSize=8.5,
        leading=11,
        spaceAfter=3,
    )

    metric_style = ParagraphStyle(
        "Metric",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
    )

    story = []

    # ---------------------------------------------------------
    # HEADER
    # ---------------------------------------------------------

    story.append(
        Paragraph(
            title,
            title_style,
        )
    )

    story.append(
        Paragraph(
            "Satellite Change Analysis",
            section_style,
        )
    )

    # ---------------------------------------------------------
    # STRUCTURED SUMMARY
    # ---------------------------------------------------------

    summary = analysis_text.strip()

    story.append(
        Paragraph(
            "<b>AI Summary</b>",
            section_style,
        )
    )

    story.append(
        Paragraph(
            summary,
            body_style,
        )
    )

    story.append(Spacer(1, 0.12 * cm))

    # ---------------------------------------------------------
    # METRICS
    # ---------------------------------------------------------

    changed_area = (
        f"{change_pct:.2f}%"
        if change_pct is not None
        else "—"
    )

    score_text = (
        f"{score:.3f}"
        if score is not None
        else "—"
    )

    method_text = method or "—"

    metrics = [
        [
            Paragraph("<b>Changed Area</b>", metric_style),
            Paragraph("<b>Score</b>", metric_style),
            Paragraph("<b>Detection Method</b>", metric_style),
        ],
        [
            Paragraph(changed_area, metric_style),
            Paragraph(score_text, metric_style),
            Paragraph(method_text, metric_style),
        ],
    ]

    metrics_table = Table(
        metrics,
        colWidths=[4.2 * cm, 4.2 * cm, 8.0 * cm],
    )

    metrics_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#F1F3F5"),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#D5D9DE"),
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.HexColor("#E1E4E8"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    story.append(metrics_table)

    story.append(Spacer(1, 0.25 * cm))

    # ---------------------------------------------------------
    # VISUAL COMPARISON
    # ---------------------------------------------------------

    story.append(
        Paragraph(
            "Visual Comparison",
            section_style,
        )
    )

    # Create the actual highlighted-after image.
    combined_png = create_change_overlay(
        after_png,
        overlay_png,
    )

    image_width = 5.65 * cm
    image_height = 4.4 * cm

    image_cells = []
    label_cells = []

    if before_png:
        label_cells.append(
            Paragraph("<b>Before</b>", metric_style)
        )

        image_cells.append(
            Image(
                BytesIO(before_png),
                width=image_width,
                height=image_height,
                kind="proportional",
            )
        )
    else:
        label_cells.append(
            Paragraph("<b>Before</b>", metric_style)
        )
        image_cells.append(
            Paragraph("Image unavailable", body_style)
        )

    if after_png:
        label_cells.append(
            Paragraph("<b>After</b>", metric_style)
        )

        image_cells.append(
            Image(
                BytesIO(after_png),
                width=image_width,
                height=image_height,
                kind="proportional",
            )
        )
    else:
        label_cells.append(
            Paragraph("<b>After</b>", metric_style)
        )
        image_cells.append(
            Paragraph("Image unavailable", body_style)
        )

    if combined_png:
        label_cells.append(
            Paragraph(
                "<b>Detected Change</b>",
                metric_style,
            )
        )

        image_cells.append(
            Image(
                BytesIO(combined_png),
                width=image_width,
                height=image_height,
                kind="proportional",
            )
        )
    else:
        label_cells.append(
            Paragraph(
                "<b>Detected Change</b>",
                metric_style,
            )
        )
        image_cells.append(
            Paragraph("Overlay unavailable", body_style)
        )

    visual_table = Table(
        [
            label_cells,
            image_cells,
        ],
        colWidths=[
            image_width,
            image_width,
            image_width,
        ],
    )

    visual_table.setStyle(
        TableStyle(
            [
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    2,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    2,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    2,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    2,
                ),
            ]
        )
    )

    story.append(visual_table)

    story.append(Spacer(1, 0.2 * cm))

    # ---------------------------------------------------------
    # INTERPRETATION
    # ---------------------------------------------------------

    story.append(
        Paragraph(
            "Interpretation",
            section_style,
        )
    )

    interpretation = (
        f"The analysis identified approximately "
        f"<b>{changed_area}</b> of valid pixels as changed. "
        f"The reported analysis score was "
        f"<b>{score_text}</b>, using the "
        f"<b>{method_text}</b> detection method."
    )

    story.append(
        Paragraph(
            interpretation,
            body_style,
        )
    )

    document.build(story)

    return output.getvalue()


async def save_report(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    analysis_id: uuid.UUID,
    title: str,
    pdf_gcs_uri: str,
) -> Report:

    report = Report(
        session_id=session_id,
        analysis_id=analysis_id,
        title=title,
        pdf_gcs_uri=pdf_gcs_uri,
    )

    db.add(report)

    await db.commit()
    await db.refresh(report)

    return report