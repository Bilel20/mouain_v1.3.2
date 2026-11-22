"""Native-widget dialog for previewing a recorded day's A4 pages."""
import html
import random
import re
from io import BytesIO
from datetime import datetime
from pathlib import Path

from PIL import Image
from PySide6.QtCore import (
    QPoint,
    QBuffer,
    QIODevice,
    QMarginsF,
    QSize,
    QStandardPaths,
    QTimer,
    Qt,
)
from PySide6.QtGui import (
    QPageLayout,
    QPageSize,
    QPainter,
    QPixmap,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import (
    QPrinter,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from busy_overlay import BusyOverlay, start_background_task
from print_preview import (
    paint_widget_pages,
    show_application_print_preview,
)


PAGE_WIDTH = 820
PAGE_HEIGHT = round(PAGE_WIDTH * 297 / 210)
PAGE_MARGIN = 6
PAGE_CONTENT_HEIGHT = PAGE_HEIGHT - 2 * PAGE_MARGIN - 2
PREVIEW_EXPORT_DPI = 600
COLORS = (
    ("#2563EB", "#EFF6FF", "#BFDBFE"),
    ("#059669", "#ECFDF5", "#A7F3D0"),
    ("#D97706", "#FFFBEB", "#FDE68A"),
    ("#7C3AED", "#F5F3FF", "#DDD6FE"),
    ("#DB2777", "#FDF2F8", "#FBCFE8"),
    ("#0891B2", "#ECFEFF", "#A5F3FC"),
    ("#DC2626", "#FEF2F2", "#FECACA"),
    ("#4F46E5", "#EEF2FF", "#C7D2FE"),
)
MONTHLY_SESSION_PALETTES = (
    ("#059669", "#ECFDF5", "#A7F3D0"),
    ("#D97706", "#FFFBEB", "#FDE68A"),
    ("#DB2777", "#FDF2F8", "#FBCFE8"),
    ("#0891B2", "#ECFEFF", "#A5F3FC"),
    ("#65A30D", "#F7FEE7", "#D9F99D"),
    ("#DC2626", "#FEF2F2", "#FECACA"),
    ("#7C3AED", "#F5F3FF", "#DDD6FE"),
)


def _day_date_parts(date_text):
    date_value = datetime.strptime(date_text, "%Y-%m-%d")
    weekdays = (
        "الإثنين", "الثلاثاء", "الأربعاء", "الخميس",
        "الجمعة", "السبت", "الأحد",
    )
    months = (
        "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
        "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
    )
    return (
        weekdays[date_value.weekday()],
        str(date_value.day),
        months[date_value.month - 1],
        str(date_value.year),
    )


def _label(text, style, parent=None):
    label = QLabel(str(text))
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setStyleSheet(style)
    if parent is not None:
        label.setParent(parent)
    return label


class HeightAwareCard(QFrame):
    """Card sized from its measured content height."""

    def __init__(self, object_name, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._content_min_height = 0

    def set_content_heights(self, min_height, preferred_height):
        self._content_min_height = int(min_height)
        self.setMinimumHeight(self._content_min_height)
        self.setMaximumHeight(16777215)
        self.resize(self.width(), int(preferred_height))
        self.setMaximumHeight(self.height())


class PageContentComposer:
    """Position page widgets using measured heights instead of a page layout."""

    def __init__(self, page):
        self.page = page
        self._spacing = 5
        self._next_offset = 0
        self.components = []

    def spacing(self):
        return self._spacing

    def place(self, widget, vertical_offset):
        widget.setParent(self.page)
        widget.move(
            PAGE_MARGIN,
            PAGE_MARGIN + int(vertical_offset),
        )
        widget.show()
        self.components.append(widget)
        self._next_offset = int(vertical_offset) + widget.height() + self._spacing

    def addWidget(self, widget):
        self.place(widget, self._next_offset)


def _calculate_min_height(widget, width):
    widget.setFixedWidth(width)
    widget.ensurePolished()
    layouts = []

    def collect_layouts(layout):
        if layout is None:
            return
        margins = layout.contentsMargins()
        layouts.append(
            (layout, margins.left(), margins.top(), margins.right(),
             margins.bottom(), layout.spacing())
        )
        for index in range(layout.count()):
            item = layout.itemAt(index)
            child_layout = item.layout()
            if child_layout is not None:
                collect_layouts(child_layout)

    def measure_height():
        layout = widget.layout()
        if layout is not None:
            layout.activate()
        widget.ensurePolished()
        if widget.hasHeightForWidth():
            return max(
                widget.minimumSizeHint().height(),
                widget.heightForWidth(width),
            )
        return max(
            widget.sizeHint().height(),
            widget.minimumSizeHint().height(),
        )

    collect_layouts(widget.layout())
    preferred_height = measure_height()
    try:
        for layout_data in layouts:
            layout = layout_data[0]
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        compact_height = measure_height()
    finally:
        for layout, left, top, right, bottom, spacing in layouts:
            layout.setContentsMargins(left, top, right, bottom)
            layout.setSpacing(spacing)
        layout = widget.layout()
        if layout is not None:
            layout.activate()
    return compact_height, preferred_height


def _size_component(widget, width):
    min_height, preferred_height = _calculate_min_height(widget, width)
    if isinstance(widget, HeightAwareCard):
        widget.set_content_heights(min_height, preferred_height)
    else:
        widget.setFixedHeight(preferred_height)
    widget.setSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
    )
    return preferred_height


def _render_page_pixmap(page, dpi=None):
    if dpi is None:
        dpi = PREVIEW_EXPORT_DPI
    if dpi <= 0:
        raise ValueError("يجب أن تكون دقة الصورة أكبر من صفر.")
    pixel_width = round(210 * dpi / 25.4)
    pixel_height = round(297 * dpi / 25.4)
    pixmap = QPixmap(pixel_width, pixel_height)
    if pixmap.isNull():
        raise OSError("تعذر إنشاء Pixmap بالحجم المطلوب.")
    pixmap.fill(Qt.GlobalColor.white)

    painter = QPainter(pixmap)
    if not painter.isActive():
        raise OSError("تعذر بدء الرسم على Pixmap.")
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.TextAntialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
    )
    painter.scale(pixel_width / page.width(), pixel_height / page.height())
    page.ensurePolished()
    if page.layout() is not None:
        page.layout().activate()
    try:
        page.render(painter, QPoint())
    finally:
        painter.end()

    return pixmap


def _pdf_page_dimensions(dpi):
    if dpi <= 0:
        raise ValueError("يجب أن تكون دقة الصورة أكبر من صفر.")
    return round(210 * dpi / 25.4), round(297 * dpi / 25.4)


def _validate_exported_pdf(pdf_path, expected_page_count):
    pdf_data = Path(pdf_path).read_bytes()
    number = rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    media_boxes = re.findall(
        rb"/MediaBox\s*\[\s*("
        + number
        + rb")\s+("
        + number
        + rb")\s+("
        + number
        + rb")\s+("
        + number
        + rb")\s*\]",
        pdf_data,
    )
    if len(media_boxes) != expected_page_count:
        raise RuntimeError("تعذر التحقق من أبعاد صفحات ملف PDF.")
    for page_number, box in enumerate(media_boxes):
        left, bottom, right, top = (float(value) for value in box)
        if right <= left or top <= bottom:
            raise RuntimeError(
                f"أبعاد صفحة PDF رقم {page_number + 1} غير صالحة."
            )

    document = QPdfDocument(None)
    try:
        if document.load(str(pdf_path)) != QPdfDocument.Error.None_:
            raise RuntimeError("تعذر فتح ملف PDF بعد إنشائه.")
        if document.pageCount() != expected_page_count:
            raise RuntimeError("عدد صفحات ملف PDF لا يطابق صفحات المعاينة.")

        for page_number in range(document.pageCount()):
            page_size = document.pagePointSize(page_number)
            if page_size.width() <= 0 or page_size.height() <= 0:
                raise RuntimeError(
                    f"أبعاد صفحة PDF رقم {page_number + 1} غير صالحة."
                )
            image_size = QSize(
                240,
                round(240 * page_size.height() / page_size.width()),
            )
            image = document.render(
                page_number,
                image_size,
                fillColor=Qt.GlobalColor.white,
            )
            if image.isNull():
                raise RuntimeError(
                    f"تعذر قراءة محتوى صفحة PDF رقم {page_number + 1}."
                )
            has_content = any(
                (color := image.pixelColor(x, y)).alpha() > 0
                and (
                    color.red() < 255
                    or color.green() < 255
                    or color.blue() < 255
                )
                for y in range(0, image.height(), 4)
                for x in range(0, image.width(), 4)
            )
            if not has_content:
                raise RuntimeError(
                    f"صفحة PDF رقم {page_number + 1} فارغة."
                )
    finally:
        document.close()


def export_day_preview_to_pdf(payload, output_path, dpi=None):
    if not isinstance(payload, dict):
        raise TypeError("بيانات اليوم يجب أن تكون قاموسًا.")
    if not output_path or not str(output_path).strip():
        raise ValueError("يجب تحديد مسار ملف PDF.")
    if dpi is None:
        dpi = PREVIEW_EXPORT_DPI
    if dpi <= 0:
        raise ValueError("يجب أن تكون دقة الصورة أكبر من صفر.")

    pdf_path = Path(output_path)
    if pdf_path.suffix.lower() != ".pdf":
        pdf_path = pdf_path.with_suffix(".pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    dialog = DayPdfPreviewDialog(payload)
    images = []
    try:
        for page, _, _ in dialog._pages:
            pixmap = _render_page_pixmap(page, dpi)
            images.append(
                Image.fromqimage(pixmap.toImage()).convert("RGB")
            )
        images[0].save(
            pdf_path,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            resolution=dpi,
        )
    finally:
        for image in images:
            image.close()

    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"لم يتم إنشاء ملف PDF: {pdf_path}")
    _validate_exported_pdf(pdf_path, len(dialog._pages))
    return pdf_path


def export_day_preview_to_documents(payload, dpi=None):
    if not isinstance(payload, dict) or not payload.get("date"):
        raise ValueError("يجب تحديد تاريخ اليوم قبل التصدير.")
    documents_path = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    if not documents_path:
        raise OSError("تعذر تحديد مجلد Documents الخاص بالنظام.")
    output_directory = Path(documents_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"school_day_{payload['date']}.pdf"
    return export_day_preview_to_pdf(payload, output_path, dpi)


def _documents_export_path(payload):
    documents_path = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    if not documents_path:
        raise OSError("تعذر تحديد مجلد Documents الخاص بالنظام.")
    output_directory = Path(documents_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    preview_title = str(payload.get("header_title") or "").strip()
    if preview_title:
        filename = re.sub(r'[<>:"/\\|?*]+', "_", preview_title).strip(" .")
        return output_directory / f"{filename}.pdf"
    monthly_document = payload.get("monthly_club_document")
    if isinstance(monthly_document, dict):
        filename = " - ".join((
            "جدول الأنشطة الشهرية للنادي",
            str(monthly_document.get("club_name") or "نادي"),
            str(monthly_document.get("month") or "الشهر"),
        ))
        filename = re.sub(r'[<>:"/\\|?*]+', "_", filename).strip(" .")
        return output_directory / f"{filename}.pdf"
    return output_directory / f"school_day_{payload['date']}.pdf"


def _save_rendered_preview_pdf(
    png_pages, output_path, dpi, expected_page_count
):
    pdf_path = Path(output_path)
    images = []
    try:
        for png_page in png_pages:
            with Image.open(BytesIO(png_page)) as source:
                images.append(source.convert("RGB"))
        images[0].save(
            pdf_path,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            resolution=dpi,
        )
    finally:
        for image in images:
            image.close()
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"لم يتم إنشاء ملف PDF: {pdf_path}")
    _validate_exported_pdf(pdf_path, expected_page_count)
    return pdf_path


def _date_card(date_text, width):
    card = QFrame()
    card.setObjectName("dayPreviewDateCard")
    card.setStyleSheet(
        "QFrame#dayPreviewDateCard { background:#F8FAFC;"
        "border:1px solid #E2E8F0; border-right:5px solid #2563EB;"
        "border-radius:12px; }"
    )
    layout = QHBoxLayout(card)
    layout.setContentsMargins(14, 7, 14, 7)
    layout.setSpacing(24)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    weekday, day, month, year = _day_date_parts(date_text)
    weekday_label = _label(
        f"يوم {weekday}",
        "color:#475569; font-size:12pt; font-weight:600;"
        "background:transparent; border:none;",
    )
    day_label = _label(
        day,
        "color:#1D4ED8; background:#DBEAFE; border-radius:8px;"
        "font-size:16pt; font-weight:700; padding:2px 10px;",
    )
    month_year_label = _label(
        f"{month} {year}",
        "color:#1E3A8A; font-size:12pt; font-weight:700;"
        "background:transparent; border:none;",
    )
    weekday_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    month_year_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(weekday_label)
    layout.addWidget(day_label)
    layout.addWidget(month_year_label)
    card.setFixedWidth(width)
    card.setFixedHeight(60)
    return card


def _title_card(title_text, width):
    card = QFrame()
    card.setObjectName("dayPreviewTitleCard")
    card.setStyleSheet(
        "QFrame#dayPreviewTitleCard { background:#F8FAFC;"
        "border:1px solid #E2E8F0; border-right:5px solid #2563EB;"
        "border-radius:12px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 8, 14, 8)
    title = _label(
        title_text,
        "color:#1E3A8A; font-size:14pt; font-weight:700;"
        "background:transparent; border:none;",
    )
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    card.setFixedWidth(width)
    card.setFixedHeight(60)
    return card


def _monthly_document_card(title_text, body_text, width, object_name,
                           accent="#2563EB"):
    card = HeightAwareCard(object_name)
    card.setStyleSheet(
        f"QFrame#{object_name} {{ background:#FFFFFF;"
        f"border:1px solid #CBD5E1; border-right:4px solid {accent};"
        "border-radius:8px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(3)
    if title_text:
        title = _label(
            title_text,
            f"color:{accent}; font-weight:700;"
            "background:transparent; border:none;",
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
    body = _label(
        body_text or "—",
        "color:#334155; background:transparent; border:none;",
    )
    body.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(body)
    _size_component(card, width)
    return card


def _monthly_club_and_school_row(document, width):
    gap = 5
    available_width = width - gap
    schedule_width = available_width // 3
    school_width = available_width - schedule_width
    row = QWidget()
    row.setObjectName("monthlyClubSchoolDetailsRow")
    row.setFixedWidth(width)
    row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(gap)
    cards = (
        _monthly_document_card(
            "النادي وموعد التنشيط",
            f"اسم النادي: {document.get('club_name') or '—'}\n"
            f"{document.get('club_schedule') or '—'}",
            schedule_width,
            "monthlyClubScheduleCard",
        ),
        _monthly_document_card(
            "بيانات المدرسة",
            f"المدرسة الابتدائية: "
            f"{document.get('school_name') or '—'}\n"
            f"دائرة التفقد: "
            f"{document.get('inspection_district') or '—'}\n"
            f"مدير المدرسة: "
            f"{document.get('school_principal') or '—'}\n"
            f"هاتف المدرسة: "
            f"{document.get('school_phone') or '—'}\n"
            f"البريد الإلكتروني للمدير: "
            f"{document.get('principal_email') or '—'}",
            school_width,
            "monthlyClubSchoolCard",
        ),
    )
    row_height = max(card.height() for card in cards)
    row.setFixedHeight(row_height)
    for card in cards:
        card.setFixedHeight(row_height)
        layout.addWidget(card)
    return row


def _monthly_teacher_card(document, width):
    card = HeightAwareCard("monthlyClubTeacherCard")
    card.setStyleSheet(
        "QFrame#monthlyClubTeacherCard { background:#FFFFFF;"
        "border:1px solid #CBD5E1; border-right:4px solid #2563EB;"
        "border-radius:8px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(3)
    title = _label(
        "بيانات مؤطر النادي",
        "color:#2563EB; font-weight:700;"
        "background:transparent; border:none;",
    )
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)

    columns = QWidget(card)
    columns.setObjectName("monthlyClubTeacherColumns")
    columns.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    columns_layout = QHBoxLayout(columns)
    columns_layout.setContentsMargins(0, 0, 0, 0)
    columns_layout.setSpacing(8)
    right_column = _label(
        f"المعلم: {document.get('teacher_name') or '—'}\n"
        f"الهاتف: {document.get('teacher_phone') or '—'}",
        "color:#334155; background:transparent; border:none;",
        columns,
    )
    right_column.setObjectName("monthlyClubTeacherRightColumn")
    right_column.setAlignment(Qt.AlignmentFlag.AlignCenter)
    left_details = [
        f"الرتبة: {document.get('teacher_grade') or '—'}",
        f"المعرف الوحيد: {document.get('teacher_identifier') or '—'}",
        f"الشهادة العلمية: {document.get('teacher_degree') or '—'}",
    ]
    training_certificates = str(
        document.get("teacher_training_certificates") or ""
    ).strip()
    if training_certificates:
        left_details.append(
            f"الشهادة التكوينية: {training_certificates}"
        )
    left_column = _label(
        "\n".join(left_details),
        "color:#334155; background:transparent; border:none;",
        columns,
    )
    left_column.setObjectName("monthlyClubTeacherLeftColumn")
    left_column.setAlignment(Qt.AlignmentFlag.AlignCenter)
    columns_layout.addWidget(right_column, 1)
    columns_layout.addWidget(left_column, 1)
    layout.addWidget(columns)
    _size_component(card, width)
    return card


def _monthly_session_card(session, width):
    seed = str(
        session.get("id")
        or session.get("session_date")
        or session.get("number")
        or ""
    )
    accent, tint, border = random.Random(seed).choice(
        MONTHLY_SESSION_PALETTES
    )
    card = HeightAwareCard("monthlyClubSessionCard")
    card.setStyleSheet(
        "QFrame#monthlyClubSessionCard { "
        f"background:{tint}; border:1px solid {border}; "
        f"border-right:4px solid {accent};"
        "border-radius:8px; }"
    )
    layout = QHBoxLayout(card)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(12)
    layout.setDirection(QBoxLayout.Direction.RightToLeft)

    summary = QWidget(card)
    summary.setObjectName("monthlyClubSessionSummaryColumn")
    summary.setStyleSheet("background:transparent;")
    summary_layout = QVBoxLayout(summary)
    summary_layout.setContentsMargins(0, 0, 0, 0)
    summary_layout.setSpacing(3)
    heading = _label(
        f"الأسبوع عدد: {session.get('number', '—')}",
        f"color:{accent}; font-weight:700; "
        "background:transparent; border:none;",
        summary,
    )
    heading.setAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    )
    summary_layout.addWidget(heading)
    attendance = _label(
        f"عدد التلاميذ المسجلين بالنادي: "
        f"{session.get('participant_count', 0)}\n"
        f"عدد الغائبين: {session.get('absent_count', 0)}\n"
        f"عدد الحاضرين: {session.get('present_count', 0)}",
        "color:#334155; background:transparent; border:none;",
        summary,
    )
    attendance.setObjectName("monthlyClubSessionSummary")
    attendance.setAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    )
    summary_layout.addWidget(attendance)
    content = _label(
        "",
        "color:#334155; background:transparent; border:none;",
        card,
    )
    content.setObjectName("monthlyClubSessionContent")
    content.setContentsMargins(8, 0, 0, 0)
    content.setTextFormat(Qt.TextFormat.RichText)
    indent_width = max(
        1, content.fontMetrics().horizontalAdvance("  ")
    )
    content_lines = str(session.get("content") or "—").splitlines() or ["—"]
    content_blocks = []
    for index, line in enumerate(content_lines):
        heading = (
            f"<span style='color:{accent};font-weight:700;'>"
            "المحتوى:</span> "
            if index == 0 else ""
        )
        content_value = html.escape(line, quote=True) or "&nbsp;"
        content_blocks.append(
            f"<div style='margin:0px; margin-right:{indent_width}px;'>"
            f"{heading}<span style='color:#334155;'>"
            f"{content_value}</span></div>"
        )
    content.setText("".join(content_blocks))
    content.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    layout.addWidget(content, 3)
    layout.addWidget(summary, 2)
    _size_component(card, width)
    return card


def _monthly_signature_row(document, width):
    signatures = (
        ("إمضاء مؤطر النادي", document.get("teacher_name")),
        (
            "متفقد الدائرة",
            f"{document.get('inspector_name') or 'المتفقد'}\n"
            "(الإمضاء والختم)",
        ),
        (
            "أشهد بصحة البيانات المذكورة",
            f"{document.get('school_name') or '—'} في "
            f"{document.get('signature_date') or '—'}\n"
            f"اسم المدير: {document.get('school_principal') or '—'}\n"
            "(الإمضاء والختم)",
        ),
    )
    gap = 5
    card_width = (width - gap * (len(signatures) - 1)) // len(signatures)
    row = QWidget()
    row.setObjectName("monthlyClubSignatureRow")
    row.setFixedWidth(width)
    row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(gap)
    cards = [
        _monthly_document_card(
            title, body, card_width, "monthlyClubSignatureCard", "#059669"
        )
        for title, body in signatures
    ]
    row_height = max(card.height() for card in cards)
    row.setFixedHeight(row_height)
    for card in cards:
        card.setFixedHeight(row_height)
        layout.addWidget(card)
    return row


def _lesson_card(lesson, index, width):
    accent, tint, border = COLORS[index % len(COLORS)]
    card = HeightAwareCard("dayLessonCard")
    card.setStyleSheet(
        "QFrame#dayLessonCard { background:#FFFFFF;"
        f"border:1px solid {border}; border-right:5px solid {accent};"
        "border-radius:12px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.setSpacing(3)

    title_text = str(
        lesson.get("display_classe") or lesson.get("classe") or "—"
    )
    title = _label(
        title_text,
        f"color:{accent}; font-size:12pt; font-weight:700;"
        "background:transparent; border:none;",
    )
    layout.addWidget(title)

    metadata = (
        ("المجال", lesson.get("majal")),
        ("ساعة التدريس", lesson.get("heure")),
        ("التوقيت", lesson.get("time")),
        (
            lesson.get("display_unit_label") or "الوحدة",
            lesson.get("display_unit_value", lesson.get("wehda_number")),
        ),
        ("الحصة", lesson.get("hessa_number")),
        ("نمط التعلم", lesson.get("namat_taallom")),
    )
    for row_start in (0, 3):
        row = QHBoxLayout()
        row.setSpacing(3)
        for field_name, field_value in metadata[row_start:row_start + 3]:
            chip = _label(
                f"{field_name}: {field_value or '—'}",
                f"color:#334155; background:{tint}; border:1px solid {border};"
                "border-radius:6px; padding:2px 4px;",
            )
            chip.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            row.addWidget(chip, 1)
        layout.addLayout(row)

    _size_component(card, width)
    return card


def _club_daily_session_card(session, index, width):
    accent, tint, border = COLORS[(index + 3) % len(COLORS)]
    card = HeightAwareCard("dayCulturalClubSessionCard")
    card.setStyleSheet(
        "QFrame#dayCulturalClubSessionCard { background:#FFFFFF;"
        f"border:1px solid {border}; border-right:5px solid {accent};"
        "border-radius:12px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(4)
    layout.addWidget(_label(
        f"جلسة نادي {session.get('club_name') or '—'}",
        f"color:{accent}; font-size:12pt; font-weight:700;"
        "background:transparent; border:none;",
    ))
    layout.addWidget(_label(
        f"النوع: {session.get('club_type') or '—'}  |  "
        f"الساعة: {session.get('hour_interval') or '—'}  |  "
        f"المدة: {session.get('duration_minutes') or '—'} دقيقة",
        f"color:#334155; background:{tint}; border:1px solid {border};"
        "border-radius:6px; padding:4px;",
    ))
    properties = session.get("properties", [])
    if properties:
        properties_widget = QWidget(card)
        properties_widget.setObjectName("dayClubSessionProperties")
        properties_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        properties_layout = QVBoxLayout(properties_widget)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        properties_layout.setSpacing(4)
        pair_width = max(160, width - 32)
        for index in range(0, len(properties) - 1, 2):
            pair = QWidget(properties_widget)
            pair.setObjectName("dayClubSessionPropertyPair")
            pair.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(8)
            labels = []
            for prop in properties[index:index + 2]:
                property_label = _activity_detail_label(
                    prop, pair, accent
                )
                property_label.setObjectName("dayClubSessionProperty")
                labels.append(property_label)
            widths, pair_height = _balanced_label_pair_widths(
                labels, pair_width - pair_layout.spacing()
            )
            for property_label, property_width in zip(labels, widths):
                property_label.setFixedWidth(property_width)
                property_label.setFixedHeight(pair_height)
                pair_layout.addWidget(property_label)
            properties_layout.addWidget(pair)

        if len(properties) % 2:
            final_label = _activity_detail_label(
                properties[-1], properties_widget, accent
            )
            final_label.setObjectName("dayClubSessionProperty")
            final_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            properties_layout.addWidget(final_label)
        layout.addWidget(properties_widget)
    _size_component(card, width)
    return card


def _balanced_label_pair_widths(labels, available_width):
    minimum_width = min(max(80, available_width // 5), available_width // 2)
    maximum_width = available_width - minimum_width
    heights = [{} for _label_widget in labels]

    def measure(index, width):
        cache = heights[index]
        if width not in cache:
            label = labels[index]
            label.setFixedWidth(width)
            label.ensurePolished()
            measured = label.heightForWidth(width)
            cache[width] = max(
                label.minimumSizeHint().height(),
                measured if measured >= 0 else label.sizeHint().height(),
            )
        return cache[width]

    initial_width = available_width // 2
    initial_heights = [
        measure(0, initial_width),
        measure(1, available_width - initial_width),
    ]
    initial_height = max(initial_heights)

    def widths_for_height(target_height):
        result = []
        for index in range(2):
            low, high = minimum_width, maximum_width
            if measure(index, high) > target_height:
                return None
            while low < high:
                middle = (low + high) // 2
                if measure(index, middle) <= target_height:
                    high = middle
                else:
                    low = middle + 1
            result.append(low)
        if sum(result) > available_width:
            return None
        return result

    low_height, high_height = 0, initial_height
    while low_height < high_height:
        target_height = (low_height + high_height) // 2
        if widths_for_height(target_height) is None:
            low_height = target_height + 1
        else:
            high_height = target_height

    widths = widths_for_height(high_height)
    if widths is None:
        widths = [initial_width, available_width - initial_width]
    extra_width = available_width - sum(widths)
    widths[0] += extra_width // 2
    widths[1] += extra_width - extra_width // 2
    pair_height = max(
        measure(index, label_width)
        for index, label_width in enumerate(widths)
    )
    return widths, pair_height


def _activity_detail_label(detail, parent, accent):
    name = str(detail.get("key_name") or "—").strip()
    if name.startswith("العنصر:"):
        name = name[len("العنصر:"):].strip()
    value = str(detail.get("value_text") or "—").strip()
    label = _label(
        "",
        "color:#334155; background:#F8FAFC;"
        "border:1px solid #E2E8F0; border-radius:6px; padding:4px;",
        parent,
    )
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setObjectName("dayActivityDetail")
    indent_width = max(1, label.fontMetrics().horizontalAdvance("  "))
    escaped_name = html.escape(name).replace("\n", "<br>")
    escaped_value = html.escape(value).replace("\n", "<br>")
    label.setText(
        f'<div style="margin-right:{indent_width}px;">'
        f'<span style="color:{accent};font-weight:700;">'
        f"{escaped_name}</span>: "
        f'<span style="color:#334155;">{escaped_value}</span></div>'
    )
    return label


def _activity_card(
    activity, index, width, details, spread_details=False
):
    accent, tint, border = COLORS[index % len(COLORS)]
    details = [
        detail
        for _original_index, detail in sorted(
            enumerate(details),
            key=lambda indexed_detail: (
                0
                if str(
                    indexed_detail[1].get("key_name") or ""
                ).strip().casefold()
                in {"مكوّن الكفاية", "مكون الكفاية"}
                else 1
                if str(
                    indexed_detail[1].get("key_name") or ""
                ).strip().casefold()
                in {"الهدف المميز", "الأهداف المميزة"}
                else 2,
                indexed_detail[0],
            ),
        )
    ]
    card = HeightAwareCard("dayActivityCard")
    card.setStyleSheet(
        "QFrame#dayActivityCard {"
        f"background:{tint}; border:1px solid {border};"
        "border-radius:9px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(5)

    heading_text = str(
        activity.get("display_title")
        or activity.get("title")
        or "نشاط دون عنوان"
    )
    if activity.get("time"):
        heading_text += f"  ·  {activity['time']}"
    if activity.get("classe") and not activity.get("display_title"):
        heading_text += f"  ·  {activity['classe']}"
    heading = _label(
        heading_text,
        f"color:{accent}; font-weight:700;"
        "background:transparent; border:none;",
    )
    layout.addWidget(heading)

    if spread_details and details:
        details_widget = QWidget(card)
        details_widget.setObjectName("dayActivityDetailsGrid")
        details_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(4)

        def create_detail_label(detail):
            return _activity_detail_label(detail, details_widget, accent)

        pair_width = max(160, width - 30)
        for detail_index in range(0, len(details) - 1, 2):
            pair = QWidget(details_widget)
            pair.setObjectName("dayActivityDetailPair")
            pair.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(8)
            labels = [
                create_detail_label(details[detail_index]),
                create_detail_label(details[detail_index + 1]),
            ]
            widths, pair_height = _balanced_label_pair_widths(
                labels, pair_width - pair_layout.spacing()
            )
            for label, label_width in zip(labels, widths):
                label.setFixedWidth(label_width)
                label.setFixedHeight(pair_height)
                pair_layout.addWidget(label)
            details_layout.addWidget(pair)

        if len(details) % 2:
            final_label = create_detail_label(details[-1])
            final_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            details_layout.addWidget(final_label)
        layout.addWidget(details_widget)
    else:
        for detail in details:
            detail_label = _activity_detail_label(detail, card, accent)
            detail_label.setStyleSheet(
                "color:#334155; background:transparent; border:none;"
            )
            detail_label.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )
            layout.addWidget(detail_label)

    _size_component(card, width)
    return card


def _monthly_plan_activity_card(activity, index, width, details):
    accent, tint, border = COLORS[index % len(COLORS)]
    card = HeightAwareCard("dayActivityCard")
    card.setStyleSheet(
        "QFrame#dayActivityCard {"
        f"background:{tint}; border:1px solid {border};"
        "border-radius:9px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(7)
    heading = _label(
        activity.get("display_title") or activity.get("title") or "نشاط",
        f"color:{accent}; font-weight:700;"
        "background:transparent; border:none;",
    )
    heading.setAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    )
    layout.addWidget(heading)

    content_values = []
    tool_values = []
    other_details = []
    for detail in details:
        name = str(detail.get("key_name") or "—").strip()
        if name.startswith("العنصر:"):
            name = name[len("العنصر:"):].strip()
        value = str(detail.get("value_text") or "—").strip()
        if name == "المحتوى":
            content_values.append(value)
        elif name == "الأدوات":
            tool_values.append(value)
        else:
            other_details.append((name, value))

    columns = QWidget(card)
    columns.setObjectName("monthlyPlanActivityColumns")
    columns.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    columns_layout = QHBoxLayout(columns)
    columns_layout.setContentsMargins(0, 0, 0, 0)
    columns_layout.setSpacing(10)

    content_column = QWidget(columns)
    content_column.setObjectName("monthlyPlanActivityContentColumn")
    content_column.setStyleSheet("background:transparent;")
    content_layout = QVBoxLayout(content_column)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(3)
    content_label = _label(
        "المحتوى:",
        f"color:{accent}; font-weight:700; background:transparent; border:none;",
        content_column,
    )
    content_label.setAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    )
    content_layout.addWidget(content_label)
    content_text = _label(
        "\n".join(content_values) or "—",
        "color:#334155; background:transparent; border:none;",
        content_column,
    )
    content_text.setObjectName("monthlyPlanActivityContent")
    content_text.setAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    )
    content_layout.addWidget(content_text)

    divider = QFrame(columns)
    divider.setObjectName("monthlyPlanActivityDivider")
    divider.setFixedWidth(1)
    divider.setStyleSheet(f"background:{border}; border:none;")

    details_column = QWidget(columns)
    details_column.setObjectName("monthlyPlanActivityDetailsColumn")
    details_column.setStyleSheet("background:transparent;")
    details_layout = QVBoxLayout(details_column)
    details_layout.setContentsMargins(0, 0, 0, 0)
    details_layout.setSpacing(4)
    if tool_values:
        tools_heading = _label(
            "الأدوات:",
            f"color:{accent}; font-weight:700; "
            "background:transparent; border:none;",
            details_column,
        )
        tools_heading.setObjectName("monthlyPlanActivityDetailsHeading")
        tools_heading.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        details_layout.addWidget(tools_heading)
        for value in tool_values:
            tool_label = _label(
                value,
                "color:#334155; background:transparent; border:none;",
                details_column,
            )
            tool_label.setObjectName("monthlyPlanActivityToolValue")
            tool_label.setAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            )
            details_layout.addWidget(tool_label)
    for name, value in other_details:
        detail_label = _label(
            f"{name}: {value}",
            "color:#334155; background:transparent; border:none;",
            details_column,
        )
        detail_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        details_layout.addWidget(detail_label)
    if not tool_values and not other_details:
        empty_details = _label(
            "لا توجد تفاصيل إضافية.",
            "color:#64748B; background:transparent; border:none;",
            details_column,
        )
        empty_details.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        details_layout.addWidget(empty_details)

    columns_layout.addWidget(content_column, 2)
    columns_layout.addWidget(divider)
    columns_layout.addWidget(details_column, 1)
    layout.addWidget(columns)
    _size_component(card, width)
    return card


def _activity_grid_row(cards, width):
    row = QWidget()
    row.setObjectName("dayActivityGridRow")
    row.setFixedWidth(width)
    row_height = max(card.height() for card in cards)
    row.setFixedHeight(row_height)
    row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    layout = QGridLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(5)
    layout.setVerticalSpacing(0)
    for column, card in enumerate(cards):
        card.setFixedHeight(row_height)
        layout.addWidget(card, 0, column)
        layout.setColumnStretch(column, card.width())
    return row


def _balance_activity_card_widths(cards, row_width, gap_width):
    if len(cards) < 2:
        return

    available_width = row_width - gap_width
    base_width, remainder = divmod(available_width, len(cards))
    minimum_width = 100
    widths = [base_width] * len(cards)
    for index in range(remainder):
        widths[index] += 1

    measured_heights = [{} for _ in cards]

    def measure(card_index, width):
        cache = measured_heights[card_index]
        if width not in cache:
            cache[width] = _size_component(cards[card_index], width)
        return cache[width]

    initial_height = max(
        measure(index, width) for index, width in enumerate(widths)
    )
    maximum_width = available_width - minimum_width * (len(cards) - 1)

    def widths_for_height(target_height):
        required_widths = []
        for index in range(len(cards)):
            low = minimum_width
            high = maximum_width
            if measure(index, high) > target_height:
                return None
            while low < high:
                middle = (low + high) // 2
                if measure(index, middle) <= target_height:
                    high = middle
                else:
                    low = middle + 1
            required_widths.append(low)
        if sum(required_widths) > available_width:
            return None
        return required_widths

    low_height = 0
    high_height = initial_height
    best_widths = widths
    while low_height < high_height:
        target_height = (low_height + high_height) // 2
        candidate_widths = widths_for_height(target_height)
        if candidate_widths is None:
            low_height = target_height + 1
        else:
            high_height = target_height
            best_widths = candidate_widths

    best_widths = widths_for_height(high_height) or best_widths
    extra_width = available_width - sum(best_widths)
    preferred_widths = [
        min(
            maximum_width,
            max(minimum_width, _unwrapped_content_width(card)),
        )
        for card in cards
    ]
    while extra_width:
        width_deficits = [
            max(0, preferred_width - width)
            for preferred_width, width in zip(
                preferred_widths, best_widths
            )
        ]
        total_deficit = sum(width_deficits)
        if not total_deficit:
            break
        allocations = [
            min(
                deficit,
                extra_width * deficit // total_deficit,
            )
            for deficit in width_deficits
        ]
        allocated_width = sum(allocations)
        if not allocated_width:
            recipient = width_deficits.index(max(width_deficits))
            allocations[recipient] = 1
            allocated_width = 1
        for index, allocation in enumerate(allocations):
            best_widths[index] += allocation
        extra_width -= allocated_width

    for index in range(len(best_widths)):
        if not extra_width:
            break
        share = extra_width // (len(best_widths) - index)
        best_widths[index] += share
        extra_width -= share

    for card, width in zip(cards, best_widths):
        _size_component(card, width)


def _unwrapped_content_width(widget):
    preferred_width = 0
    for label in widget.findChildren(QLabel):
        word_wrap = label.wordWrap()
        try:
            label.setWordWrap(False)
            label.ensurePolished()
            preferred_width = max(
                preferred_width, label.sizeHint().width()
            )
        finally:
            label.setWordWrap(word_wrap)
            label.ensurePolished()

    layout = widget.layout()
    if layout is None:
        return preferred_width
    margins = layout.contentsMargins()
    return preferred_width + margins.left() + margins.right() + 2


class DayPdfPreviewDialog(QDialog):
    """Show paginated A4 pages built from native Qt card widgets."""

    def __init__(self, payload, parent=None):
        super().__init__(parent)
        monthly_document = (
            payload.get("monthly_club_document")
            if isinstance(payload, dict) else None
        )
        if not isinstance(payload, dict) or not payload.get("date"):
            raise ValueError("بيانات اليوم غير صالحة للمعاينة.")
        if not isinstance(monthly_document, dict) and (
            not isinstance(payload.get("lessons"), list)
            or (
                not payload["lessons"]
                and not payload.get("club_sessions")
            )
        ):
            raise ValueError(
                "لا توجد حصص أو جلسات نوادٍ مسجلة لهذا اليوم."
            )

        self.setWindowTitle(
            str(payload.get("preview_title") or "معاينة صفحات اليوم")
        )
        self.resize(960, 760)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._payload = payload
        self._pages = []

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        pages_container = QWidget()
        self.pages_layout = QVBoxLayout(pages_container)
        self.pages_layout.setContentsMargins(18, 18, 18, 18)
        self.pages_layout.setSpacing(22)
        if isinstance(monthly_document, dict):
            self._build_monthly_club_pages(monthly_document, payload["date"])
        else:
            self._build_pages(payload)
        scroll_area.setWidget(pages_container)

        layout = QVBoxLayout(self)
        buttons_layout = QHBoxLayout()
        self.export_pdf_button = QPushButton("تصدير PDF", self)
        self.export_pdf_button.setObjectName("dayPreviewExportPdfButton")
        self.export_pdf_button.setProperty("actionType", "export")
        self.export_pdf_button.clicked.connect(self.export_pdf)
        self.print_button = QPushButton("طباعة", self)
        self.print_button.setObjectName("dayPreviewPrintButton")
        self.print_button.setProperty("actionType", "print")
        self.print_button.clicked.connect(self.print_pages)
        buttons_layout.addWidget(self.export_pdf_button)
        buttons_layout.addWidget(self.print_button)
        buttons_layout.addStretch(1)
        layout.addLayout(buttons_layout)
        layout.addWidget(scroll_area)

    def export_pdf(self):
        try:
            output_path = _documents_export_path(self._payload)
            self._export_pages_async(
                output_path,
                lambda pdf_path: QMessageBox.information(
                    self,
                    "نجاح التصدير",
                    f"تم تصدير اليوم إلى:\n{pdf_path}",
                ),
                lambda error: QMessageBox.critical(
                    self, "تعذر تصدير PDF",
                    f"حدث خطأ أثناء تصدير اليوم:\n{error}",
                ),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(
                self, "تعذر تصدير PDF", f"حدث خطأ أثناء تصدير اليوم:\n{exc}"
            )

    def _export_pages_async(self, output_path, on_success, on_error):
        if getattr(self, "_day_export_pending", False):
            return
        self._day_export_pending = True
        self.export_pdf_button.setEnabled(False)
        overlay = BusyOverlay(self)
        png_pages = []
        page_index = 0
        expected_page_count = len(self._pages)

        def finish_with_error(message):
            self._day_export_pending = False
            self.export_pdf_button.setEnabled(True)
            overlay.close()
            on_error(message)

        def render_next_page():
            nonlocal page_index
            try:
                if page_index < len(self._pages):
                    page, _, _ = self._pages[page_index]
                    pixmap = _render_page_pixmap(
                        page, PREVIEW_EXPORT_DPI
                    )
                    buffer = QBuffer()
                    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                    if not pixmap.toImage().save(buffer, "PNG"):
                        raise RuntimeError(
                            "تعذر تجهيز صفحة PDF للتصدير."
                        )
                    png_pages.append(bytes(buffer.data()))
                    buffer.close()
                    page_index += 1
                    QTimer.singleShot(0, render_next_page)
                    return

                started = start_background_task(
                    self,
                    lambda: _save_rendered_preview_pdf(
                        png_pages,
                        output_path,
                        PREVIEW_EXPORT_DPI,
                        expected_page_count,
                    ),
                    lambda path: self._complete_day_export(
                        path, on_success
                    ),
                    lambda error: self._fail_day_export(
                        error, on_error
                    ),
                    overlay=overlay,
                )
                if not started:
                    finish_with_error(
                        "توجد مهمة أخرى قيد التنفيذ في نافذة المعاينة."
                    )
            except (OSError, ValueError, RuntimeError) as exc:
                finish_with_error(str(exc))

        QTimer.singleShot(0, render_next_page)

    def _complete_day_export(self, path, on_success):
        self._day_export_pending = False
        self.export_pdf_button.setEnabled(True)
        on_success(path)

    def _fail_day_export(self, error, on_error):
        self._day_export_pending = False
        self.export_pdf_button.setEnabled(True)
        on_error(error)

    def print_pages(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageLayout(
            QPageLayout(
                QPageSize(QPageSize.PageSizeId.A4),
                QPageLayout.Orientation.Portrait,
                QMarginsF(8, 8, 8, 8),
                QPageLayout.Unit.Millimeter,
            )
        )
        try:
            first_page = self._pages[0][0]
            orientation = (
                QPageLayout.Orientation.Landscape
                if first_page.width() > first_page.height()
                else QPageLayout.Orientation.Portrait
            )
            show_application_print_preview(
                self,
                printer,
                len(self._pages),
                lambda target_printer, page_numbers: paint_widget_pages(
                    target_printer, self._pages, page_numbers
                ),
                orientation,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                "تعذرت معاينة الطباعة",
                f"حدث خطأ أثناء تجهيز المعاينة:\n{exc}",
            )

    def _new_page(self, date_text, include_date=False):
        page = QFrame()
        page.setObjectName("dayPreviewPage")
        page.setFixedSize(PAGE_WIDTH, PAGE_HEIGHT)
        page.setStyleSheet(
            "QFrame#dayPreviewPage { background:#FFFFFF;"
            "border:1px solid #CBD5E1; }"
        )
        page_content = PageContentComposer(page)
        date_card = None
        if include_date:
            title_text = str(self._payload.get("header_title") or "")
            date_card = (
                _title_card(
                    title_text, PAGE_WIDTH - 2 * PAGE_MARGIN
                )
                if title_text else
                _date_card(date_text, PAGE_WIDTH - 2 * PAGE_MARGIN)
            )
            page_content.place(date_card, 0)
        self.pages_layout.addWidget(page, 0, Qt.AlignmentFlag.AlignHCenter)
        self._pages.append((page, page_content, date_card))
        return page_content, date_card

    def _build_pages(self, payload):
        date_text = payload["date"]
        page_content, date_card = self._new_page(
            date_text, include_date=True
        )
        spacing = page_content.spacing()
        used_height = date_card.height() + spacing
        content_width = PAGE_WIDTH - 2 * PAGE_MARGIN
        show_lesson_headers = not payload.get("hide_lesson_headers", False)
        split_monthly_activity_details = payload.get(
            "split_monthly_activity_details", False
        )
        club_statistics = payload.get("club_statistics")
        if isinstance(club_statistics, dict):
            sections = club_statistics.get("sections", [])
            summary_text = (
                f"إجمالي المشاركين: "
                f"{club_statistics.get('participant_count', 0)}"
            )
            if sections:
                summary_text += "\n" + "\n".join(
                    f"{section.get('section_name') or '—'}: "
                    f"{section.get('female_count', 0)} تلميذة، "
                    f"{section.get('male_count', 0)} تلميذ"
                    for section in sections
                )
            statistics_card = _monthly_document_card(
                "إحصاءات الأقسام المشاركة",
                summary_text,
                content_width,
                "monthlyClubPlanStatistics",
            )
            if statistics_card.height() > PAGE_CONTENT_HEIGHT:
                raise ValueError(
                    "بطاقة إحصاءات النادي أكبر من مساحة صفحة المعاينة."
                )
            if (
                used_height + statistics_card.height() + spacing
                > PAGE_CONTENT_HEIGHT
            ):
                page_content, _date_card = self._new_page(date_text)
                used_height = 0
            page_content.addWidget(statistics_card)
            used_height += statistics_card.height() + spacing

        def create_activity_card(
            activity, lesson_index, width, details, spread_details=False
        ):
            if split_monthly_activity_details:
                return _monthly_plan_activity_card(
                    activity, lesson_index, width, details
                )
            return _activity_card(
                activity, lesson_index, width, details, spread_details
            )

        def place_activity_row(cards):
            nonlocal page_content, used_height
            row = _activity_grid_row(cards, content_width)
            row_height = row.height()
            if (
                used_height + row_height + spacing
                > PAGE_CONTENT_HEIGHT
            ):
                page_content, _ = self._new_page(date_text)
                used_height = 0
            page_content.addWidget(row)
            used_height += row_height + spacing

        def place_full_width_activity(
            activity, lesson_index, force_fragment=False,
            spread_details=False,
        ):
            nonlocal page_content, used_height
            details = list(activity.get("details", []))
            card = create_activity_card(
                activity, lesson_index, content_width, details,
                spread_details,
            )
            if card.height() <= PAGE_CONTENT_HEIGHT and not force_fragment:
                place_activity_row([card])
                return
            if not details:
                raise ValueError(
                    "عنوان النشاط أكبر من المساحة المتاحة في صفحة A4."
                )

            remaining_details = details
            while remaining_details:
                available_height = (
                    PAGE_CONTENT_HEIGHT - used_height - spacing
                )
                chunk = []
                for detail in remaining_details:
                    candidate = create_activity_card(
                        activity,
                        lesson_index,
                        content_width,
                        chunk + [detail],
                        spread_details,
                    )
                    if candidate.height() > available_height:
                        break
                    chunk.append(detail)

                if not chunk:
                    if used_height:
                        page_content, _ = self._new_page(date_text)
                        used_height = 0
                        continue
                    raise ValueError(
                        "أحد تفاصيل النشاط أكبر من صفحة المعاينة."
                    )

                fragment = create_activity_card(
                    activity,
                    lesson_index,
                    content_width,
                    chunk,
                    spread_details,
                )
                place_activity_row([fragment])
                remaining_details = remaining_details[len(chunk):]
                if remaining_details:
                    page_content, _ = self._new_page(date_text)
                    used_height = 0

        for lesson_index, lesson in enumerate(payload["lessons"]):
            header = (
                _lesson_card(lesson, lesson_index, content_width)
                if show_lesson_headers else None
            )
            header_height = (
                _size_component(header, content_width) if header else 0
            )
            header_spacing = spacing if header else 0
            if header and header_height > PAGE_CONTENT_HEIGHT:
                raise ValueError(
                    "بطاقة الحصة أكبر من المساحة المتاحة في صفحة A4."
                )

            activities = lesson.get("activities", [])
            activity_groups = [
                activities[start:start + 4]
                for start in range(0, len(activities), 4)
            ]
            keep_first_group = False
            force_fragment_first_activity = False
            first_activity_height = 0
            if activity_groups:
                first_group = activity_groups[0]
                columns = len(first_group)
                gap_width = 5 * (columns - 1)
                card_width = (content_width - gap_width) // columns
                first_group_cards = [
                    create_activity_card(
                        activity,
                        lesson_index,
                        card_width,
                        activity.get("details", []),
                        len(activities) == 1,
                    )
                    for activity in first_group
                ]
                _balance_activity_card_widths(
                    first_group_cards, content_width, gap_width
                )
                first_group_height = max(
                    card.height() for card in first_group_cards
                )
                keep_first_group = (
                    first_group_height <= PAGE_CONTENT_HEIGHT
                    and header_height + header_spacing
                    + first_group_height + spacing
                    <= PAGE_CONTENT_HEIGHT
                )
                if not keep_first_group:
                    first_activity = first_group[0]
                    full_width_card = create_activity_card(
                        first_activity,
                        lesson_index,
                        content_width,
                        first_activity.get("details", []),
                        len(activities) == 1,
                    )
                    first_activity_height = full_width_card.height()
                    if (
                        header_height + header_spacing
                        + first_activity_height + spacing
                        > PAGE_CONTENT_HEIGHT
                    ):
                        details = first_activity.get("details", [])
                        if not details:
                            raise ValueError(
                                "تعذر وضع بطاقة الحصة وأول نشاط في صفحة واحدة."
                            )
                        force_fragment_first_activity = True
                        first_activity_height = create_activity_card(
                            first_activity,
                            lesson_index,
                            content_width,
                            details[:1],
                            len(activities) == 1,
                        ).height()
                    if (
                        header_height + header_spacing
                        + first_activity_height + spacing
                        > PAGE_CONTENT_HEIGHT
                    ):
                        raise ValueError(
                            "تعذر وضع بطاقة الحصة وأول نشاط في صفحة واحدة."
                        )
                    activity_groups = [
                        [first_group[0]],
                        first_group[1:],
                        *activity_groups[1:],
                    ]
                    activity_groups = [
                        group for group in activity_groups if group
                    ]

            required_height = header_height + header_spacing
            if keep_first_group:
                required_height += (
                    first_group_height + spacing
                )
            elif activities:
                required_height += (
                    first_activity_height + spacing
                )
            if used_height + required_height > PAGE_CONTENT_HEIGHT:
                page_content, date_card = self._new_page(date_text)
                used_height = 0
            if header is not None:
                page_content.addWidget(header)
                used_height += header_height + spacing

            if not activities:
                empty = _label(
                    "لا توجد أنشطة مسجلة لهذه الحصة.",
                    "color:#64748B; padding:6px;"
                    "background:#F8FAFC; border-radius:8px;",
                )
                _size_component(empty, content_width - 20)
                if (
                    used_height + empty.height() + spacing
                    > PAGE_CONTENT_HEIGHT
                ):
                    page_content, date_card = self._new_page(date_text)
                    used_height = 0
                page_content.addWidget(empty)
                used_height += empty.height() + spacing
                continue
            for group_index, activity_group in enumerate(activity_groups):
                if group_index == 0 and not keep_first_group:
                    place_full_width_activity(
                        activity_group[0],
                        lesson_index,
                        force_fragment_first_activity,
                        len(activities) == 1,
                    )
                    continue
                columns = len(activity_group)
                gap_width = 5 * (columns - 1)
                activity_card_width = (content_width - gap_width) // columns
                cards = [
                    create_activity_card(
                        activity,
                        lesson_index,
                        activity_card_width,
                        activity.get("details", []),
                        len(activities) == 1,
                    )
                    for activity in activity_group
                ]
                _balance_activity_card_widths(
                    cards, content_width, gap_width
                )
                if all(card.height() <= PAGE_CONTENT_HEIGHT for card in cards):
                    place_activity_row(cards)
                else:
                    for activity in activity_group:
                        place_full_width_activity(
                            activity,
                            lesson_index,
                            spread_details=len(activities) == 1,
                        )

        club_sessions = payload.get("club_sessions", [])
        if club_sessions:
            title = _label(
                "الأنشطة والنوادي",
                "color:#7C3AED; font-size:14pt; font-weight:700;"
                "border-bottom:1px solid #DDD6FE; padding:4px 0;",
            )
            _size_component(title, content_width)
            if used_height + title.height() + spacing > PAGE_CONTENT_HEIGHT:
                page_content, _date_card = self._new_page(date_text)
                used_height = 0
            page_content.addWidget(title)
            used_height += title.height() + spacing
            for index, session in enumerate(club_sessions):
                card = _club_daily_session_card(
                    session, index, content_width
                )
                if card.height() > PAGE_CONTENT_HEIGHT:
                    raise ValueError(
                        "بطاقة جلسة النادي أكبر من مساحة صفحة المعاينة."
                    )
                if (
                    used_height + card.height() + spacing
                    > PAGE_CONTENT_HEIGHT
                ):
                    page_content, _date_card = self._new_page(date_text)
                    used_height = 0
                page_content.addWidget(card)
                used_height += card.height() + spacing

        self.pages_layout.addStretch(1)

    def _build_monthly_club_pages(self, document, date_text):
        content_width = PAGE_WIDTH - 2 * PAGE_MARGIN
        def create_page(include_metadata):
            page_content, _date_card = self._new_page(date_text)
            used_height = 0
            components = []
            if include_metadata:
                title_card = _monthly_document_card(
                    "",
                    document.get("title") or "جدول الأنشطة الشهرية للنادي",
                    content_width,
                    "monthlyClubDocumentTitle",
                )
                title_label = title_card.findChild(QLabel)
                if title_label is not None:
                    title_label.setStyleSheet(
                        "color:#1E3A8A; font-size:14pt; font-weight:700;"
                        "background:transparent; border:none;"
                    )
                title_layout = title_card.layout()
                margins = title_layout.contentsMargins()
                title_layout.setContentsMargins(
                    margins.left(), margins.top(), margins.right(), 16
                )
                title_card.setMaximumHeight(16777215)
                _size_component(title_card, content_width)
                components.extend((
                    _monthly_document_card(
                        "وزارة التربية",
                        "المندوبية الجهوية للتربية بـ "
                        f"{document.get('delegation') or '—'}",
                        content_width,
                        "monthlyClubMinistryCard",
                    ),
                    title_card,
                    _monthly_club_and_school_row(document, content_width),
                    _monthly_teacher_card(document, content_width),
                    _monthly_document_card(
                        "الشهر",
                        document.get("month") or "—",
                        content_width,
                        "monthlyClubMonthCard",
                    ),
                ))
            for component in components:
                height = component.height()
                if height > PAGE_CONTENT_HEIGHT:
                    raise ValueError(
                        "إحدى بطاقات النشاط الشهري أكبر من صفحة A4."
                    )
                page_content.addWidget(component)
                used_height += height + page_content.spacing()
            return page_content, used_height

        page_content, used_height = create_page(include_metadata=True)
        sessions = document.get("sessions", [])
        for session in sessions:
            session_card = _monthly_session_card(session, content_width)
            height = session_card.height()
            if height > PAGE_CONTENT_HEIGHT:
                raise ValueError(
                    "محتوى إحدى الجلسات أكبر من المساحة المتاحة في صفحة A4."
                )
            if used_height + height + page_content.spacing() > PAGE_CONTENT_HEIGHT:
                page_content, used_height = create_page(include_metadata=False)
            page_content.addWidget(session_card)
            used_height += height + page_content.spacing()

        signature_row = _monthly_signature_row(document, content_width)
        if signature_row.height() > PAGE_CONTENT_HEIGHT:
            raise ValueError("بطاقات الإمضاء أكبر من صفحة A4.")
        if used_height + signature_row.height() > PAGE_CONTENT_HEIGHT:
            page_content, used_height = create_page(include_metadata=False)
        page_content.addWidget(signature_row)
        self.pages_layout.addStretch(1)
