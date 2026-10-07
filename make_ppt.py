#!/usr/bin/env python3
"""
Builds AISYS_RFID_Library_Technical_Presentation.pptx (10 slides, 16:9).

    pip install python-pptx
    python build_presentation.py

Slide 3 reserves the right-hand side for assets/architecture_diagram.png.
If that file exists it is inserted (scaled to fit); if not, a native 7-layer
stack is drawn in its place so the slide is never empty.
All slide text lives in the build_* functions below, so edits are one-line changes.
"""
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

# ----------------------------------------------------------------- settings
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "AISYS_RFID_Library_Technical_Presentation.pptx"
DIAGRAM = ROOT / "assets" / "architecture_diagram.png"
TOTAL = 10
TOP = 1.65                      # y where slide content starts (inches)

BG = RGBColor(0x0F, 0x17, 0x2A)         # #0F172A  slide background
TEXT = RGBColor(0xF8, 0xFA, 0xFC)       # #F8FAFC  primary text
BLUE = RGBColor(0x38, 0xBD, 0xF8)       # #38BDF8  accent
EMERALD = RGBColor(0x10, 0xB9, 0x81)    # #10B981  key stats
CARD = RGBColor(0x1E, 0x29, 0x3B)       # card surface (lighter slate of the background)
BORDER = RGBColor(0x33, 0x41, 0x55)     # card outline
MUTED = RGBColor(0x94, 0xA3, 0xB8)      # footers, hints
FONT = "Calibri"
MONO = "Consolas"
CENTER, LEFT = PP_ALIGN.CENTER, PP_ALIGN.LEFT
MIDDLE, TOPA = MSO_ANCHOR.MIDDLE, MSO_ANCHOR.TOP


# ------------------------------------------------------------------ helpers
def _bullet(p, size):
    """Real hanging bullet (wrapped lines align under the text)."""
    pPr = p._p.get_or_add_pPr()
    hang = int(Pt(size) * 1.3)
    pPr.set("marL", str(hang))
    pPr.set("indent", str(-hang))
    clr = etree.SubElement(pPr, qn("a:buClr"))
    etree.SubElement(clr, qn("a:srgbClr")).set("val", "38BDF8")
    etree.SubElement(pPr, qn("a:buChar")).set("char", "•")


