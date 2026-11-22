"""Standalone QWidget-based preview for teaching plans."""
from datetime import date
from html import escape
from pathlib import Path
from unicodedata import category

from PySide6.QtCore import (
    QMarginsF,
    QPoint,
    QRectF,
    QStandardPaths,
    Qt,
)
from PySide6.QtGui import (
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)


PAGE_WIDTH = 1123
PAGE_HEIGHT = 794
PAGE_MARGIN = 30
PAGE_CONTENT_WIDTH = PAGE_WIDTH - PAGE_MARGIN * 2
PAGE_CONTENT_HEIGHT = PAGE_HEIGHT - PAGE_MARGIN * 2
CARD_SPACING = 6
MIN_SUMMARY_CARD_WIDTH = 180
PREVIEW_EXPORT_DPI = 300
LEARNING_MODES = (
    ("منهجي", "حصص التعلم المنهجي", "#2563EB", "#EFF6FF"),
    ("إدماج", "حصص التعلم الإدماجي", "#059669", "#ECFDF5"),
    ("تقييم", "حصص التعلم التقييمي", "#D97706", "#FFFBEB"),
    ("دعم وعلاج", "حصص الدعم والعلاج", "#7C3AED", "#F5F3FF"),
)
LEARNING_MODE_NAMES = tuple(mode[0] for mode in LEARNING_MODES)
LEARNING_MODE_STYLES = {
    "منهجي": ("#2563EB", "#EFF6FF"),
    "إدماج": ("#059669", "#ECFDF5"),
    "تقييم": ("#D97706", "#FFFBEB"),
    "دعم وعلاج": ("#7C3AED", "#F5F3FF"),
}


def _plain_label(text, alignment, parent):
    label = QLabel(str(text or "—"), parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )
    label.setWordWrap(True)
    label.setAlignment(alignment)
    return label


def _rich_label(text, alignment, parent, object_name=None):
    label = QLabel(parent)
    if object_name:
        label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )
    label.setWordWrap(True)
    label.setAlignment(alignment)
    label.setText(text)
    return label


