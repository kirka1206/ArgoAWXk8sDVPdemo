#!/usr/bin/env python3
"""Build a navigable PDF guide from repository Markdown documentation."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/pdf/ArgoAWXk8sDVPdemo-project-guide.pdf"


@dataclass(frozen=True)
class Source:
    title: str
    path: Path
    level: int = 1
    note: str | None = None


SOURCES: list[Source] = [
    Source("README проекта", ROOT / "README.ru.md"),
    Source("Паспорт стенда d8case.ru", ROOT / "docs/d8case/README.md"),
    Source("Текущий статус", ROOT / "docs/STATUS.md"),
    Source("Актуальные сценарии d8case.ru: индекс", ROOT / "scenarios/d8case/README.md"),
    Source("00. Подготовка демонстратора", ROOT / "scenarios/d8case/00-preflight.md"),
    Source("01. Архитектура GitOps + DVP + AWX", ROOT / "scenarios/d8case/01-architecture-tour.md"),
    Source("02. Управление golden images", ROOT / "scenarios/d8case/02-golden-image-lifecycle.md"),
    Source("03. Self-service через Git и YAML", ROOT / "scenarios/d8case/03-git-environment-request.md"),
    Source("04. Self-service через Web", ROOT / "scenarios/d8case/04-web-self-service.md"),
    Source("05. Административный lifecycle Victor", ROOT / "scenarios/d8case/05-victor-lifecycle.md"),
    Source("06. Drift correction DVP VM", ROOT / "scenarios/d8case/06-vm-drift-correction.md"),
    Source("07. Cleanup и troubleshooting", ROOT / "scenarios/d8case/07-cleanup-and-troubleshooting.md"),
    Source("Исторические сценарии: 01 Initial Deploy", ROOT / "scenarios/01-initial-deploy.md"),
    Source("Исторические сценарии: 02 Scale Application", ROOT / "scenarios/02-scale-application.md"),
    Source("Исторические сценарии: 03 Drift Correction", ROOT / "scenarios/03-drift-correction.md"),
    Source("Исторические сценарии: 04 VM Resize", ROOT / "scenarios/04-vm-resize.md"),
    Source("Исторические сценарии: 05 AWX Post-Config", ROOT / "scenarios/05-awx-post-config.md"),
    Source("Исторические сценарии: 06 Broken Release And Rollback", ROOT / "scenarios/06-broken-release-and-rollback.md"),
    Source("Исторические сценарии: 07 Self-Service Tenant", ROOT / "scenarios/07-self-service-tenant.md"),
    Source("Исторические сценарии: 08 Golden Image Management", ROOT / "scenarios/08-golden-image-management.md"),
    Source("Исторические сценарии: 09 Self-Service Environment Request", ROOT / "scenarios/09-self-service-environment-request.md"),
    Source("Исторические сценарии: 10 Self-Service Portal", ROOT / "scenarios/10-self-service-portal.md"),
    Source("Исторические сценарии: 11 Practicum End-to-End", ROOT / "scenarios/11-practicum-end-to-end.md"),
    Source("Исторические сценарии: 12 DVP VM Drift Correction", ROOT / "scenarios/12-dvp-vm-drift-correction.md"),
    Source("Исторические сценарии: 13 Manual Environment Lifecycle", ROOT / "scenarios/13-manual-environment-lifecycle.md"),
    Source("Операционный runbook", ROOT / "docs/operations.ru.md"),
    Source("Use cases", ROOT / "docs/use-cases.ru.md"),
    Source("Self-service GitOps", ROOT / "docs/self-service.ru.md"),
    Source("Self-service portal", ROOT / "docs/self-service-portal.ru.md"),
    Source("Demo talk track", ROOT / "docs/demo-talk-track.ru.md"),
    Source("Prerequisites", ROOT / "docs/prerequisites.ru.md"),
    Source("Migration plan", ROOT / "docs/migration-plan.ru.md"),
    Source("Next steps", ROOT / "docs/NEXT_STEPS.md"),
]


def register_fonts() -> tuple[str, str, str]:
    regular_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    mono_candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    ]
    regular = next((p for p in regular_candidates if Path(p).exists()), None)
    mono = next((p for p in mono_candidates if Path(p).exists()), None)
    if not regular:
        raise RuntimeError("No Cyrillic-capable TTF font found")
    pdfmetrics.registerFont(TTFont("DocFont", regular))
    pdfmetrics.registerFont(TTFont("DocFontBold", regular))
    if mono:
        pdfmetrics.registerFont(TTFont("DocMono", mono))
    else:
        pdfmetrics.registerFont(TTFont("DocMono", regular))
    return "DocFont", "DocFontBold", "DocMono"


FONT, FONT_BOLD, FONT_MONO = register_fonts()


class BookmarkParagraph(Paragraph):
    def __init__(self, text: str, style: ParagraphStyle, bookmark: str, level: int, toc_text: str):
        super().__init__(text, style)
        self.bookmark = bookmark
        self.level = level
        self.toc_text = toc_text


class GuideDoc(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(2.0 * cm, 1.8 * cm, A4[0] - 4.0 * cm, A4[1] - 3.8 * cm, id="normal")
        cover = Frame(2.0 * cm, 2.0 * cm, A4[0] - 4.0 * cm, A4[1] - 4.0 * cm, id="cover")
        self.addPageTemplates(
            [
                PageTemplate(id="cover", frames=[cover], onPage=self.cover_page),
                PageTemplate(id="normal", frames=[frame], onPage=self.normal_page),
            ]
        )

    def afterFlowable(self, flowable):
        if isinstance(flowable, BookmarkParagraph):
            self.canv.bookmarkPage(flowable.bookmark)
            self.canv.addOutlineEntry(flowable.toc_text, flowable.bookmark, max(0, flowable.level - 1), closed=False)
            self.notify("TOCEntry", (flowable.level - 1, flowable.toc_text, self.page, flowable.bookmark))

    def cover_page(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#0f2f57"))
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#2d8cff"))
        canvas.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, fill=1, stroke=0)
        canvas.restoreState()

    def normal_page(self, canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(2.0 * cm, 1.1 * cm, "ArgoAWXk8sDVPdemo - project guide")
        canvas.drawRightString(A4[0] - 2.0 * cm, 1.1 * cm, f"Page {doc.page}")
        canvas.setStrokeColor(colors.HexColor("#d7dde6"))
        canvas.line(2.0 * cm, 1.45 * cm, A4[0] - 2.0 * cm, 1.45 * cm)
        canvas.restoreState()


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName=FONT_BOLD,
            fontSize=30,
            leading=36,
            textColor=colors.white,
            alignment=TA_LEFT,
            spaceAfter=24,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#dbeafe"),
            spaceAfter=10,
        ),
        "h1": ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=20, leading=25, spaceBefore=14, spaceAfter=8, textColor=colors.HexColor("#0f2f57")),
        "h2": ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=15, leading=20, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1f4e79")),
        "h3": ParagraphStyle("h3", fontName=FONT_BOLD, fontSize=12.5, leading=16, spaceBefore=8, spaceAfter=5, textColor=colors.HexColor("#334155")),
        "body": ParagraphStyle("body", fontName=FONT, fontSize=9.2, leading=13, spaceAfter=5, alignment=TA_LEFT),
        "small": ParagraphStyle("small", fontName=FONT, fontSize=8, leading=11, spaceAfter=4, textColor=colors.HexColor("#475569")),
        "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=9.0, leading=12.5, leftIndent=14, firstLineIndent=-8, spaceAfter=3),
        "code": ParagraphStyle("code", fontName=FONT_MONO, fontSize=7.0, leading=9.0, textColor=colors.HexColor("#111827")),
        "table": ParagraphStyle("table", fontName=FONT, fontSize=7.2, leading=9.2),
        "toc_title": ParagraphStyle("toc_title", fontName=FONT_BOLD, fontSize=19, leading=24, textColor=colors.HexColor("#0f2f57"), spaceAfter=12),
    }


S = styles()


def clean_inline(text: str) -> str:
    text = html.escape(text.strip())
    text = re.sub(r"`([^`]+)`", r"<font name='DocMono'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    return text


def wrap_code_line(line: str, width: int = 96) -> list[str]:
    if len(line) <= width:
        return [line]
    chunks = []
    current = line
    while len(current) > width:
        cut = current.rfind(" ", 0, width)
        if cut < 40:
            cut = width
        chunks.append(current[:cut])
        current = "  " + current[cut:].lstrip()
    chunks.append(current)
    return chunks


def flush_paragraph(story: list, paragraph_lines: list[str]):
    if not paragraph_lines:
        return
    text = " ".join(line.strip() for line in paragraph_lines if line.strip())
    if text:
        story.append(Paragraph(clean_inline(text), S["body"]))
    paragraph_lines.clear()


def table_from_lines(lines: list[str]):
    rows = []
    for line in lines:
        cells = [clean_inline(cell.strip()) for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) > 1 and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in rows[1]):
        rows.pop(1)
    if not rows:
        return []
    max_cols = max(len(row) for row in rows)
    for row in rows:
        row.extend([""] * (max_cols - len(row)))
    page_width = A4[0] - 4.0 * cm
    col_widths = [page_width / max_cols] * max_cols
    data = [[Paragraph(cell, S["table"]) for cell in row] for row in rows]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1fb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f2f57")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [Spacer(1, 3), table, Spacer(1, 6)]


def markdown_to_flowables(text: str, source_path: Path, bookmark_prefix: str, include_title: bool = True) -> list:
    story: list = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    table_lines: list[str] = []
    in_code = False
    heading_counter = 0

    def flush_code():
        nonlocal code_lines
        if code_lines:
            wrapped: list[str] = []
            for line in code_lines:
                wrapped.extend(wrap_code_line(line.rstrip()))
            story.append(
                Table(
                    [[Preformatted(html.escape("\n".join(wrapped)), S["code"])]],
                    colWidths=[A4[0] - 4.2 * cm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f7fb")),
                            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7dde6")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ]
                    ),
                )
            )
            story.append(Spacer(1, 6))
        code_lines = []

    def flush_table():
        nonlocal table_lines
        if table_lines:
            story.extend(table_from_lines(table_lines))
        table_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            flush_paragraph(story, paragraph_lines)
            flush_table()
            if in_code:
                in_code = False
                flush_code()
            else:
                in_code = True
                code_lines = []
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            flush_paragraph(story, paragraph_lines)
            table_lines.append(line)
            continue
        else:
            flush_table()
        match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if match:
            flush_paragraph(story, paragraph_lines)
            level = len(match.group(1))
            title = match.group(2).strip()
            if not include_title and level == 1:
                continue
            heading_counter += 1
            bookmark = f"{bookmark_prefix}-{heading_counter}"
            style_name = "h1" if level == 1 else "h2" if level == 2 else "h3"
            story.append(BookmarkParagraph(clean_inline(title), S[style_name], bookmark, min(level, 3), title))
            continue
        if not line.strip():
            flush_paragraph(story, paragraph_lines)
            story.append(Spacer(1, 3))
            continue
        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        numbered = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if bullet or numbered:
            flush_paragraph(story, paragraph_lines)
            content = bullet.group(1) if bullet else numbered.group(1)
            bullet_text = "•" if bullet else "•"
            story.append(Paragraph(clean_inline(content), S["bullet"], bulletText=bullet_text))
            continue
        quote = re.match(r"^>\s?(.*)$", line)
        if quote:
            flush_paragraph(story, paragraph_lines)
            story.append(Paragraph(clean_inline(quote.group(1)), S["small"]))
            continue
        paragraph_lines.append(line)

    flush_paragraph(story, paragraph_lines)
    flush_table()
    flush_code()
    return story


def source_section(source: Source, index: int) -> list:
    rel = source.path.relative_to(ROOT)
    text = source.path.read_text(encoding="utf-8")
    bookmark = f"source-{index}"
    flow = [
        PageBreak(),
        BookmarkParagraph(clean_inline(source.title), S["h1"], bookmark, 1, source.title),
        Paragraph(f"<font name='DocMono'>{html.escape(str(rel))}</font>", S["small"]),
        Spacer(1, 8),
    ]
    if source.note:
        flow.append(Paragraph(clean_inline(source.note), S["small"]))
    flow.extend(markdown_to_flowables(text, source.path, f"src-{index}", include_title=False))
    return flow


def build_story() -> list:
    story: list = []
    story.extend(
        [
            NextPageTemplate("cover"),
            Spacer(1, 3.0 * cm),
            Paragraph("ArgoAWXk8sDVPdemo", S["title"]),
            Paragraph("Описание проекта, архитектуры и демонстрационных сценариев", S["subtitle"]),
            Spacer(1, 0.8 * cm),
            Paragraph("Сформировано из Markdown-документации репозитория.", S["subtitle"]),
            Paragraph("Актуальный стенд: practicum-tks на d8case.ru.", S["subtitle"]),
            NextPageTemplate("normal"),
            PageBreak(),
        ]
    )
    story.append(BookmarkParagraph("Оглавление", S["toc_title"], "toc", 1, "Оглавление"))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("toc1", fontName=FONT, fontSize=10, leading=14, leftIndent=0, firstLineIndent=0),
        ParagraphStyle("toc2", fontName=FONT, fontSize=9, leading=12, leftIndent=12, firstLineIndent=0),
        ParagraphStyle("toc3", fontName=FONT, fontSize=8, leading=11, leftIndent=24, firstLineIndent=0),
    ]
    story.append(toc)
    story.append(PageBreak())
    story.append(BookmarkParagraph("Как читать этот документ", S["h1"], "how-to-read", 1, "Как читать этот документ"))
    intro = [
        "Документ собран из Git-репозитория ArgoAWXk8sDVPdemo и предназначен для демонстраторов, архитекторов и инженеров сопровождения.",
        "Основной актуальный набор сценариев находится в разделе d8case.ru. Исторические сценарии сохранены отдельно: они полезны для контекста, но команды с demo-prod и d8.kir.lab не следует выполнять на practicum-стенде.",
        "Используйте закладки PDF или оглавление для перехода между разделами. Каждый крупный раздел содержит исходный путь файла в репозитории.",
    ]
    for item in intro:
        story.append(Paragraph(clean_inline(item), S["body"]))
    story.append(Spacer(1, 10))
    story.append(BookmarkParagraph("Состав источников", S["h2"], "sources", 2, "Состав источников"))
    rows = [["Раздел", "Файл"]]
    for source in SOURCES:
        rows.append([source.title, str(source.path.relative_to(ROOT))])
    table = Table([[Paragraph(clean_inline(a), S["table"]), Paragraph(clean_inline(b), S["table"])] for a, b in rows], colWidths=[7.0 * cm, 9.5 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1fb")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    for index, source in enumerate(SOURCES, 1):
        story.extend(source_section(source, index))
    return story


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = GuideDoc(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.8 * cm,
        title="ArgoAWXk8sDVPdemo Project Guide",
        author="Codex",
        subject="GitOps, Argo CD, AWX, DKP/DVP demo documentation",
    )
    doc.multiBuild(build_story())
    print(OUTPUT)


if __name__ == "__main__":
    main()