def add_text(slide, x, y, w, h, paras, size=16, color=TEXT, bold=False, align=LEFT,
             anchor=TOPA, bullet=False, space_after=6, font=FONT):
    """paras: str | list of (str | list of (text, style-dict)) — style keys: size, bold, color, font."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    for i, para in enumerate([paras] if isinstance(paras, str) else paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        for text, style in ([(para, {})] if isinstance(para, str) else para):
            r = p.add_run()
            r.text = text
            r.font.name = style.get("font", font)
            r.font.size = Pt(style.get("size", size))
            r.font.bold = style.get("bold", bold)
            r.font.color.rgb = style.get("color", color)
        if bullet:
            _bullet(p, size)
    return box


def add_card(slide, x, y, w, h, fill=CARD, line=BORDER, line_w=1.25, radius=0.07):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   Inches(x), Inches(y), Inches(w), Inches(h))
    shape.adjustments[0] = radius
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line
    shape.line.width = Pt(line_w)
    shape.shadow.inherit = False
    return shape


def stat_tile(slide, x, y, w, h, value, label, color=EMERALD, vsize=34):
    add_card(slide, x, y, w, h, fill=BG, line=color, line_w=1.5, radius=0.12)
    add_text(slide, x, y + 0.08, w, h * 0.55, value, size=vsize, bold=True, color=color,
             align=CENTER, anchor=MIDDLE, space_after=0)
    add_text(slide, x + 0.05, y + h * 0.60, w - 0.1, h * 0.38, label, size=12,
             align=CENTER, space_after=0)


def card(slide, x, y, w, h, heading, bullets, bsize=15, body_top=0.8, line=BORDER,
         footnote=None):
    """Rounded card with a blue heading and bullet list."""
    add_card(slide, x, y, w, h, line=line)
    add_text(slide, x + 0.3, y + 0.2, w - 0.6, 0.5, heading, size=20, bold=True, color=BLUE)
    add_text(slide, x + 0.3, y + body_top, w - 0.6, h - body_top - 0.3, bullets,
             size=bsize, bullet=True, space_after=8)
    if footnote:
        add_text(slide, x + 0.3, y + h - 0.5, w - 0.6, 0.35, footnote, size=11, color=MUTED)


def new_slide(prs, n, title, subtitle=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])      # blank layout
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BG
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(0.5),
                                 Inches(0.09), Inches(0.82 if subtitle else 0.58))
    bar.fill.solid()
    bar.fill.fore_color.rgb = BLUE
    bar.line.fill.background()
    add_text(slide, 0.85, 0.4, 11.9, 0.6, title, size=30, bold=True, space_after=0)
    if subtitle:
        add_text(slide, 0.85, 0.93, 11.9, 0.4, subtitle, size=17, color=BLUE, space_after=0)
    add_text(slide, 0.6, 7.05, 9.0, 0.3,
             "AISYS RFID Library Management System  |  Technical Evaluation",
             size=10, color=MUTED, space_after=0)
    add_text(slide, 11.73, 7.05, 1.0, 0.3, f"{n} / {TOTAL}", size=10, color=MUTED,
             align=PP_ALIGN.RIGHT, space_after=0)
    return slide


def fit_picture(slide, path, x, y, w, h):
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    slide.shapes.add_picture(str(path), Inches(x + (w - pw) / 2), Inches(y + (h - ph) / 2),
                             Inches(pw), Inches(ph))


def rich(label, text):
    """Bullet with a bold blue lead-in followed by plain text."""
    return [(label, {"bold": True, "color": BLUE}), (text, {})]


# ------------------------------------------------------------------- slides
def build_title(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    top = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.12))
    top.fill.solid()
    top.fill.fore_color.rgb = BLUE
    top.line.fill.background()
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.2), Inches(0.1), Inches(2.6))
    bar.fill.solid()
    bar.fill.fore_color.rgb = EMERALD
    bar.line.fill.background()
    add_text(s, 1.1, 2.1, 7.6, 1.9, "AISYS RFID Library Management System", size=46, bold=True,
             space_after=0)
    add_text(s, 1.1, 4.05, 7.6, 0.9, "Technical Evaluation & 7-Layer Modular Architecture",
             size=22, color=BLUE, space_after=0)
    add_text(s, 1.1, 5.35, 7.6, 0.5, [[("Presenter:  ", {"color": MUTED}),
                                       ("Mouli Palluru", {"bold": True})]], size=18)
    add_card(s, 9.1, 2.3, 3.65, 3.0, line=EMERALD, line_w=2)
    add_text(s, 9.1, 2.55, 3.65, 1.3, "53 / 53", size=60, bold=True, color=EMERALD,
             align=CENTER, anchor=MIDDLE, space_after=0)
    add_text(s, 9.3, 3.95, 3.25, 1.1, ["Acceptance Tests Passed", "(100% Pass Rate)"], size=17,
             align=CENTER, space_after=2)


def build_exec(prs):
    s = new_slide(prs, 2, "Executive Assessment & Core Metrics")
    # Left card - demonstrated
    x, y, w, h = 0.6, TOP, 5.9, 5.25
    add_card(s, x, y, w, h)
    add_text(s, x + 0.3, y + 0.2, w - 0.6, 0.5, "Demonstrated", size=20, bold=True, color=BLUE)
    stat_tile(s, x + 0.3, y + 0.8, 2.55, 1.2, "53 / 53", "Pytest scenarios pass (~5 s)")
    stat_tile(s, x + 3.0, y + 0.8, 2.55, 1.2, "20,000", "records imported in < 5 s")
    add_text(s, x + 0.3, y + 2.25, w - 0.6, 2.8, [
        "53 of 53 Pytest acceptance scenarios pass in about 5 seconds.",
        "20,000-record CSV import and reconciliation in under 5 seconds (XLSX supported).",
        "Modular FastAPI backend covering circulation, NCIP 2.0 / SIP2 adapters, RFID tag "
        "association, gate alarms, handheld audit and RBAC."],
        size=15, bullet=True, space_after=9)
    # Right card - SOP position
    x = 6.83
    add_card(s, x, y, w, h)
    add_text(s, x + 0.3, y + 0.2, w - 0.6, 0.5, "SOP Position", size=20, bold=True, color=BLUE)
    tw = (w - 0.6 - 0.3) / 3
    stat_tile(s, x + 0.3, y + 0.8, tw, 1.2, "7 / 31", "fully met")
    stat_tile(s, x + 0.3 + tw + 0.15, y + 0.8, tw, 1.2, "22", "partially met", color=BLUE)
    stat_tile(s, x + 0.3 + 2 * (tw + 0.15), y + 0.8, tw, 1.2, "2", "queued for backlog",
              color=TEXT)
    add_text(s, x + 0.3, y + 2.2, w - 0.6, 0.4, "Deliverables Index", size=16, bold=True,
             color=BLUE)
    add_text(s, x + 0.3, y + 2.6, w - 0.6, 2.5, [
        rich("D1  ", "Traceability matrix"),
        rich("D2 / D3  ", "Architecture specification"),
        rich("D4  ", "SBOM and licence inventory"),
        rich("D5  ", "Migration tool"),
        rich("D6  ", "Acceptance tests"),
        rich("D7 / D8  ", "Operations runbook"),
        rich("D9  ", "Presentation deck")], size=14, space_after=4)


def build_architecture(prs):
    s = new_slide(prs, 3, "7-Layer Modular Architecture", "Modular Architecture Breakdown")
    add_card(s, 0.6, TOP, 7.0, 5.25)
    add_text(s, 0.9, TOP + 0.2, 6.4, 4.9, [
        rich("Layer 1 · FastAPI / RBAC — ", "REST endpoints, validated requests, role checks"),
        rich("Layer 2 · NCIP 2.0 / SIP2 — ", "mock protocol adapters over one shared rules engine"),
        rich("Layer 3 · Circulation Rules — ", "5-item cap, ₹500 fine limit, member blocks, "
                                               "reference protection"),
        rich("Layer 4 · RFID Middleware & Gate Security — ", "tag association, security-bit "
                                                             "check, alarms, mock CCTV"),
        rich("Layer 5 · Handheld Audit — ", "shelf scans flag missing, misplaced and unknown items"),
        rich("Layer 6 · Notifications — ", "queued security e-mails with background delivery"),
        rich("Layer 7 · Persistence Repository — ", "SQLite schema, staging table and backup "
                                                    "for migrated data")],
        size=15, bullet=True, space_after=11)
    # Right-hand space reserved for the architecture diagram
    rx, ry, rw, rh = 7.85, TOP, 4.88, 5.25
    add_card(s, rx, ry, rw, rh, line=BLUE, line_w=1.5)
    if DIAGRAM.exists():
        fit_picture(s, DIAGRAM, rx + 0.15, ry + 0.15, rw - 0.3, rh - 0.3)
        return True
    add_text(s, rx + 0.3, ry + 0.15, rw - 0.6, 0.4, "Layer Stack", size=16, bold=True, color=BLUE)
    names = ["1  API & RBAC", "2  Protocol Interoperability", "3  Circulation Logic",
             "4  RFID Middleware & Gate Security", "5  Inventory Audit", "6  Notifications",
             "7  Persistence Data Layer"]
    for i, name in enumerate(names):
        yy = ry + 0.7 + i * 0.64
        add_card(s, rx + 0.3, yy, rw - 0.6, 0.54, fill=BG,
                 line=EMERALD if i in (2, 3) else BLUE, line_w=1.25, radius=0.2)
        add_text(s, rx + 0.45, yy, rw - 0.9, 0.54, name, size=14, bold=True, anchor=MIDDLE,
                 space_after=0)
    return False


def build_migration(prs):
    s = new_slide(prs, 4, "High-Throughput Data Migration (D5)",
                  "Ingestion & Reconciliation Engine (migrate.py)")
    w, h = 5.9, 1.95
    xs, ys = (0.6, 6.83), (TOP, TOP + h + 0.15)
    card(s, xs[0], ys[0], w, h, "Bulk Ingestion", [
        "CSV and XLSX input through Pandas",
        "Members and book copies with RFID tags",
        "20,000 rows imported in about 3 seconds"], bsize=14, body_top=0.72)
    card(s, xs[1], ys[0], w, h, "Schema Validation", [
        "Required columns, email, phone, ISBN, tag UID, year",
        "Duplicates checked in file, staging table and database",
        "Rejected rows written to error_log.csv"], bsize=14, body_top=0.72)
    card(s, xs[0], ys[1], w, h, "Transactional Rollback", [
        "One transaction per batch",
        "--rollback reverts the whole batch if any row is rejected",
        "Unexpected errors always revert; existing records are never modified"],
        bsize=14, body_top=0.72)
    card(s, xs[1], ys[1], w, h, "Reconciliation Logging", [
        "Total Read, Valid, Rejected, Inserted",
        "Automatic consistency check on the counts",
        "Every row's outcome kept in the staging table"], bsize=14, body_top=0.72)
    sy, sh, sw = 5.85, 1.05, 3.9
    stat_tile(s, 0.6, sy, sw, sh, "≈ 3 s", "20,000 rows imported", vsize=28)
    stat_tile(s, 0.6 + sw + 0.215, sy, sw, sh, "0", "existing records modified (insert-only)",
              vsize=28)
    stat_tile(s, 0.6 + 2 * (sw + 0.215), sy, sw, sh, "1", "transaction per batch", vsize=28,
              color=BLUE)


def build_circulation(prs):
    s = new_slide(prs, 5, "Circulation Logic & Security Gate Middleware")
    x, w = 0.6, 12.13
    add_card(s, x, TOP, w, 2.45)
    add_text(s, x + 0.3, TOP + 0.15, 6, 0.45, "Circulation Rules", size=20, bold=True, color=BLUE)
    tw = (w - 0.6 - 0.45) / 4
    for i, (v, lab, col) in enumerate([("5 items", "loan cap per member", EMERALD),
                                       ("₹500", "fine limit at check-out", EMERALD),
                                       ("Blocks", "member account blocking", BLUE),
                                       ("Reference", "item protection", BLUE)]):
        stat_tile(s, x + 0.3 + i * (tw + 0.15), TOP + 0.75, tw, 1.45, v, lab, color=col, vsize=30)
    y2 = TOP + 2.6
    add_card(s, x, y2, w, 2.65)
    add_text(s, x + 0.3, y2 + 0.15, 6, 0.45, "Exit Gate Security", size=20, bold=True, color=BLUE)
    steps = ["Gate event", "Security-bit check", "Alarm + accession no.", "Mock CCTV capture",
             "Queued e-mail"]
    bw, gap = 1.95, 0.3
    for i, label in enumerate(steps):
        bx = x + 0.4 + i * (bw + gap)
        add_card(s, bx, y2 + 0.7, bw, 0.75, fill=BG, line=EMERALD if i == 2 else BLUE,
                 radius=0.2)
        add_text(s, bx, y2 + 0.7, bw, 0.75, label, size=13, bold=True, align=CENTER,
                 anchor=MIDDLE, space_after=0)
        if i < len(steps) - 1:
            add_text(s, bx + bw, y2 + 0.7, gap, 0.75, "→", size=18, bold=True, color=BLUE,
                     align=CENTER, anchor=MIDDLE, space_after=0)
    add_text(s, x + 0.3, y2 + 1.65, w - 0.6, 0.95, [
        "Real-time RFID tag monitoring at the exit gate",
        "Unauthorized item detection: unissued or unknown tags fail secure",
        "Mock CCTV snapshot reference attached to every alarm"],
        size=14, bullet=True, space_after=4)


def build_protocols(prs):
    s = new_slide(prs, 6, "Protocol Adapters & Handheld Inventory Audit")
    w, h = 5.9, 5.25
    card(s, 0.6, TOP, w, h, "Handheld Shelf Inventory", [
        "Batch reconciliation of scanned tags against shelf records",
        "Flags missing and misplaced books",
        "Also reports items on loan but on the shelf, and unknown tags",
        "Duplicate reads are collapsed; the audit never alters records"],
        bsize=16, body_top=0.85, footnote="Mocked handheld reader")
    card(s, 6.83, TOP, w, h, "Protocol Interoperability", [
        "NCIP 2.0 adapter for inter-library workflows: CheckOutItem, CheckInItem, LookupItem",
        "SIP2 boundary for kiosk hardware: messages 11, 09 and 17",
        "Both adapters call the same circulation rules as the REST API"],
        bsize=16, body_top=0.85, footnote="Simplified NCIP (JSON) and SIP2 mocks")


def build_api_docs(prs):
    s = new_slide(prs, 7, "Interactive API Documentation & Verification",
                  "Live API Control (Swagger UI)")
    w, h, gap = 3.9, 3.55, 0.215
    items = [
        ("Interactive Swagger UI", "http://127.0.0.1:8000/docs",
         "Try every endpoint in the browser while the service runs locally."),
        ("Role-Based Endpoint Execution", "admin · staff · patron",
         "Send the X-Role header to exercise protected endpoints; other callers receive 403."),
        ("Strict JSON Schemas", "Pydantic request models",
         "Malformed requests are rejected with clear validation errors.")]
    for i, (head, code, desc) in enumerate(items):
        x = 0.6 + i * (w + gap)
        add_card(s, x, TOP, w, h)
        add_text(s, x + 0.25, TOP + 0.2, w - 0.5, 0.8, head, size=19, bold=True, color=BLUE)
        add_card(s, x + 0.25, TOP + 1.1, w - 0.5, 0.7, fill=BG, line=BORDER, radius=0.15)
        add_text(s, x + 0.3, TOP + 1.1, w - 0.6, 0.7, code, size=14, color=EMERALD, font=MONO,
                 anchor=MIDDLE, space_after=0)
        add_text(s, x + 0.25, TOP + 2.0, w - 0.5, 1.4, desc, size=14, space_after=0)
    y = TOP + h + 0.2
    add_card(s, 0.6, y, 12.13, 1.5)
    add_text(s, 0.9, y + 0.15, 11.5, 1.2, [
        rich("Demo tip:  ", "start the service with uvicorn main:app --reload, open /docs, and "
                            "add the header X-Role: admin to try member blocking and the alarm log."),
        rich("Access rules:  ", "admin: block members, view alarms; admin or librarian: "
                                "associate tags; all other callers: 403.")],
        size=14, space_after=6)


def build_tests(prs):
    s = new_slide(prs, 8, "Automated Verification & Quality Assurance (D6)",
                  "Automated Acceptance Suite (test_acceptance.py)")
    tw, gap = 2.88, 0.2
    for i, (v, lab, col) in enumerate([("53", "Passed", EMERALD), ("0", "Failed", EMERALD),
                                       ("100%", "Pass Rate", EMERALD), ("~5 s", "Execution Time", BLUE)]):
        stat_tile(s, 0.6 + i * (tw + gap), TOP, tw, 1.4, v, lab, color=col, vsize=38)
    y = TOP + 1.6
    add_card(s, 0.6, y, 12.13, 3.65)
    add_text(s, 0.9, y + 0.15, 8, 0.45, "Test Scenario Coverage", size=20, bold=True, color=BLUE)
    left = ["Spreadsheet import, validation, duplicates and reconciliation (AC 01)",
            "RFID tag association and uniqueness (AC 02)",
            "NCIP 2.0 and SIP2 check-out / check-in flows (AC 03)",
            "Circulation blocking: reference, blocked member, fine limit (AC 04)"]
    right = ["Handheld inventory audit: missing, misplaced, unknown (AC 05)",
             "Gate event, accession number, mock CCTV, queued e-mail (AC 06)",
             "Role-based access control, 12 tests (AC 07)",
             "Rollback, backup-and-restore and 20,000-row volume (AC 10)"]
    add_text(s, 0.9, y + 0.8, 5.6, 2.7, left, size=14, bullet=True, space_after=9)
    add_text(s, 6.85, y + 0.8, 5.6, 2.7, right, size=14, bullet=True, space_after=9)


def build_links(prs):
    s = new_slide(prs, 9, "Demo, Repository & Project Links", "Everything is Reproducible")
    w, h = 5.9, 2.5
    items = [
        ("1 · Repository", "github.com/MouliPalluru/aisys_rfid_library",
         "Source code, tests, runbook and project documents"),
        ("2 · Interactive API Docs", "http://127.0.0.1:8000/docs",
         "Available while uvicorn main:app is running"),
        ("3 · Acceptance Test Command", "pytest -v test_acceptance.py",
         "53 tests in about 5 seconds"),
        ("4 · Migration Command", "python migrate.py sample/members_sample.csv --entity members",
         "Create demo data first: python migrate.py --make-sample sample")]
    for i, (label, value, hint) in enumerate(items):
        x = 0.6 if i % 2 == 0 else 6.83
        y = TOP if i < 2 else TOP + h + 0.25
        add_card(s, x, y, w, h)
        add_text(s, x + 0.3, y + 0.2, w - 0.6, 0.45, label, size=18, bold=True, color=BLUE)
        add_card(s, x + 0.3, y + 0.8, w - 0.6, 0.9, fill=BG, line=BORDER, radius=0.15)
        add_text(s, x + 0.4, y + 0.8, w - 0.8, 0.9, value, size=14, color=EMERALD, font=MONO,
                 anchor=MIDDLE, space_after=0)
        add_text(s, x + 0.3, y + 1.85, w - 0.6, 0.5, hint, size=12, color=MUTED, space_after=0)


def build_roadmap(prs):
    s = new_slide(prs, 10, "Production Readiness & Architectural Backlog",
                  "Production Roadmap & Next Engineering Steps")
    w, h = 5.9, 2.5
    items = [
        ("PostgreSQL Database Upgrade",
         "Replace the in-memory API store and the SQLite migration target with one persistent "
         "PostgreSQL layer."),
        ("OAuth2 / JWT Authentication Hardening",
         "Replace the header-based role check with verified identity, TLS and audit logging."),
        ("Web Admin Dashboard",
         "Statistics and filterable reports for items, members, circulation, operators and "
         "gate events."),
        ("UAT Sign-off",
         "Library-staff acceptance testing and Windows 11 / Server 2022 validation of the "
         "install, update and rollback procedures.")]
    for i, (head, desc) in enumerate(items):
        x = 0.6 if i % 2 == 0 else 6.83
        y = TOP if i < 2 else TOP + h + 0.25
        add_card(s, x, y, w, h)
        add_card(s, x + 0.3, y + 0.28, 0.6, 0.6, fill=EMERALD, line=EMERALD, radius=0.5)
        add_text(s, x + 0.3, y + 0.28, 0.6, 0.6, str(i + 1), size=20, bold=True, color=BG,
                 align=CENTER, anchor=MIDDLE, space_after=0)
        add_text(s, x + 1.1, y + 0.2, w - 1.4, 0.8, head, size=19, bold=True, color=BLUE,
                 anchor=MIDDLE, space_after=0)
        add_text(s, x + 0.3, y + 1.2, w - 0.6, 1.2, desc, size=15, space_after=0)


# --------------------------------------------------------------------- main
def main():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)     # 16:9
    build_title(prs)
    build_exec(prs)
    used_image = build_architecture(prs)
    for build in (build_migration, build_circulation, build_protocols, build_api_docs,
                  build_tests, build_links, build_roadmap):
        build(prs)
    prs.save(OUTPUT)
    print(f"Saved {OUTPUT.name} ({len(prs.slides)} slides). "
          f"Slide 3 diagram: {'inserted ' + str(DIAGRAM.relative_to(ROOT)) if used_image else 'file not found, native layer stack drawn'}.")


if __name__ == "__main__":
    main()