def _card(
    title, body, accent, tint, alignment, width, parent=None,
    object_name="teachingPlanPreviewCard",
    expand_body=False,
):
    card = QFrame(parent)
    card.setObjectName(object_name)
    card.setFixedWidth(width)
    card.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Fixed,
    )
    card.setStyleSheet(
        f"QFrame#{object_name} {{"
        f"background:#FFFFFF; border:1px solid {accent};"
        "border-radius:8px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(5)
    if title:
        heading = _plain_label(title, Qt.AlignmentFlag.AlignCenter, card)
        heading.setObjectName("teachingPlanPreviewCardHeading")
        heading.setStyleSheet(
            f"background:{tint}; color:{accent}; font-weight:700;"
            "padding:5px; border-radius:4px;"
        )
        layout.addWidget(heading, 0, Qt.AlignmentFlag.AlignTop)
    if isinstance(body, QWidget):
        layout.addWidget(body, 0, Qt.AlignmentFlag.AlignTop)
    else:
        body_label = _plain_label(body, alignment, card)
        layout.addWidget(
            body_label,
            1 if expand_body else 0,
            Qt.AlignmentFlag(0) if expand_body
            else Qt.AlignmentFlag.AlignTop,
        )
    return card


def _card_height_for_width(card, width):
    layout = card.layout()
    if layout is None:
        return card.sizeHint().height()

    margins = layout.contentsMargins()
    content_width = max(
        0,
        width - margins.left() - margins.right() - 2 * card.frameWidth(),
    )
    height = margins.top() + margins.bottom() + 2 * card.frameWidth()
    for index in range(layout.count()):
        item = layout.itemAt(index)
        child = item.widget()
        if child is None:
            height += item.sizeHint().height()
            continue
        if index:
            height += layout.spacing()
        child_height = (
            child.heightForWidth(content_width)
            if child.hasHeightForWidth()
            else child.sizeHint().height()
        )
        height += max(child_height, 0)
    return height


def _component_match_key(component):
    return "".join(
        character
        for character in str(component or "")
        if not character.isspace()
        and not category(character).startswith("P")
    )


def _component_symbol_map(components):
    symbols = {}
    for component in components:
        key = _component_match_key(component)
        if key and key not in symbols:
            symbols[key] = (component, f"م ك {len(symbols) + 1}")
    return symbols


class _PageView(QGraphicsView):
    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.setObjectName("teachingPlanPreviewPageView")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(Qt.GlobalColor.gray)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.addWidget(page)
        self._scene.setSceneRect(page.rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(
            self._scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )


class TeachingPlanPreviewDialog(QDialog):
    """Render a plan into independent A4-proportioned QWidget pages."""

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        if not isinstance(snapshot, dict) or not isinstance(
            snapshot.get("plan"), dict
        ):
            raise ValueError("بيانات المخطط غير صالحة للمعاينة.")

        self.setObjectName("teachingPlanPreviewDialog")
        self.setWindowTitle("معاينة المخطط")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1180, 820)
        self.setMinimumSize(800, 600)
        self._snapshot = snapshot
        self.pages = []
        self._used_heights = []
        self._build_pages()
        self.page_count = len(self.pages)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("teachingPlanPreviewScrollArea")
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.page_container = QWidget()
        self.page_container.setObjectName("teachingPlanPreviewPageContainer")
        self.page_container.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.page_container_layout = QVBoxLayout(self.page_container)
        self.page_container_layout.setContentsMargins(16, 16, 16, 16)
        self.page_container_layout.setSpacing(20)
        self.page_views = []
        for page in self.pages:
            page_view = _PageView(page, self.page_container)
            page_view.setFixedSize(page.size())
            self.page_views.append(page_view)
            self.page_container_layout.addWidget(
                page_view, 0, Qt.AlignmentFlag.AlignHCenter
            )
        self.page_container.adjustSize()
        self.scroll_area.setWidget(self.page_container)

        layout = QVBoxLayout(self)
        actions_layout = QHBoxLayout()
        actions_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        actions_layout.addStretch(1)
        self.print_button = QPushButton("طباعة", self)
        self.print_button.setObjectName("teachingPlanPreviewPrint")
        self.print_button.setProperty("actionType", "print")
        self.print_button.clicked.connect(self.print_plan)
        self.export_pdf_button = QPushButton("تصدير PDF", self)
        self.export_pdf_button.setObjectName("teachingPlanPreviewExportPdf")
        self.export_pdf_button.setProperty("actionType", "export")
        self.export_pdf_button.clicked.connect(self.export_pdf)
        actions_layout.addWidget(self.print_button)
        actions_layout.addWidget(self.export_pdf_button)
        layout.addLayout(actions_layout)
        layout.addWidget(self.scroll_area, 1)

    def print_plan(self):
        try:
            from print_preview import show_application_print_preview

            show_application_print_preview(
                self,
                self._create_printer(),
                len(self.pages),
                self._paint_pages_as_images,
                QPageLayout.Orientation.Landscape,
                "معاينة طباعة المخطط",
            )
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(
                self, "تعذرت معاينة طباعة المخطط", str(error)
            )

    def export_pdf(self):
        plan = self._snapshot["plan"]
        try:
            documents_path = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DocumentsLocation
            )
            if not documents_path:
                raise OSError("تعذر تحديد مجلد Documents الخاص بالنظام.")
            documents = Path(documents_path)
            documents.mkdir(parents=True, exist_ok=True)
            filename_parts = (
                "مخطط",
                plan.get("title") or "غير محدد",
                plan.get("plan_number")
                if plan.get("plan_number") is not None
                else "غير محدد",
                plan.get("shared_group_key")
                or plan.get("class_name")
                or "غير محدد",
            )
            filename = "_".join(
                "".join(
                    "_"
                    if character in '<>:"/\\|?*' or ord(character) < 32
                    else character
                    for character in str(part).strip()
                ).strip(" ._")
                or "غير محدد"
                for part in filename_parts
            )[:200]
            path = documents / f"{filename}.pdf"
            self.export_pdf_to_path(path)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "تعذر تصدير PDF", str(error))
            return
        QMessageBox.information(
            self, "اكتمل التصدير", f"تم تصدير المخطط إلى:\n{path}"
        )

    def export_pdf_to_path(self, output_path):
        path = Path(output_path)
        if not str(output_path).strip():
            raise ValueError("يجب تحديد مسار ملف PDF.")
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = self._create_pdf_writer(path)
        self._paint_pages_as_images(writer)
        if not path.is_file() or path.stat().st_size < 1000:
            raise OSError("لم يتم إنشاء ملف PDF صالح.")
        return path

    @staticmethod
    def _create_pdf_writer(path):
        writer = QPdfWriter(str(path))
        writer.setResolution(PREVIEW_EXPORT_DPI)
        writer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Landscape,
            QMarginsF(5.0, 5.0, 5.0, 5.0),
            QPageLayout.Unit.Millimeter,
        ))
        return writer

    @staticmethod
    def _create_printer():
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(PREVIEW_EXPORT_DPI)
        printer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Landscape,
            QMarginsF(5.0, 5.0, 5.0, 5.0),
            QPageLayout.Unit.Millimeter,
        ))
        return printer

    @staticmethod
    def _render_page_image(page, dpi=PREVIEW_EXPORT_DPI):
        if dpi <= 0:
            raise ValueError("يجب أن تكون دقة الصورة أكبر من صفر.")
        pixel_width = round(page.width() * dpi / 96)
        pixel_height = round(page.height() * dpi / 96)
        image = QImage(
            pixel_width,
            pixel_height,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        if image.isNull():
            raise OSError("تعذر إنشاء صورة الصفحة بالدقة المطلوبة.")
        image.fill(Qt.GlobalColor.white)
        dots_per_meter = round(dpi / 0.0254)
        image.setDotsPerMeterX(dots_per_meter)
        image.setDotsPerMeterY(dots_per_meter)
        painter = QPainter(image)
        if not painter.isActive():
            raise OSError("تعذر بدء تحويل الصفحة إلى صورة.")
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.scale(
            pixel_width / page.width(),
            pixel_height / page.height(),
        )
        page.ensurePolished()
        if page.layout() is not None:
            page.layout().activate()
        try:
            page.render(painter, QPoint())
        finally:
            painter.end()
        return image

    def _paint_pages_as_images(self, printer, page_numbers=None):
        if page_numbers is None:
            page_numbers = list(range(1, len(self.pages) + 1))
        if not page_numbers:
            raise ValueError("لا توجد صفحات جاهزة للطباعة.")
        if any(
            page_number < 1 or page_number > len(self.pages)
            for page_number in page_numbers
        ):
            raise ValueError("رقم صفحة المعاينة غير صالح.")

        painter = QPainter()
        if not painter.begin(printer):
            raise OSError("تعذر بدء الطباعة على الطابعة المحددة.")
        try:
            for index, page_number in enumerate(page_numbers):
                if index and not printer.newPage():
                    raise OSError("تعذر إنشاء صفحة جديدة في ملف PDF.")
                page = self.pages[page_number - 1]
                image = self._render_page_image(page)
                page_rect = printer.pageLayout().paintRectPixels(
                    printer.resolution()
                )
                scale = min(
                    page_rect.width() / image.width(),
                    page_rect.height() / image.height(),
                )
                target_width = image.width() * scale
                target_height = image.height() * scale
                target = QRectF(
                    page_rect.left()
                    + (page_rect.width() - target_width) / 2,
                    page_rect.top()
                    + (page_rect.height() - target_height) / 2,
                    target_width,
                    target_height,
                )
                painter.drawImage(target, image)
        finally:
            painter.end()

    @staticmethod
    def _school_year(plan):
        try:
            start = date.fromisoformat(str(plan.get("start_date") or ""))
        except ValueError:
            return "—"
        start_year = start.year if start.month >= 7 else start.year - 1
        return f"{start_year}-{start_year + 1}"

    @staticmethod
    def _component_records(items):
        records = []
        seen_records = set()
        for item in items:
            for detail in item.get("details", []):
                name = str(
                    detail.get("component_name") or ""
                ).strip()
                text = str(detail.get("component_text") or "").strip()
                record = (name, text)
                match_key = _component_match_key(text or name)
                if match_key and match_key not in seen_records:
                    records.append(record)
                    seen_records.add(match_key)
        return records

    @staticmethod
    def _page():
        page = QFrame()
        page.setObjectName("teachingPlanA4LandscapePage")
        page.setFixedSize(PAGE_WIDTH, PAGE_HEIGHT)
        page.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        page.setStyleSheet(
            "QFrame#teachingPlanA4LandscapePage {"
            "background:#FFFFFF; border:1px solid #D1D5DB; }"
        )
        return page

    def _new_page(self):
        page = self._page()
        self.pages.append(page)
        self._used_heights.append(PAGE_MARGIN)
        return len(self.pages) - 1

    def _append(self, widget, page_index, spacing=CARD_SPACING):
        widget.setParent(self.pages[page_index])
        widget.adjustSize()
        widget_height = max(widget.sizeHint().height(), widget.height())
        if isinstance(widget, QFrame) and widget.layout() is not None:
            widget_height = max(
                widget_height,
                _card_height_for_width(widget, widget.width()),
            )
        top = self._used_heights[page_index]
        has_content = top > PAGE_MARGIN
        required_top = top + (spacing if has_content else 0)
        if (
            required_top + widget_height > PAGE_HEIGHT - PAGE_MARGIN
            and has_content
        ):
            page_index = self._new_page()
            widget.setParent(self.pages[page_index])
            required_top = PAGE_MARGIN
        page = self.pages[page_index]
        required_bottom = required_top + widget_height + PAGE_MARGIN
        if required_bottom > page.height():
            page.setFixedHeight(required_bottom)
        widget.setGeometry(
            PAGE_MARGIN,
            required_top,
            widget.width(),
            widget_height,
        )
        self._used_heights[page_index] = (
            required_top + widget_height
        )
        return page_index

    @staticmethod
    def _position_summary_cards(cards, width):
        row = QWidget()
        row.setObjectName("teachingPlanSummaryRow")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        row.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        spacing = CARD_SPACING
        card_width = (width - spacing * (len(cards) - 1)) // len(cards)
        total_width = card_width * len(cards) + spacing * (len(cards) - 1)
        first_x = (width - total_width) // 2
        card_heights = []
        for card in cards:
            card.setParent(row)
            card.setFixedWidth(card_width)
            card.adjustSize()
            card_heights.append(
                _card_height_for_width(card, card_width)
            )
        card_height = max(card_heights, default=0)
        row.setFixedSize(width, card_height)
        for index, card in enumerate(cards):
            x = width - first_x - card_width - index * (card_width + spacing)
            card.setFixedHeight(card_height)
            card.setGeometry(x, 0, card_width, card_height)
        return row

    @staticmethod
    def _optimized_card_widths(cards, width):
        spacing = CARD_SPACING
        available = width - spacing * (len(cards) - 1)
        minimum_width = MIN_SUMMARY_CARD_WIDTH
        maximum_width = available - minimum_width * (len(cards) - 1)
        if maximum_width < minimum_width:
            return [available // len(cards)] * len(cards)

        def widths_for_height(target_height):
            widths = []
            for card in cards:
                if _card_height_for_width(card, maximum_width) > target_height:
                    return None
                low = minimum_width
                high = maximum_width
                while low < high:
                    middle = (low + high) // 2
                    if _card_height_for_width(card, middle) <= target_height:
                        high = middle
                    else:
                        low = middle + 1
                widths.append(low)
            if sum(widths) > available:
                return None
            return widths

        low_height = 0
        high_height = max(
            _card_height_for_width(card, minimum_width)
            for card in cards
        )
        while low_height < high_height:
            middle = (low_height + high_height) // 2
            if widths_for_height(middle) is None:
                low_height = middle + 1
            else:
                high_height = middle

        widths = widths_for_height(low_height)
        if widths is None:
            return [available // len(cards)] * len(cards)

        spare = available - sum(widths)
        while spare:
            increment = max(1, spare // len(cards))
            for index in range(len(widths)):
                addition = min(increment, spare)
                widths[index] += addition
                spare -= addition
                if spare == 0:
                    break
        return widths

    @staticmethod
    def _position_variable_summary_cards(cards, width):
        row = QWidget()
        row.setObjectName("teachingPlanSummaryRow")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        row.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        spacing = CARD_SPACING
        widths = TeachingPlanPreviewDialog._optimized_card_widths(
            cards, width
        )
        heights = []
        for card, card_width in zip(cards, widths):
            card.setParent(row)
            card.setFixedWidth(card_width)
            card.adjustSize()
            heights.append(_card_height_for_width(card, card_width))
        shared_height = max(heights, default=0)
        row.setFixedSize(width, shared_height)
        x = width
        for card, card_width in zip(cards, widths):
            x -= card_width
            card.setFixedHeight(shared_height)
            card.setGeometry(x, 0, card_width, shared_height)
            x -= spacing
        return row

    def _summary_cards(self, plan, items):
        third = (PAGE_CONTENT_WIDTH - 16) // 3
        counts = plan.get("mode_lesson_counts") or {}
        school_body = "\n".join((
            f"السنة الدراسية: {self._school_year(plan)}",
            f"اسم المعلم: {plan.get('teacher_name') or '—'}",
            f"المجال: {plan.get('domain_name') or '—'}",
        ))
        plan_body = "\n".join((
            str(plan.get("title") or "المخطط"),
            f"عدد الوحدة: {plan.get('plan_number') or 'غير محدد'}",
            f"القسم: {plan.get('shared_group_key') or plan.get('class_name') or '—'}",
        ))
        duration_body = "\n".join((
            f"تاريخ الانطلاق: {plan.get('start_date') or '—'}",
            f"التاريخ المتوقع للانتهاء: {plan.get('expected_end_date') or '—'}",
            "عدد الحصص — " + "، ".join(
                f"{mode}: {counts.get(mode, 0)}"
                for mode in LEARNING_MODE_NAMES
            ),
        ))
        centered = Qt.AlignmentFlag.AlignCenter
        header_cards = [
            _card("", school_body, "#2563EB", "#EFF6FF",
                  centered, third),
            _card("", plan_body, "#2563EB", "#EFF6FF",
                  centered, third),
            _card("", duration_body, "#2563EB", "#EFF6FF",
                  centered, third),
        ]

        competence_parts = [
            (
                "كفاية المجال",
                str(plan.get("domain_competence") or "—"),
            )
        ]
        competence_parts.extend(
            (
                str(item.get("activity_name") or "نشاط"),
                str(item.get("competence_text") or "—"),
            )
            for item in items
        )
        competence_body = QLabel()
        competence_body.setObjectName("teachingPlanCompetenceBody")
        competence_body.setTextFormat(Qt.TextFormat.RichText)
        competence_body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        competence_body.setWordWrap(True)
        competence_body.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        competence_body.setText("<br>".join(
            "<b style='color:#047857;'>"
            f"{escape(name)}:</b> {escape(text)}"
            for name, text in competence_parts
        ))
        competence_card = _card(
            "كفاية المجال والأنشطة",
            competence_body,
            "#059669", "#ECFDF5",
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            third,
        )

        components = self._component_records(items)
        component_symbols = _component_symbol_map(
            [text or name for name, text in components]
        )
        component_body = _rich_label(
            "<br>".join(
                f"<b style='color:#7C3AED;'>"
                f"{escape(component_symbols[_component_match_key(text or name)][1])}"
                "</b>: "
                f"{escape(name + ': ') if name and text and _component_match_key(name) != _component_match_key(text) else ''}"
                f"{escape(text or name)}"
                for name, text in components
            ) or "لا توجد مكونات مسجلة.",
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            None,
            "teachingPlanComponentList",
        )
        component_card = _card(
            "مكونات الكفاية",
            component_body,
            "#7C3AED", "#F5F3FF",
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            third,
        )

        properties = [
            (
                str(prop.get("key") or "").strip(),
                str(prop.get("value") or "").strip(),
            )
            for prop in self._snapshot.get("properties", [])
            if prop.get("key")
            and prop.get("value")
            and prop.get("key") not in (
                "تقديم الوحدة",
                "وضعية الانطلاق",
                "وضعية الاستكشاف",
            )
        ]
        properties_body = _rich_label(
            "<br>".join(
                f"<b style='color:#D97706;'>{escape(key)}:</b> "
                f"{escape(value)}"
                for key, value in properties
            ) or "لا توجد خصائص مسجلة.",
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            None,
            "teachingPlanPropertiesList",
        )
        properties_card = _card(
            "خصائص المخطط",
            properties_body,
            "#D97706", "#FFFBEB",
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            third,
        )
        rows = [
            self._position_summary_cards(header_cards, PAGE_CONTENT_WIDTH),
            self._position_variable_summary_cards(
                [competence_card, component_card, properties_card],
                PAGE_CONTENT_WIDTH,
            ),
        ]
        presentation = next(
            (
                str(prop.get("value") or "").strip()
                for prop in self._snapshot.get("properties", [])
                if prop.get("key") == "تقديم الوحدة"
                and str(prop.get("value") or "").strip()
            ),
            "",
        )
        if presentation:
            card = _card(
                "تقديم الوحدة",
                presentation,
                "#2563EB", "#EFF6FF",
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                PAGE_CONTENT_WIDTH,
                object_name="teachingPlanUnitIntroductionCard",
            )
            rows.append(card)
        return tuple(rows)

    @staticmethod
    def _activity_card(activity, item, component_symbols, width, parent):
        name = str(activity.get("activity_name") or "نشاط")
        class_name = str((item or {}).get("scope_class_name") or "").strip()
        if class_name:
            name = f"{class_name} — {name}"
        duration = activity.get("duration_minutes")
        accent, tint = LEARNING_MODE_STYLES.get(
            activity.get("learning_mode"), ("#64748B", "#F8FAFC")
        )
        rich_body_parts = []

        def append_property(label, value):
            value = str(value or "").strip()
            if value:
                rich_body_parts.append(
                    f"<b style='color:{accent};'>"
                    f"{escape(label)}:</b> {escape(value)}"
                )

        if activity.get("learning_mode") == "منهجي" and item:
            component_codes = []
            for detail in item.get("details", []):
                component = str(
                    detail.get("component_text")
                    or detail.get("component_name")
                    or ""
                ).strip()
                symbol = component_symbols.get(
                    _component_match_key(component)
                )
                if symbol and symbol[1] not in component_codes:
                    component_codes.append(symbol[1])
            if component_codes:
                append_property(
                    "مكوّن الكفاية", ", ".join(component_codes)
                )
        append_property("الهدف المميز", activity.get("specific_objective"))
        append_property("المحتوى", activity.get("content"))
        for key, label in (
            ("lesson_goal", "هدف الحصة"),
            ("target_competencies", "الكفايات المستهدفة"),
            ("evaluation", "التقييم"),
            ("expected_performance", "الأداء المنتظر"),
            ("target_criteria", "المعايير المستهدفة"),
            ("demographic_concept", "المفهوم السكاني"),
            ("health_concept", "المفهوم الصحي"),
            ("life_skills", "المهارات الحياتية"),
        ):
            append_property(label, activity.get(key))
        for prop in activity.get("properties", []):
            if prop.get("key"):
                append_property(prop["key"], prop.get("value"))
        title = name if duration is None else f"{name} — {duration} دقيقة"
        card = _card(
            title,
            _rich_label(
                "<br>".join(rich_body_parts) or "—",
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                parent,
            ),
            accent, tint,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            width,
            parent,
            object_name="teachingPlanLessonActivityCard",
        )
        return card

    def _lesson_row(
        self, lesson_number, activities, items_by_id, component_symbols
    ):
        row = QWidget()
        row.setObjectName("teachingPlanLessonRow")
        row.setFixedWidth(PAGE_CONTENT_WIDTH)
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        row.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        gap = CARD_SPACING
        badge_width = 94
        activity_count = max(1, len(activities))
        initial_card_width = max(
            1,
            (
                PAGE_CONTENT_WIDTH
                - badge_width
                - gap * activity_count
            ) // activity_count,
        )
        lesson_badge = _card(
            "الحصة",
            str(lesson_number),
            "#334155", "#F1F5F9",
            Qt.AlignmentFlag.AlignCenter,
            badge_width,
            row,
            object_name="teachingPlanLessonBadge",
            expand_body=True,
        )
        cards = []
        for activity in activities:
            cards.append(self._activity_card(
                activity,
                items_by_id.get(activity.get("item_source_id")),
                component_symbols,
                initial_card_width,
                row,
            ))
        if not activities:
            empty = _card(
                "لا توجد أنشطة مسجلة",
                "—",
                "#94A3B8", "#F8FAFC",
                Qt.AlignmentFlag.AlignCenter,
                initial_card_width,
                row,
            )
            empty.setObjectName("teachingPlanLessonActivityCard")
            cards.append(empty)

        card_widths = self._optimized_card_widths(
            cards,
            PAGE_CONTENT_WIDTH - badge_width - gap,
        )
        for card, card_width in zip(cards, card_widths):
            card.setFixedWidth(card_width)
            card.adjustSize()

        children = [lesson_badge, *cards]
        for child in children:
            child.adjustSize()
        row_height = max(
            _card_height_for_width(child, child.width())
            for child in children
        )
        row.setFixedHeight(row_height)
        lesson_badge.setFixedHeight(row_height)
        lesson_badge.setGeometry(
            PAGE_CONTENT_WIDTH - badge_width,
            0,
            badge_width,
            row_height,
        )
        x = PAGE_CONTENT_WIDTH - badge_width - gap
        for card, card_width in zip(cards, card_widths):
            x -= card_width
            card.setFixedHeight(row_height)
            card.setGeometry(x, 0, card_width, row_height)
            x -= gap
        return row

    def _build_pages(self):
        snapshot = self._snapshot
        plan = snapshot["plan"]
        items = snapshot.get("items", [])
        items_by_id = {
            item.get("source_id"): item for item in items
            if item.get("source_id") is not None
        }
        component_symbols = _component_symbol_map(
            [
                text or name
                for name, text in self._component_records(items)
            ]
        )
        page_index = self._new_page()

        for row_index, row in enumerate(self._summary_cards(plan, items)):
            page_index = self._append(row, page_index)

        activities_by_mode = {}
        for activity in snapshot.get("activities", []):
            activities_by_mode.setdefault(
                activity.get("learning_mode"), []
            ).append(activity)
        mode_counts = plan.get("mode_lesson_counts") or {}
        lesson_offset = 0
        for mode, heading, accent, tint in LEARNING_MODES:
            activities = activities_by_mode.get(mode, [])
            try:
                count = max(0, int(mode_counts.get(mode, 0) or 0))
            except (TypeError, ValueError):
                count = 0
            if activities:
                count = max(
                    count,
                    max(int(activity.get("lesson_number") or 0)
                        for activity in activities),
                )
            heading_card = _card(
                heading,
                f"عدد الحصص: {count}",
                accent, tint,
                Qt.AlignmentFlag.AlignCenter,
                PAGE_CONTENT_WIDTH,
            )
            page_index = self._append(heading_card, page_index)
            mode_activities = sorted(
                activities,
                key=lambda activity: (
                    int(activity.get("lesson_number") or 0)
                ),
            )
            for lesson_number in range(1, count + 1):
                lesson_activities = [
                    activity for activity in mode_activities
                    if int(activity.get("lesson_number") or 0)
                    == lesson_number
                ]
                row = self._lesson_row(
                    lesson_offset + lesson_number,
                    lesson_activities,
                    items_by_id,
                    component_symbols,
                )
                page_index = self._append(row, page_index)
            lesson_offset += count

        starting_situation = next(
            (
                str(prop.get("value") or "").strip()
                for prop in snapshot.get("properties", [])
                if prop.get("key") == "وضعية الانطلاق"
                and str(prop.get("value") or "").strip()
            ),
            "",
        )
        if starting_situation:
            page_index = self._append(
                _card(
                    "وضعية الانطلاق",
                    starting_situation,
                    "#D97706", "#FFFBEB",
                    Qt.AlignmentFlag.AlignCenter,
                    PAGE_CONTENT_WIDTH,
                ),
                page_index,
            )

        exploration_situation = next(
            (
                str(prop.get("value") or "").strip()
                for prop in snapshot.get("properties", [])
                if prop.get("key") == "وضعية الاستكشاف"
                and str(prop.get("value") or "").strip()
            ),
            "",
        )
        if exploration_situation:
            card = _card(
                "وضعية الاستكشاف",
                exploration_situation,
                "#D97706", "#FFFBEB",
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                PAGE_CONTENT_WIDTH,
                object_name="teachingPlanExplorationSituationCard",
            )
            page_index = self._append(card, page_index)
