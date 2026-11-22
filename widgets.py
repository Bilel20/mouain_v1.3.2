# -*- coding: utf-8 -*-
"""Extracted module widgets."""
import html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    Qt, QDate, QLocale, QPoint, QSize, QTimer,
)
from PySide6.QtGui import (
    QColor, QTextCharFormat, QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCalendarWidget, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHeaderView, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSplitter, QDateEdit,
    QMessageBox,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QFrame, QStyle,
    QGridLayout,
)

from app_config import (
    SCHOOL_INFO_COLUMNS,
    is_small_window,
    set_card_action_type,
    set_dialog_button_action_types,
)
from busy_overlay import start_background_task
from database_connection import connect_database
from day_pdf_preview import (
    DayPdfPreviewDialog,
)
from lesson_book_settings import (
    filter_print_details,
    load_print_detail_exclusions,
)
import sqlite3


def _day_lesson_teaching_time_key(hour_text, lesson_id):
    hour_text = (
        str(hour_text or "")
        .replace("ـ", "-")
        .replace("–", "-")
        .replace("—", "-")
    )
    start_text = hour_text.split("-", 1)[0].strip()
    try:
        start_time = datetime.strptime(start_text, "%H:%M").time()
        return 0, start_time, lesson_id
    except ValueError:
        return 1, datetime.max.time(), lesson_id


def _cultural_club_display_title(clubs, title, class_name, domain):
    def normalized_name(value):
        name = str(value or "").strip().casefold()
        for prefix in ("نادي ", "ناد "):
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        return name

    title_key = normalized_name(title)
    class_key = str(class_name or "").strip().casefold()
    domain_key = str(domain or "").strip().casefold()
    for club in clubs:
        club_name = str(club.get("name") or "").strip()
        club_type = str(club.get("club_type") or "").strip()
        sections = {
            str(section.get("section_name") or "").strip().casefold()
            for section in club.get("sections", [])
        }
        if (
            title_key == normalized_name(club_name)
            and class_key in sections
            and domain_key == club_type.casefold()
        ):
            return f"ناد — {club_type}\n{club_name}"
    return None


def _arabic_month_name(date_text):
    month_names = (
        "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
        "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
    )
    try:
        month_number = int(str(date_text or "").split("-")[1])
    except (IndexError, TypeError, ValueError):
        return ""
    if not 1 <= month_number <= len(month_names):
        return ""
    return month_names[month_number - 1]


def _target_criteria_display_value(learning_mode, key_name, value):
    value = str(value or "")
    if (
        str(learning_mode or "").strip() != "دعم وعلاج"
        or str(key_name or "").strip() != "المعايير المستهدفة"
    ):
        return value

    lines = value.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("- "):
            criterion = line[2:].strip()
            if criterion and not criterion.endswith(":"):
                criterion += ":"
            lines[index] = f"* {criterion}"
    return "\n".join(lines)


def _wrapped_text_height(text, width, font, padding=8):
    """قياس ارتفاع النص بعد الالتفاف على عرض معين باستخدام QTextDocument."""
    doc = QTextDocument()
    doc.setDefaultFont(font)
    doc.setPlainText(str(text or ""))
    doc.setTextWidth(max(20, width))
    return int(doc.size().height()) + padding


class TeacherInfoPopup(QDialog):
    def __init__(self, parent, on_hidden):
        super().__init__(parent, Qt.Popup)
        self._on_hidden = on_hidden

    def hideEvent(self, event):
        super().hideEvent(event)
        self._on_hidden()


class CustomCalendarWidget(QCalendarWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._holiday_date_disabling_enabled = False
        self._holiday_dates = set()
        self._holiday_types = {}
        self._custom_disabled_dates = set()
        self._custom_disabled_tooltip = ""
        self._last_enabled_date = self.selectedDate()
        self.selectionChanged.connect(self.restore_enabled_selection)
        self.refresh_recorded_dates()

    @property
    def _disabled_dates(self):
        return self._holiday_dates

    def set_disabled_dates(
        self, dates, tooltip, background_color="#E2E8F0"
    ):
        self._custom_disabled_dates = {
            day for day in dates if day.isValid()
        }
        self._custom_disabled_tooltip = str(tooltip)
        self._custom_disabled_background_color = QColor(background_color)
        selected = self.selectedDate()
        if self._is_disabled_date(selected):
            self._last_enabled_date = self._nearest_enabled_date(selected)
            if not self._is_disabled_date(self._last_enabled_date):
                self.blockSignals(True)
                self.setSelectedDate(self._last_enabled_date)
                self.blockSignals(False)
        else:
            self._last_enabled_date = selected
        self._apply_disabled_date_formats()

    def set_holiday_date_disabling_enabled(self, enabled):
        self._holiday_date_disabling_enabled = bool(enabled)
        if self._holiday_date_disabling_enabled:
            self.refresh_holiday_dates()

    def showEvent(self, event):
        super().showEvent(event)
        if self._holiday_date_disabling_enabled:
            self.refresh_holiday_dates()

    def refresh_holiday_dates(self):
        disabled_dates = set()
        holiday_types = {}
        for (
            _holiday_id, start_text, end_text, _name, holiday_type
        ) in self.db.holidays():
            current_date = QDate.fromString(start_text, "yyyy-MM-dd")
            end_date = QDate.fromString(end_text, "yyyy-MM-dd")
            while current_date.isValid() and current_date <= end_date:
                disabled_dates.add(current_date)
                holiday_types[current_date] = holiday_type
                current_date = current_date.addDays(1)
        self._holiday_dates = disabled_dates
        self._holiday_types = holiday_types
        selected = self.selectedDate()
        if not self._is_disabled_date(selected):
            self._last_enabled_date = selected
        elif self._is_disabled_date(self._last_enabled_date):
            self._last_enabled_date = self._nearest_enabled_date(selected)
            if not self._is_disabled_date(self._last_enabled_date):
                self.blockSignals(True)
                self.setSelectedDate(self._last_enabled_date)
                self.blockSignals(False)
        self._apply_disabled_date_formats()

    def _is_disabled_date(self, day):
        return (
            day in self._holiday_dates
            or day in self._custom_disabled_dates
        )

    def _nearest_enabled_date(self, reference_date):
        minimum = self.minimumDate()
        maximum = self.maximumDate()
        for distance in range(1, 367):
            for candidate in (
                reference_date.addDays(distance),
                reference_date.addDays(-distance),
            ):
                if (
                    candidate.isValid()
                    and minimum <= candidate <= maximum
                    and not self._is_disabled_date(candidate)
                ):
                    return candidate
        return reference_date

    def restore_enabled_selection(self):
        selected = self.selectedDate()
        if self._is_disabled_date(selected):
            self.blockSignals(True)
            fallback = self._last_enabled_date
            if self._is_disabled_date(fallback):
                fallback = self._nearest_enabled_date(selected)
            self.setSelectedDate(fallback)
            self.blockSignals(False)
            return
        self._last_enabled_date = selected

    def _apply_disabled_date_formats(self):
        for disabled_date in self._holiday_dates | self._custom_disabled_dates:
            disabled_format = QTextCharFormat()
            disabled_format.setForeground(QColor("#94A3B8"))
            if disabled_date in self._holiday_dates:
                disabled_format.setBackground(QColor("#E2E8F0"))
                holiday_type = self._holiday_types.get(
                    disabled_date, "official"
                )
                tooltip = (
                    "عطلة رسمية" if holiday_type == "official"
                    else "غياب طارئ غير رسمي"
                ) + " — لا يمكن اختيار هذا اليوم"
            else:
                disabled_format.setBackground(
                    self._custom_disabled_background_color
                )
                tooltip = self._custom_disabled_tooltip
            disabled_format.setToolTip(tooltip)
            self.setDateTextFormat(disabled_date, disabled_format)

    def refresh_recorded_dates(self):
        try:
            self.setDateTextFormat(QDate(), QTextCharFormat())
            year_id = getattr(self, "year_id", self.db.year_id)
            with self.db.connect() as con:
                cursor = con.cursor()
                cursor.execute("""
                    SELECT DISTINCT d.date 
                    FROM day_data d
                    JOIN hessa h ON h.day_data_id = d.id
                    WHERE d.ann_scolaire_id = ?
                    """, (year_id,))
                rows = cursor.fetchall()
                incomplete_dates = self.db.incomplete_workday_dates(year_id)
                recorded_format = QTextCharFormat()
                recorded_format.setBackground(QColor("#D4EDDA"))
                recorded_format.setForeground(QColor("#155724"))
                incomplete_format = QTextCharFormat()
                incomplete_format.setBackground(QColor("#FEE2E2"))
                incomplete_format.setForeground(QColor("#991B1B"))
                incomplete_format.setToolTip("يحتوي هذا اليوم على حصة غير مكتملة")
                for row in rows:
                    if row[0]:
                        qd = QDate.fromString(row[0], "yyyy-MM-dd")
                        if qd.isValid():
                            self.setDateTextFormat(
                                qd,
                                incomplete_format
                                if row[0] in incomplete_dates else recorded_format,
                            )
            self._apply_disabled_date_formats()
        except Exception as e:
            print(f"Error loading recorded dates: {e}")


class OfficialProgramsTreeWidget(QWidget):
    def __init__(
        self, db, level_id, level_name, majal_id=None, majal_name="",
        parent=None, activity_name=None, embedded=False
    ):
        super().__init__(parent, Qt.Widget if embedded else Qt.Window)
        self.db = db
        self.level_id = level_id
        self.majal_id = majal_id
        self.level_name = level_name
        self.majal_name = majal_name
        self.activity_name = activity_name
        self.setObjectName("officialProgramsTreeDialog")
        self.setWindowTitle("شجرة البرامج الرسمية")
        self.setLayoutDirection(Qt.RightToLeft)
        if not embedded:
            self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        self.info_label = QLabel()
        self.info_label.setObjectName("officialTreeInfo")
        self._update_info_label()
        layout.addWidget(self.info_label)

        self.tree = QTreeWidget()
        self.tree.setObjectName("officialProgramsTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setAnimated(True)
        self.tree.setIndentation(26)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 56)
        layout.addWidget(self.tree, 1)

        self.status_label = QLabel("اضغط أيقونة النسخ بجانب العنصر المطلوب.")
        self.status_label.setObjectName("officialTreeStatus")
        layout.addWidget(self.status_label)
        self.refresh_tree()

    def _update_info_label(self):
        scope = f"المستوى: {self.level_name or '—'}"
        if self.majal_id:
            scope += f"    |    المجال: {self.majal_name or '—'}"
        if self.activity_name:
            scope += f"    |    النشاط: {self.activity_name}"
        self.info_label.setText(scope)

    def refresh_tree(self):
        self._update_info_label()
        if not self.level_id:
            self.tree.clear()
            self.status_label.setText("اختر المستوى والمجال والنشاط لعرض البرامج الرسمية.")
            return
        query = """
            SELECT mj.name, cmj.id, cmj.competence,
                cm.id, cm.matiere, cm.competence,
                mk.id, mk.competence,
                os.id, os.objectif_specifique,
                cnt.id, cnt.content
            FROM competence_majal cmj
            JOIN majal mj ON mj.id=cmj.id_majal
            LEFT JOIN competence_matiere cm
                ON cm.id_competence_majal=cmj.id
            LEFT JOIN moukawan_kifaya mk
                ON mk.id_competence_matiere=cm.id
            LEFT JOIN objectif_specifique os
                ON os.id_moukawa_kifaya=mk.id
            LEFT JOIN content cnt
                ON cnt.id_objectif_specifique=os.id
            WHERE cmj.id_level=?
        """
        params = [self.level_id]
        if self.majal_id:
            query += " AND cmj.id_majal=?"
            params.append(self.majal_id)
        if self.activity_name:
            query += " AND cm.matiere=?"
            params.append(self.activity_name)
        query += """
            ORDER BY mj.name, cmj.id, cm.matiere, cm.id,
                mk.id, os.id, cnt.id
        """

        with self.db.connect() as con:
            rows = con.execute(query, params).fetchall()

        self.tree.clear()
        domain_items = {}
        activity_items = {}
        component_items = {}
        objective_items = {}

        for row in rows:
            (
                domain_name, domain_competence_id, domain_competence,
                activity_id, activity_name, activity_competence,
                component_id, component_text,
                objective_id, objective_text,
                content_id, content_text
            ) = row

            domain_item = domain_items.get(domain_competence_id)
            if domain_item is None:
                domain_item = self._create_tree_item(
                    self.tree.invisibleRootItem(),
                    f"المجال: {domain_name} — كفاية المجال: {domain_competence}"
                )
                domain_items[domain_competence_id] = domain_item

            if activity_id is None:
                continue
            activity_item = activity_items.get(activity_id)
            if activity_item is None:
                activity_item = self._create_tree_item(
                    domain_item,
                    f"النشاط: {activity_name} — كفاية النشاط: {activity_competence}"
                )
                activity_items[activity_id] = activity_item

            if component_id is None:
                continue
            component_item = component_items.get(component_id)
            if component_item is None:
                component_item = self._create_tree_item(activity_item, component_text)
                component_items[component_id] = component_item

            if objective_id is None:
                continue
            objective_item = objective_items.get(objective_id)
            if objective_item is None:
                objective_item = self._create_tree_item(component_item, objective_text)
                objective_items[objective_id] = objective_item

            if content_id is not None:
                self._create_tree_item(objective_item, content_text)

        self.tree.expandToDepth(1)
        if not rows:
            self.status_label.setText("لا توجد برامج رسمية مسجلة ضمن التحديد الحالي.")
        else:
            self.status_label.setText("اضغط أيقونة النسخ بجانب أي مجال أو كفاية أو هدف أو محتوى لنسخه.")

    def _create_tree_item(self, parent, text):
        text = str(text or "")
        item = QTreeWidgetItem(parent, [text, ""])
        item.setData(0, Qt.UserRole, text)
        item.setToolTip(0, text)

        copy_button = QToolButton(self.tree)
        copy_button.setObjectName("officialTreeCopyButton")
        copy_button.setText("")
        copy_button.setProperty("actionType", "copy_paste")
        copy_button.setToolTip("نسخ النص")
        copy_button.setAutoRaise(True)
        copy_button.setFixedWidth(44)
        copy_button.setMaximumWidth(48)
        copy_button.clicked.connect(lambda _checked=False, value=text: self.copy_text(value))
        self.tree.setItemWidget(item, 1, copy_button)
        return item

    def copy_text(self, text):
        QApplication.clipboard().setText(text)
        self.status_label.setText("تم نسخ النص إلى الحافظة.")


class OfficialProgramsBrowsePage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setLayoutDirection(Qt.RightToLeft)
        self.setObjectName("officialProgramsBrowsePage")
        style = self.style()
        self._folder_icon = style.standardIcon(
            QStyle.StandardPixmap.SP_DirIcon
        )
        self._file_icon = style.standardIcon(
            QStyle.StandardPixmap.SP_FileIcon
        )

        splitter = QSplitter(Qt.Horizontal, self)
        self.splitter = splitter
        splitter.setObjectName("officialProgramsBrowseSplitter")
        splitter.setLayoutDirection(Qt.LeftToRight)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        self._initial_tree_width_set = False
        self._levels_loaded = False

        self.details_panel = QWidget()
        self.details_panel.setObjectName("officialProgramsDetailsPanel")
        self.details_panel.setLayoutDirection(Qt.RightToLeft)
        details_layout = QVBoxLayout(self.details_panel)
        self.details_title = QLabel("تفاصيل الهدف المميز ومحتوياته")
        self.details_title.setObjectName("officialProgramsDetailsTitle")
        details_layout.addWidget(self.details_title)

        self.details_scroll = QScrollArea()
        self.details_scroll.setObjectName("officialProgramsDetailsScroll")
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.details_container = QWidget()
        self.details_container.setObjectName(
            "officialProgramsDetailsContainer"
        )
        self.details_container.setLayoutDirection(Qt.RightToLeft)
        self.details_layout = QVBoxLayout(self.details_container)
        self.details_layout.setContentsMargins(8, 8, 8, 8)
        self.details_layout.setSpacing(12)
        self.details_scroll.setWidget(self.details_container)
        details_layout.addWidget(self.details_scroll, 1)
        splitter.addWidget(self.details_panel)

        self.tree_panel = QWidget()
        self.tree_panel.setObjectName("officialProgramsTreePanel")
        self.tree_panel.setLayoutDirection(Qt.RightToLeft)
        tree_layout = QVBoxLayout(self.tree_panel)
        tree_layout.setContentsMargins(8, 8, 8, 8)
        tree_layout.setSpacing(6)
        self.tree_title = QLabel("المستويات والبرامج الرسمية")
        self.tree_title.setObjectName("officialProgramsTreeTitle")
        self.tree_title.setAlignment(Qt.AlignCenter)
        tree_layout.addWidget(self.tree_title)
        self.tree = QTreeWidget()
        self.tree.setObjectName("officialProgramsBrowseTree")
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setAnimated(True)
        self.tree.setIndentation(22)
        self.tree.itemSelectionChanged.connect(
            self.on_tree_selection_changed
        )
        tree_layout.addWidget(self.tree, 1)
        splitter.addWidget(self.tree_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1, 1])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter, 1)
        self._show_details_placeholder(
            "اختر هدفًا مميزًا من الشجرة لعرض بياناته ومحتوياته."
        )

    def showEvent(self, event):
        super().showEvent(event)
        if self._levels_loaded and not self._initial_tree_width_set:
            QTimer.singleShot(0, self._set_initial_tree_width)

    def _set_initial_tree_width(self):
        if self._initial_tree_width_set:
            return
        available_width = self.splitter.width()
        if available_width <= self.splitter.handleWidth():
            return

        objective_widths = []
        for level_index in range(self.tree.topLevelItemCount()):
            level_item = self.tree.topLevelItem(level_index)
            for objective_item in self._descendant_items(level_item):
                record = objective_item.data(0, Qt.UserRole)
                if not isinstance(record, dict) or record.get("type") != "objective":
                    continue
                words = str(record.get("objective") or "").split()
                if words:
                    objective_widths.append(
                        self.tree.fontMetrics().horizontalAdvance(
                            " ".join(words[:7])
                        )
                    )

        if objective_widths:
            objective_widths.sort()
            text_width = objective_widths[len(objective_widths) // 2]
        else:
            text_width = self.tree.fontMetrics().horizontalAdvance(
                " ".join(["الهدف"] * 7)
            )
        hierarchy_indent = self.tree.indentation() * 4
        tree_width = text_width + hierarchy_indent + 56
        tree_width = min(tree_width, available_width - self.splitter.handleWidth())
        details_width = available_width - tree_width - self.splitter.handleWidth()
        if details_width <= 0:
            return
        self.splitter.setSizes([details_width, tree_width])
        self._initial_tree_width_set = True

    @staticmethod
    def _descendant_items(item):
        for index in range(item.childCount()):
            child = item.child(index)
            yield child
            yield from OfficialProgramsBrowsePage._descendant_items(child)

    def load_levels(self):
        if getattr(self, "_active_background_task", None) is not None:
            return False
        self.tree.clear()
        self._show_details_placeholder(
            "اختر هدفًا مميزًا من الشجرة لعرض بياناته ومحتوياته."
        )
        return start_background_task(
            self,
            self._fetch_tree_rows,
            self._populate_tree,
            self._show_tree_load_error,
            keep_overlay_during_success=True,
        )

    def _fetch_tree_rows(self):
        with self.db.connect() as con:
            return con.execute(
                """SELECT l.id, l.name,
                          cmj.id, mj.name, cmj.competence,
                          cm.id, cm.matiere, cm.competence,
                          mk.id, mk.competence,
                          os.id, os.objectif_specifique, os.description
                   FROM level l
                   LEFT JOIN competence_majal cmj
                     ON cmj.id_level=l.id
                   LEFT JOIN majal mj ON mj.id=cmj.id_majal
                   LEFT JOIN competence_matiere cm
                     ON cm.id_competence_majal=cmj.id
                   LEFT JOIN moukawan_kifaya mk
                     ON mk.id_competence_matiere=cm.id
                   LEFT JOIN objectif_specifique os
                     ON os.id_moukawa_kifaya=mk.id
                   ORDER BY l.id, mj.name, cm.matiere, cm.id,
                            mk.id, os.id"""
            ).fetchall()

    def _populate_tree(self, rows):
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        try:
            level_items = {}
            domain_items = {}
            activity_items = {}
            component_items = {}
            for row in rows:
                (
                    level_id, level_name,
                    domain_id, domain_name, domain_competence,
                    activity_id, activity_name, activity_competence,
                    component_id, component_text,
                    objective_id, objective_text, objective_description,
                ) = row

                level_item = level_items.get(level_id)
                if level_item is None:
                    level_item = QTreeWidgetItem([str(level_name or "")])
                    level_item.setData(0, Qt.UserRole, {"type": "level"})
                    self._set_folder_icon(level_item)
                    level_items[level_id] = level_item
                    self.tree.addTopLevelItem(level_item)

                if domain_id is None:
                    continue
                domain_item = domain_items.get(domain_id)
                if domain_item is None:
                    domain_item = QTreeWidgetItem([
                        str(domain_name or "")
                    ])
                    domain_item.setToolTip(
                        0, f"كفاية المجال: {domain_competence or '—'}"
                    )
                    self._set_folder_icon(domain_item)
                    domain_items[domain_id] = domain_item
                    level_item.addChild(domain_item)

                if activity_id is None:
                    continue
                activity_item = activity_items.get(activity_id)
                if activity_item is None:
                    activity_item = QTreeWidgetItem([
                        str(activity_name or "")
                    ])
                    activity_item.setToolTip(
                        0, f"كفاية النشاط: {activity_competence or '—'}"
                    )
                    self._set_folder_icon(activity_item)
                    activity_items[activity_id] = activity_item
                    domain_item.addChild(activity_item)

                if component_id is None:
                    continue
                component_item = component_items.get(component_id)
                if component_item is None:
                    component_item = QTreeWidgetItem(
                        [str(component_text or "")]
                    )
                    self._set_folder_icon(component_item)
                    component_items[component_id] = component_item
                    activity_item.addChild(component_item)

                if objective_id is None:
                    continue
                objective_item = QTreeWidgetItem(
                    [str(objective_text or "")]
                )
                objective_item.setIcon(0, self._file_icon)
                objective_item.setData(0, Qt.UserRole, {
                    "type": "objective",
                    "id": objective_id,
                    "level": level_name,
                    "domain": domain_name,
                    "activity": activity_name,
                    "component": component_text,
                    "objective": objective_text,
                    "description": objective_description or "",
                })
                component_item.addChild(objective_item)
            self.tree.setCurrentItem(None)
            self.tree.collapseAll()
            for index in range(self.tree.topLevelItemCount()):
                self._collapse_tree_item(self.tree.topLevelItem(index))
            self._levels_loaded = True
            if self.isVisible() and not self._initial_tree_width_set:
                QTimer.singleShot(0, self._set_initial_tree_width)
        finally:
            self.tree.blockSignals(False)
            self.tree.setUpdatesEnabled(True)
            self.tree.viewport().update()

    def _show_tree_load_error(self, error):
        self.tree.clear()
        self._levels_loaded = False
        message = error.strip().splitlines()[-1] if error.strip() else error
        QMessageBox.critical(
            self, "تعذر تحميل البرامج الرسمية",
            f"تعذر تحميل شجرة البرامج الرسمية:\n{message}"
        )

    @staticmethod
    def _collapse_tree_item(item):
        item.setExpanded(False)
        for index in range(item.childCount()):
            OfficialProgramsBrowsePage._collapse_tree_item(
                item.child(index)
            )

    def _set_folder_icon(self, item):
        item.setIcon(0, self._folder_icon)

    def on_tree_selection_changed(self):
        current = self.tree.currentItem()
        record = current.data(0, Qt.UserRole) if current else None
        if not isinstance(record, dict) or record.get("type") != "objective":
            self._show_details_placeholder(
                "اختر هدفًا مميزًا من الشجرة لعرض بياناته ومحتوياته."
            )
            return
        try:
            with self.db.connect() as con:
                rows = con.execute(
                    """SELECT content, description
                       FROM content
                       WHERE id_objectif_specifique=?
                       ORDER BY id""",
                    (record["id"],),
                ).fetchall()
        except sqlite3.Error as exc:
            QMessageBox.critical(
                self, "تعذر تحميل المحتويات",
                f"تعذر تحميل محتويات الهدف المحدد:\n{exc}"
            )
            self._show_details_placeholder(
                "تعذر تحميل بيانات الهدف ومحتوياته."
            )
            return

        self._clear_details()
        objective_fields = self._non_empty_detail_fields((
            ("نص الهدف المميز", record["objective"]),
            ("الخصائص / الملاحظات", record["description"]),
        ))
        objective_copy_text = str(record["objective"] or "")
        self.details_layout.addWidget(
            self._create_detail_card(
                "بطاقة الهدف المميز", objective_fields,
                "officialProgramsObjectiveCard",
                objective_copy_text,
            )
        )
        if not rows:
            empty_contents = QLabel("لا توجد محتويات مسجلة لهذا الهدف.")
            empty_contents.setObjectName("officialProgramsEmptyContents")
            empty_contents.setWordWrap(True)
            self.details_layout.addWidget(empty_contents)
        else:
            for index, (content_text, description) in enumerate(
                rows, start=1
            ):
                content_fields = self._non_empty_detail_fields((
                    ("نص المحتوى", content_text),
                    ("الخصائص / الملاحظات", description),
                ))
                self.details_layout.addWidget(
                    self._create_detail_card(
                        f"المحتوى {index}",
                        content_fields,
                        "officialProgramsContentCard",
                        str(content_text or ""),
                    )
                )
        self.details_layout.addStretch(1)

    @staticmethod
    def _non_empty_detail_fields(fields):
        return tuple(
            (name, value)
            for name, value in fields
            if value is not None and str(value).strip()
        )

    def _create_detail_card(self, title, fields, object_name, copy_text):
        card = QFrame()
        card.setObjectName(object_name)
        card.setLayoutDirection(Qt.RightToLeft)
        card.setStyleSheet(
            f"QFrame#{object_name} {{"
            "background-color: #F8FAFC;"
            "border: 2px solid #22C55E;"
            "border-radius: 12px;"
            "}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.setSpacing(8)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName(f"{object_name}Title")
        title_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_label.setStyleSheet(
            "font-weight: bold; color: #16A34A; border: none;"
            "background: transparent; font-size: 10pt;"
        )
        title_label.setWordWrap(True)
        header_layout.addStretch(1)
        header_layout.addWidget(title_label)
        copy_button = QToolButton(card)
        copy_button.setObjectName(f"{object_name}CopyButton")
        copy_button.setToolTip("نسخ بيانات البطاقة")
        copy_button.setAutoRaise(True)
        copy_button.setFixedSize(26, 26)
        copy_button.setIconSize(QSize(12, 12))
        set_card_action_type(copy_button, "copy")
        copy_button.clicked.connect(
            lambda _checked=False, value=copy_text: (
                QApplication.clipboard().setText(value)
            )
        )
        header_layout.addWidget(copy_button)
        card_layout.addLayout(header_layout)

        fields_layout = QGridLayout()
        fields_layout.setContentsMargins(0, 2, 0, 0)
        fields_layout.setHorizontalSpacing(8)
        fields_layout.setVerticalSpacing(6)
        metadata_count = (
            min(4, len(fields))
            if object_name.endswith("ObjectiveCard")
            else 0
        )
        for index, (field_name, field_value) in enumerate(fields):
            field_card = self._create_detail_field(
                field_name,
                field_value,
                object_name,
                highlight=field_name == "نص الهدف المميز",
            )
            if index < metadata_count:
                row, column = divmod(index, 2)
                fields_layout.addWidget(field_card, row, column)
            else:
                fields_layout.addWidget(
                    field_card, fields_layout.rowCount(), 0, 1, 2
                )
        card_layout.addLayout(fields_layout)
        return card

    @staticmethod
    def _create_detail_field(
        field_name, field_value, object_name, highlight=False
    ):
        field = QFrame()
        field.setObjectName(f"{object_name}Field")
        field.setLayoutDirection(Qt.RightToLeft)
        if highlight:
            field.setStyleSheet(
                f"QFrame#{object_name}Field {{"
                "background-color: #EFF6FF;"
                "border: 1px solid #BFDBFE;"
                "border-radius: 8px;"
                "}"
            )
        else:
            field.setStyleSheet(
                f"QFrame#{object_name}Field {{"
                "background-color: #FFFFFF;"
                "border: 1px solid #E2E8F0;"
                "border-radius: 8px;"
                "}"
            )
        field_layout = QVBoxLayout(field)
        field_layout.setContentsMargins(10, 6, 10, 7)
        field_layout.setSpacing(3)

        label = QLabel(f"{field_name}:")
        label.setObjectName(f"{object_name}FieldLabel")
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setStyleSheet(
            "background: transparent; border: none;"
            "color: #22C55E; font-size: 8pt; font-weight: 700;"
        )
        value = QLabel(str(field_value or ""))
        value.setObjectName(f"{object_name}Value")
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        value.setStyleSheet(
            "background: transparent; border: none;"
            f"color: {'#1D4ED8' if highlight else '#0F172A'};"
            "font-size: 9pt; font-weight: 700;"
        )
        field_layout.addWidget(label)
        field_layout.addWidget(value)
        return field

    def _clear_details(self):
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_details_placeholder(self, text):
        self._clear_details()
        placeholder = QLabel(text)
        placeholder.setObjectName("officialProgramsDetailsPlaceholder")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setWordWrap(True)
        self.details_layout.addWidget(placeholder)


class CompetencesCbaBrowsePage(QWidget):
    """صفحة تصفح المفاهيم المتصلة بالمقاربة بالكفايات.

    شجرة تعرض المفاهيم (الاسم ثم المحتوى كطفل)،
    وأمام كل عنصر زر نسخ صغير ينسخ صيغة:
        الاسم:
        <المحتوى>
    """

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setLayoutDirection(Qt.RightToLeft)
        self.setObjectName("competencesCbaBrowsePage")

        root_layout = QVBoxLayout(self)
        self.page_stack = QStackedWidget(self)
        root_layout.addWidget(self.page_stack)

        self.browse_page = QWidget()
        layout = QVBoxLayout(self.browse_page)
        browse_hint = QLabel("لاستعراض العنصر ومحتواه، انقر عليه مرتين متتاليتين.")
        browse_hint.setObjectName("competencesCbaBrowseHint")
        browse_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(browse_hint)

        self.tree = QTreeWidget()
        self.tree.setObjectName("competencesCbaTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setAnimated(True)
        self.tree.setIndentation(26)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 56)
        self.tree.itemDoubleClicked.connect(self._show_concept_for_item)
        layout.addWidget(self.tree, 1)

        self.status_label = QLabel("اضغط أيقونة النسخ بجانب أي مفهوم لنسخه.")
        self.status_label.setObjectName("competencesCbaStatus")
        layout.addWidget(self.status_label)
        self.page_stack.addWidget(self.browse_page)

        self.details_page = QWidget()
        details_layout = QVBoxLayout(self.details_page)
        self.details_name_label = QLabel()
        self.details_name_label.setAlignment(Qt.AlignCenter)
        self.details_name_label.setWordWrap(True)
        self.details_name_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #1E40AF; padding: 10px;"
        )
        details_layout.addWidget(self.details_name_label)

        self.details_content_edit = QTextEdit()
        self.details_content_edit.setReadOnly(True)
        self.details_content_edit.setObjectName("conceptDetailsContent")
        details_layout.addWidget(self.details_content_edit, 1)

        self.details_status_label = QLabel()
        self.details_status_label.setAlignment(Qt.AlignCenter)
        details_layout.addWidget(self.details_status_label)

        details_buttons = QHBoxLayout()
        details_buttons.addStretch()
        self.details_copy_button = QPushButton("نسخ المحتوى")
        self.details_copy_button.setProperty("actionType", "copy_paste")
        self.details_copy_button.clicked.connect(self.copy_details_content)
        details_buttons.addWidget(self.details_copy_button)
        self.details_back_button = QPushButton("العودة")
        self.details_back_button.setProperty("actionType", "back")
        self.details_back_button.clicked.connect(
            lambda: self.page_stack.setCurrentWidget(self.browse_page)
        )
        details_buttons.addWidget(self.details_back_button)
        details_buttons.addStretch()
        details_layout.addLayout(details_buttons)
        self.page_stack.addWidget(self.details_page)

        self._all_concepts = []
        self.load_concepts()

    def load_concepts(self):
        try:
            with self.db.connect() as con:
                concepts = con.execute(
                    "SELECT id, name, content FROM concept ORDER BY name COLLATE NOCASE"
                ).fetchall()
        except sqlite3.Error as exc:
            self._all_concepts = []
            QMessageBox.critical(
                self, "تعذر تحميل المفاهيم",
                f"تعذر تحميل المفاهيم من قاعدة البيانات:\n{exc}"
            )
        else:
            self._all_concepts = concepts
        self.refresh_tree()

    def refresh_tree(self, *_args):
        self.tree.clear()
        for _concept_id, name, content in self._all_concepts:
            concept_item = self._create_tree_item(
                self.tree.invisibleRootItem(), f"{name or ''}",
                name, content, self._copy_payload(name, content),
            )
            self._create_tree_item(
                concept_item, content or "—",
                name, content, self._copy_payload(name, content),
            )
        self.tree.expandToDepth(1)
        total = len(self._all_concepts)
        if not total:
            self.status_label.setText(
                "لا توجد مفاهيم مسجلة بعد. استخدم Ctrl+Shift+R لإضافة مفاهيم."
            )
        else:
            self.status_label.setText(
                f"عرض {total} مفهوم. اضغط أيقونة النسخ بجانب أي عنصر لنسخه."
            )

    @staticmethod
    def _copy_payload(name, content):
        return f"الاسم: {name or ''}\nالمحتوى: {content or ''}"

    def _create_tree_item(self, parent, text, name, content, copy_text):
        text = str(text or "")
        item = QTreeWidgetItem(parent, [text, ""])
        item.setData(0, Qt.UserRole, copy_text)
        item.setData(0, Qt.UserRole + 1, (name or "", content or ""))
        item.setToolTip(0, text)

        usable_width = max(
            120, self.tree.viewport().width() - self.tree.indentation() - 80
        )
        wrapped_height = _wrapped_text_height(text, usable_width, self.tree.font())
        item.setSizeHint(0, QSize(0, wrapped_height))

        copy_button = QToolButton(self.tree)
        copy_button.setObjectName("officialTreeCopyButton")
        copy_button.setText("")
        copy_button.setProperty("actionType", "copy_paste")
        copy_button.setToolTip("نسخ النص")
        copy_button.setAutoRaise(True)
        copy_button.setFixedSize(28, 28)
        copy_button.setIconSize(QSize(16, 16))
        copy_button.setMaximumWidth(48)
        copy_button.clicked.connect(
            lambda _checked=False, value=copy_text: self.copy_text(value)
        )
        self.tree.setItemWidget(item, 1, copy_button)
        return item

    def _show_concept_for_item(self, item, _column):
        name, content = item.data(0, Qt.UserRole + 1)
        self.show_concept_details(name, content)

    def show_concept_details(self, name, content):
        self.details_name_label.setText(str(name or ""))
        self.details_content_edit.setPlainText(str(content or ""))
        self.details_status_label.clear()
        self.page_stack.setCurrentWidget(self.details_page)

    def copy_details_content(self):
        QApplication.clipboard().setText(self.details_content_edit.toPlainText())
        self.details_status_label.setText("تم نسخ المحتوى إلى الحافظة.")

    def copy_text(self, text):
        QApplication.clipboard().setText(text)
        self.status_label.setText("تم نسخ النص إلى الحافظة.")

class DayBrowseCalendar(CustomCalendarWidget):
    def __init__(self, db, year_id, parent=None):
        self.year_id = year_id
        super().__init__(db, parent)
        self.currentPageChanged.connect(self.refresh_recorded_dates)

    def refresh_recorded_dates(self, *_args):
        try:
            with self.db.connect() as con:
                rows = con.execute("""
                    SELECT DISTINCT d.date
                    FROM day_data d
                    WHERE d.ann_scolaire_id=?
                        AND (
                            EXISTS (
                                SELECT 1 FROM hessa h
                                WHERE h.day_data_id=d.id
                            )
                            OR EXISTS (
                                SELECT 1
                                FROM cultural_club_daily_session club_session
                                WHERE club_session.ann_scolaire_id=
                                    d.ann_scolaire_id
                                    AND club_session.session_date=d.date
                            )
                        )
                """, (self.year_id,)).fetchall()
            self.recorded_dates = {row[0] for row in rows}
            incomplete_dates = self.db.incomplete_workday_dates(self.year_id)

            self.setDateTextFormat(QDate(), QTextCharFormat())
            first_day = QDate(self.yearShown(), self.monthShown(), 1)
            day_count = first_day.daysInMonth()
            unrecorded_format = QTextCharFormat()
            unrecorded_format.setForeground(QColor("#94A3B8"))
            recorded_format = QTextCharFormat()
            recorded_format.setBackground(QColor("#D4EDDA"))
            recorded_format.setForeground(QColor("#155724"))
            incomplete_format = QTextCharFormat()
            incomplete_format.setBackground(QColor("#FEE2E2"))
            incomplete_format.setForeground(QColor("#991B1B"))
            incomplete_format.setToolTip(
                "يحتوي هذا اليوم على حصة غير مكتملة"
            )
            for day_number in range(1, day_count + 1):
                date_value = QDate(self.yearShown(), self.monthShown(), day_number)
                day_text = date_value.toString("yyyy-MM-dd")
                if day_text in incomplete_dates:
                    self.setDateTextFormat(date_value, incomplete_format)
                elif day_text in self.recorded_dates:
                    self.setDateTextFormat(date_value, recorded_format)
                else:
                    self.setDateTextFormat(date_value, unrecorded_format)
        except sqlite3.Error as exc:
            raise RuntimeError(f"تعذر تحميل الأيام المسجلة: {exc}") from exc


class DayLessonsBrowsePage(QWidget):
    def __init__(self, db, day_id=None, day_text=None, parent=None, on_back=None):
        super().__init__(parent)
        self.db = db
        self.day_id = day_id
        self.day_year_id = db.year_id
        self.day_text = day_text or QDate.currentDate().toString("yyyy-MM-dd")
        self.on_back = on_back
        self.setObjectName("dayLessonsBrowsePage")
        self.setWindowTitle("عرض الأيام المسجلة")
        self.setLayoutDirection(Qt.RightToLeft)
        self._changing_date = False
        self._compact_layout = None
        self._compact_card_padding_layouts = []
        self._lesson_metadata_views = []
        self._teacher_info_popup = None
        self._day_ids_by_year_date = {}
        self._day_tree_items = {}
        self._recorded_days = self._get_recorded_days()
        if day_id is not None:
            self.day_year_id = next(
                (
                    year_id for (year_id, _day_text), recorded_day_id
                    in self._day_ids_by_year_date.items()
                    if recorded_day_id == day_id
                ),
                self.day_year_id,
            )

        layout = QVBoxLayout(self)
        agenda_row = QHBoxLayout()
        agenda_row.addWidget(QLabel("اليوم:"))
        self.date_edit = QDateEdit()
        self.date_edit.setObjectName("dayLessonsDateEdit")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setReadOnly(False)
        self.date_edit.lineEdit().setReadOnly(True)
        self.date_edit.setDisplayFormat("dddd، dd/MM/yyyy")
        self.date_edit.setLocale(QLocale(QLocale.Arabic, QLocale.Tunisia))
        self.calendar = DayBrowseCalendar(self.db, self.day_year_id, self)
        self.calendar.setLocale(QLocale(QLocale.Arabic, QLocale.Tunisia))
        self.date_edit.setCalendarWidget(self.calendar)
        initial_date = QDate.fromString(self.day_text, "yyyy-MM-dd")
        initial_date = initial_date if initial_date.isValid() else QDate.currentDate()
        initial_date = self._set_school_year_date_range(
            initial_date, self.day_year_id
        )
        self.date_edit.setDate(initial_date)
        self.calendar.setSelectedDate(initial_date)
        self.calendar.clicked.connect(self.on_calendar_date_clicked)
        agenda_row.addWidget(self.date_edit)
        self.day_status = QLabel()
        self.day_status.setObjectName("dayLessonsStatus")
        agenda_row.addWidget(self.day_status, 1)
        layout.addLayout(agenda_row)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setObjectName("dayLessonsContentSplitter")
        content_splitter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        content_splitter.setChildrenCollapsible(False)
        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.school_info_card = QFrame()
        self.school_info_card.setObjectName("dayLessonsTeacherCard")
        self.school_info_card_layout = QVBoxLayout(self.school_info_card)
        self.school_info_card_layout.setContentsMargins(14, 14, 14, 14)
        self.school_info_card_layout.setSpacing(12)

        teacher_header = QFrame()
        teacher_header.setObjectName("dayLessonsTeacherHeader")
        teacher_header_layout = QHBoxLayout(teacher_header)
        teacher_header_layout.setContentsMargins(12, 12, 12, 12)
        teacher_icon = QLabel("♙")
        teacher_icon.setObjectName("dayLessonsTeacherIcon")
        teacher_header_layout.addWidget(teacher_icon)
        teacher_heading = QVBoxLayout()
        teacher_title = QLabel("بطاقة المعلم")
        teacher_title.setObjectName("dayLessonsTeacherTitle")
        self.teacher_subtitle = QLabel("بيانات السنة الدراسية المحددة")
        self.teacher_subtitle.setObjectName("dayLessonsTeacherSubtitle")
        self.teacher_subtitle.setWordWrap(True)
        teacher_heading.addWidget(teacher_title)
        teacher_heading.addWidget(self.teacher_subtitle)
        teacher_header_layout.addLayout(teacher_heading, 1)
        self.school_info_card_layout.addWidget(teacher_header)

        self.school_info_content = QWidget()
        self.school_info_content.setObjectName("dayLessonsTeacherDetails")
        self.school_info_content_layout = QVBoxLayout(
            self.school_info_content
        )
        self.school_info_content_layout.setContentsMargins(0, 0, 0, 0)
        self.school_info_content_layout.setSpacing(10)
        self.school_info_card_layout.addWidget(
            self.school_info_content, 1
        )

        self.school_info_scroll = QScrollArea()
        self.school_info_scroll.setObjectName("dayLessonsTeacherScroll")
        self.school_info_scroll.setWidgetResizable(True)
        self.school_info_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.school_info_scroll.setWidget(self.school_info_card)

        self.day_tree = QTreeWidget()
        self.day_tree.setObjectName("dayLessonsTree")
        self.day_tree.setHeaderHidden(True)
        self.day_tree.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.day_tree.setUniformRowHeights(True)
        self.day_tree.currentItemChanged.connect(
            self._on_day_tree_selection_changed
        )
        tree_panel = QFrame()
        tree_panel.setObjectName("dayLessonsTreePanel")
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(8, 8, 8, 8)
        tree_layout.setSpacing(6)
        tree_heading = QLabel("الأيام حسب السنة والشهر والأسبوع")
        tree_heading.setObjectName("dayLessonsTreeTitle")
        tree_heading.setAlignment(Qt.AlignCenter)
        tree_layout.addWidget(tree_heading)
        tree_layout.addWidget(self.day_tree, 1)
        info_panel.setObjectName("dayLessonsTeacherPanel")
        self.info_panel = info_panel
        self.info_layout = info_layout
        self.tree_panel = tree_panel
        self.tree_layout = tree_layout
        info_layout.addWidget(self.school_info_scroll, 1)

        self.lessons_scroll = QScrollArea()
        self.lessons_scroll.setObjectName("dayLessonsCardsScroll")
        self.lessons_scroll.setWidgetResizable(True)
        self.lessons_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.lessons_container = QWidget()
        self.lessons_layout = QVBoxLayout(self.lessons_container)
        self.lessons_layout.setContentsMargins(8, 8, 8, 8)
        self.lessons_layout.setSpacing(14)
        self.lessons_layout.addStretch(1)
        self.lessons_scroll.setWidget(self.lessons_container)
        lessons_panel = QWidget()
        lessons_panel.setObjectName("dayLessonsPanel")
        lessons_panel_layout = QVBoxLayout(lessons_panel)
        lessons_panel_layout.setContentsMargins(0, 0, 0, 0)
        lessons_panel_layout.setSpacing(8)
        lessons_panel_layout.addWidget(self.lessons_scroll, 1)

        self.print_button = QPushButton("طباعة")
        self.print_button.setObjectName("dayLessonsExportButton")
        self.print_button.setProperty("actionType", "print")
        self.print_button.clicked.connect(self.print_day)
        self.export_pdf_button = QPushButton("تصدير PDF")
        self.export_pdf_button.setObjectName("dayLessonsExportButton")
        self.export_pdf_button.setProperty("actionType", "export")
        self.export_pdf_button.clicked.connect(self.export_pdf)
        self.preview_pdf_button = QPushButton("عرض")
        self.preview_pdf_button.setObjectName("dayLessonsPreviewButton")
        self.preview_pdf_button.setProperty("actionType", "browse")
        self.preview_pdf_button.clicked.connect(self.preview_pdf)
        self.export_json_button = QPushButton("تصدير JSON")
        self.export_json_button.setObjectName("dayLessonsExportButton")
        self.export_json_button.setProperty("actionType", "export")
        self.export_json_button.clicked.connect(self.export_json)
        self.back_button = QPushButton("التصرف في الدفتر")
        self.back_button.setProperty("actionType", "back")
        if self.on_back:
            self.back_button.clicked.connect(self.on_back)
        self._action_button_labels = {
            self.print_button: "طباعة",
            self.preview_pdf_button: "عرض",
            self.export_pdf_button: "تصدير PDF",
            self.export_json_button: "تصدير JSON",
            self.back_button: "التصرف في الدفتر",
        }
        for button, label in self._action_button_labels.items():
            button.setAccessibleName(label)
            button.setToolTip(label)
        self.actions_container = QWidget(info_panel)
        self.actions_container.setObjectName("dayLessonsActionsContainer")
        self.action_buttons = QGridLayout(self.actions_container)
        self.action_buttons.setObjectName("dayLessonsActions")
        self.action_buttons.setContentsMargins(0, 0, 0, 0)
        self.action_buttons.setHorizontalSpacing(6)
        self.action_buttons.setVerticalSpacing(6)
        self._set_action_button_positions(compact=False)
        info_layout.addWidget(self.actions_container)

        content_splitter.addWidget(lessons_panel)
        content_splitter.addWidget(tree_panel)
        content_splitter.addWidget(info_panel)
        self.content_splitter = content_splitter
        content_splitter.setStretchFactor(0, 6)
        content_splitter.setStretchFactor(1, 2)
        content_splitter.setStretchFactor(2, 2)
        content_splitter.setSizes([850, 280, 300])
        layout.addWidget(content_splitter, 1)
        self.page_layout = layout
        self._compact_layout_timer = QTimer(self)
        self._compact_layout_timer.setSingleShot(True)
        self._compact_layout_timer.setInterval(120)
        self._compact_layout_timer.timeout.connect(
            self._update_compact_layout
        )

        self._update_school_info()
        self._populate_day_tree()
        day_item = self._day_tree_items.get(
            (self.day_year_id, self.day_text)
        )
        if day_item is not None:
            self._expand_day_tree_path(day_item)
            self.day_tree.blockSignals(True)
            self.day_tree.setCurrentItem(day_item)
            self.day_tree.blockSignals(False)
        if self.day_id and (
            self.db.lessons(self.day_id)
            or self.db.cultural_club_daily_sessions(
                self.day_text, year_id=self.day_year_id
            )
        ):
            self.load_lesson_cards()
        else:
            self.day_id = None
            self._clear_lesson_cards()
            self._set_day_available(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_compact_layout_timer"):
            self._compact_layout_timer.start()

    def _set_action_button_positions(self, compact):
        while self.action_buttons.count():
            self.action_buttons.takeAt(0)

        buttons = (
            self.print_button,
            self.preview_pdf_button,
            self.export_pdf_button,
            self.export_json_button,
            self.back_button,
        )
        if compact:
            for column, button in enumerate(buttons):
                button.setText("")
                button.setFixedSize(54, 44)
                self.action_buttons.addWidget(button, 0, column)
                self.action_buttons.setColumnStretch(column, 1)
            return

        for button, label in self._action_button_labels.items():
            button.setText(label)
            button.setMinimumSize(0, 0)
            button.setMaximumSize(16777215, 16777215)
        self.action_buttons.addWidget(self.print_button, 0, 0)
        self.action_buttons.addWidget(self.preview_pdf_button, 0, 1)
        self.action_buttons.addWidget(self.export_pdf_button, 1, 0)
        self.action_buttons.addWidget(self.export_json_button, 1, 1)
        self.action_buttons.addWidget(self.back_button, 2, 0, 1, 2)
        self.action_buttons.setColumnStretch(0, 1)
        self.action_buttons.setColumnStretch(1, 1)

    def _update_compact_layout(self):
        self.set_compact_mode(is_small_window(self))

    def set_compact_mode(self, compact):
        compact = bool(compact)
        if compact == self._compact_layout:
            return

        self._compact_layout = compact
        if compact:
            self.info_layout.removeWidget(self.actions_container)
            self.actions_container.setParent(self.tree_panel)
            self.tree_layout.addWidget(self.actions_container)
            self.info_panel.hide()
            self.content_splitter.setStretchFactor(0, 6)
            self.content_splitter.setStretchFactor(1, 4)
            self.content_splitter.setSizes([600, 400, 0])
        else:
            self.tree_layout.removeWidget(self.actions_container)
            self.actions_container.setParent(self.info_panel)
            self.info_layout.addWidget(self.actions_container)
            self.info_panel.show()
            self.content_splitter.setStretchFactor(0, 6)
            self.content_splitter.setStretchFactor(1, 2)
            self.content_splitter.setStretchFactor(2, 2)
            self.content_splitter.setSizes([850, 280, 300])

        self._set_action_button_positions(compact)
        self._set_lesson_metadata_compact(compact)
        self._set_compact_card_padding(compact)

    def _is_compact_layout(self):
        return self._compact_layout is True or (
            self._compact_layout is None and is_small_window(self)
        )

    def _register_card_padding_layout(self, layout, normal_margins):
        self._compact_card_padding_layouts.append(
            (layout, normal_margins)
        )
        if self._is_compact_layout():
            layout.setContentsMargins(3, 3, 3, 3)

    def _set_compact_card_padding(self, compact):
        for layout, normal_margins in self._compact_card_padding_layouts:
            if compact:
                layout.setContentsMargins(3, 3, 3, 3)
            else:
                layout.setContentsMargins(*normal_margins)

    def _set_lesson_metadata_compact(self, compact):
        for chips_widget, compact_card in self._lesson_metadata_views:
            chips_widget.setVisible(not compact)
            compact_card.setVisible(compact)

    def show_teacher_info_popup(self, anchor_widget):
        if self._teacher_info_popup is not None:
            self._teacher_info_popup.raise_()
            return

        window = self.window()
        popup = TeacherInfoPopup(window, self._restore_teacher_info_popup)
        popup.setObjectName("dayLessonsTeacherInfoPopup")
        popup.setLayoutDirection(Qt.RightToLeft)
        popup_layout = QVBoxLayout(popup)
        popup_layout.setContentsMargins(8, 8, 8, 8)
        self.info_layout.removeWidget(self.school_info_scroll)
        self.school_info_scroll.setParent(popup)
        popup_layout.addWidget(self.school_info_scroll)
        window_origin = window.mapToGlobal(QPoint(0, 0))
        window_right = window_origin.x() + window.width()
        window_bottom = window_origin.y() + window.height()
        anchor_origin = anchor_widget.mapToGlobal(QPoint(0, 0))
        popup_width = min(420, max(240, window.width() - 16))
        popup_y = anchor_origin.y() + anchor_widget.height()
        popup_height = max(120, window_bottom - popup_y)
        popup.resize(popup_width, popup_height)
        x = min(
            max(window_origin.x(), anchor_origin.x()),
            window_right - popup.width(),
        )
        popup.move(x, popup_y)
        self._teacher_info_popup = popup
        popup.show()

    def _restore_teacher_info_popup(self):
        popup = self._teacher_info_popup
        if popup is None:
            return
        self._teacher_info_popup = None
        self.school_info_scroll.setParent(self.info_panel)
        self.info_layout.insertWidget(0, self.school_info_scroll, 1)
        popup.deleteLater()

    def _get_recorded_days(self):
        days = []
        for year_id, year_name in self.db.school_years():
            for day_id, day_text in self.db.recorded_workdays(year_id):
                day_key = (year_id, str(day_text))
                self._day_ids_by_year_date.setdefault(day_key, day_id)
                days.append((year_id, str(year_name), day_id, str(day_text)))
        return days

    def _populate_day_tree(self):
        self.day_tree.clear()
        self._day_tree_items.clear()
        folder_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DirIcon
        )
        file_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileIcon
        )
        years = {}
        months = {}
        weeks = {}
        weekdays = (
            "الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس",
        )

        for year_id, year_name, day_id, day_text in self._recorded_days:
            day_date = QDate.fromString(day_text, "yyyy-MM-dd")
            if not day_date.isValid():
                continue
            year_node = years.get(year_id)
            if year_node is None:
                year_node = QTreeWidgetItem([str(year_name)])
                year_node.setIcon(0, folder_icon)
                self.day_tree.addTopLevelItem(year_node)
                years[year_id] = year_node

            month_key = (year_id, day_date.year(), day_date.month())
            month_node = months.get(month_key)
            if month_node is None:
                month_node = QTreeWidgetItem([
                    _arabic_month_name(day_text)
                ])
                month_node.setIcon(0, folder_icon)
                year_node.addChild(month_node)
                months[month_key] = month_node

            first_day = QDate(day_date.year(), day_date.month(), 1)
            week_number = (
                day_date.day() + first_day.dayOfWeek() - 2
            ) // 7 + 1
            week_key = (*month_key, week_number)
            week_node = weeks.get(week_key)
            if week_node is None:
                week_name = (
                    weekdays[week_number - 1]
                    if week_number <= len(weekdays)
                    else str(week_number)
                )
                week_node = QTreeWidgetItem([
                    f"الأسبوع {week_name}"
                ])
                week_node.setIcon(0, folder_icon)
                week_node.setData(
                    0, Qt.ItemDataRole.UserRole + 4, week_number
                )
                month_node.addChild(week_node)
                weeks[week_key] = week_node

            weekday_text = self.date_edit.locale().toString(
                day_date, "dddd"
            )
            day_node = QTreeWidgetItem([
                f"{weekday_text} — {day_date.toString('dd/MM/yyyy')}"
            ])
            day_node.setIcon(0, file_icon)
            day_node.setData(
                0, Qt.ItemDataRole.UserRole, "day"
            )
            day_node.setData(
                0, Qt.ItemDataRole.UserRole + 1, day_id
            )
            day_node.setData(
                0, Qt.ItemDataRole.UserRole + 2, year_id
            )
            day_node.setData(
                0, Qt.ItemDataRole.UserRole + 3, day_text
            )
            week_node.addChild(day_node)
            self._day_tree_items[(year_id, day_text)] = day_node

        for month_node in months.values():
            month_weeks = [
                month_node.child(index)
                for index in range(month_node.childCount())
            ]
            month_weeks.sort(
                key=lambda item: item.data(
                    0, Qt.ItemDataRole.UserRole + 4
                )
            )
            for index, week_node in enumerate(month_weeks):
                month_node.removeChild(week_node)
                month_node.insertChild(index, week_node)

        for week_node in weeks.values():
            children = [
                week_node.child(index)
                for index in range(week_node.childCount())
            ]
            children.sort(
                key=lambda item: item.data(
                    0, Qt.ItemDataRole.UserRole + 3
                ),
                reverse=True,
            )
            for index, child in enumerate(children):
                week_node.removeChild(child)
                week_node.insertChild(index, child)
        self.day_tree.collapseAll()

    @staticmethod
    def _expand_day_tree_path(item):
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

    def _on_day_tree_selection_changed(self, current, _previous):
        if (
            current is None
            or current.data(0, Qt.ItemDataRole.UserRole) != "day"
        ):
            self.day_id = None
            self._clear_lesson_cards()
            self._set_day_available(False)
            self.day_status.setText("اختر ملف يوم لعرض حصصه.")
            return
        day_id = current.data(0, Qt.ItemDataRole.UserRole + 1)
        year_id = current.data(0, Qt.ItemDataRole.UserRole + 2)
        day_text = current.data(0, Qt.ItemDataRole.UserRole + 3)
        self.set_day(day_id, day_text, year_id=year_id)

    def set_day(self, day_id, day_text, year_id=None):
        self.day_id = day_id
        self.day_text = day_text or QDate.currentDate().toString("yyyy-MM-dd")
        self.day_year_id = (
            year_id
            if year_id is not None
            else next(
                (
                    recorded_year_id
                    for (recorded_year_id, recorded_date), recorded_day_id
                    in self._day_ids_by_year_date.items()
                    if recorded_day_id == day_id
                    and recorded_date == self.day_text
                ),
                self.db.year_id,
            )
        )
        if self.day_id is None:
            self.day_id = self._day_ids_by_year_date.get(
                (self.day_year_id, self.day_text)
            )
        selected_date = QDate.fromString(self.day_text, "yyyy-MM-dd")
        if not selected_date.isValid():
            selected_date = QDate.currentDate()
        selected_date = self._set_school_year_date_range(
            selected_date, self.day_year_id
        )
        self.day_text = selected_date.toString("yyyy-MM-dd")
        self.date_edit.setDate(selected_date)
        self.calendar.year_id = self.day_year_id
        self.calendar.setSelectedDate(selected_date)
        self.calendar.setCurrentPage(selected_date.year(), selected_date.month())
        self.calendar.refresh_recorded_dates()
        tree_item = self._day_tree_items.get(
            (self.day_year_id, self.day_text)
        )
        if tree_item is not None and self.day_tree.currentItem() is not tree_item:
            self._expand_day_tree_path(tree_item)
            self.day_tree.blockSignals(True)
            self.day_tree.setCurrentItem(tree_item)
            self.day_tree.blockSignals(False)
        if self.day_id and (
            self.db.lessons(self.day_id)
            or self.db.cultural_club_daily_sessions(
                self.day_text, year_id=self.day_year_id
            )
        ):
            self.load_lesson_cards()
        else:
            self.day_id = None
            self._clear_lesson_cards()
            self._update_school_info()
            self._set_day_available(False)

    def _set_school_year_date_range(self, selected_date, year_id=None):
        school_info = self.db.school_info(year_id)
        if not school_info:
            raise ValueError("بيانات السنة الدراسية المحددة غير موجودة.")
        year_name = str(school_info[0] or "").strip()
        try:
            start_year_text, end_year_text = year_name.split("-", 1)
            start_year = int(start_year_text)
            end_year = int(end_year_text)
        except ValueError as error:
            raise ValueError(
                f"اسم السنة الدراسية غير صالح: {year_name}"
            ) from error
        if end_year != start_year + 1:
            raise ValueError(f"اسم السنة الدراسية غير صالح: {year_name}")

        first_day = QDate(start_year, 9, 1)
        last_day = QDate(end_year, 6, 30)
        self.date_edit.setDateRange(first_day, last_day)
        self.calendar.setDateRange(first_day, last_day)
        if selected_date < first_day:
            return first_day
        if selected_date > last_day:
            return last_day
        return selected_date

    def _update_school_info(self):
        school_info = self.db.school_info(self.day_year_id)
        values = school_info or ()
        self.school_info_card.setUpdatesEnabled(False)
        try:
            has_details = False
            while self.school_info_content_layout.count():
                item = self.school_info_content_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

            if not values:
                self.teacher_subtitle.setText(
                    "بيانات السنة الدراسية المحددة"
                )
                empty_label = QLabel("لا توجد بيانات متوفرة لهذه السنة.")
                empty_label.setObjectName("dayLessonsTeacherEmpty")
                empty_label.setWordWrap(True)
                self.school_info_content_layout.addWidget(empty_label)
                return
            self.teacher_subtitle.setText(
                f"السنة الدراسية: {str(values[0] or '—').strip()}"
            )
            school = dict(zip(SCHOOL_INFO_COLUMNS, values))
            groups = (
                ("المؤسسة", (
                    ("المندوبية الجهوية للتربية بـ", "delegation_regional_education"),
                    ("دائرة التفقد", "inspection_district"),
                    ("رمز المؤسسة", "school_code"),
                    ("هاتف المؤسسة", "school_phone"),
                    ("المؤسسة", "nom_ecole"),
                    ("عنوان المدرسة", "school_address"),
                    ("السنة الدراسية", "nom_annee"),
                )),
                ("الإطار الإداري والبيداغوجي", (
                    ("المتفقد", "nom_inspecteur"),
                    ("مدير المدرسة", "school_principal"),
                    ("اسم المساعد البيداغوجي", "nom_assistant_pedagogique"),
                    ("البريد الإلكتروني للمتفقد", "email_inspecteur"),
                    ("البريد الإلكتروني لمدير المدرسة", "email_school_principal"),
                    ("البريد الإلكتروني للمساعد البيداغوجي", "email_assistant_pedagogique"),
                )),
                ("البيانات الشخصية", (
                    ("المعلم", "nom_enseignant"),
                    ("المعرف الوحيد", "identifiant_unique"),
                    ("الشهادة العلمية", "diplomes_scientifiques"),
                    ("الشهادة التكوينية", "training_certificates"),
                    ("الهاتف", "telephone"),
                    ("البريد الإلكتروني", "email"),
                    ("الحالة العائلية", "situation_familiale"),
                    ("عدد الأطفال", "nombre_enfants"),
                    ("الجنس", "teacher_gender"),
                )),
                ("المسار الوظيفي", (
                    ("الرتبة", "grade"),
                    ("تاريخ الارتقاء إليها", "date_promotion"),
                    ("تاريخ الانتداب", "date_recrutement"),
                    ("تاريخ الترسيم", "date_titularisation"),
                )),
                ("التقييم والمتابعة", (
                    ("تاريخ الزيارة الأخيرة", "date_derniere_visite"),
                    ("العدد البيداغوجي المسند", "note_pedagogique"),
                    ("متفقد التقرير البيداغوجي", "inspecteur_rapport_pedagogique"),
                    ("اللغة", "langue"),
                    ("خلاصة تقرير الزيارة", "resume_rapport_visite"),
                )),
            )
            for title, field_specs in groups:
                fields = tuple(
                    (label, str(school.get(column) or "").strip())
                    for label, column in field_specs
                    if str(school.get(column) or "").strip()
                )
                if fields:
                    self.school_info_content_layout.addWidget(
                        self._teacher_info_value_card(title, fields)
                    )
                    has_details = True
            if not has_details:
                empty_label = QLabel(
                    "لا توجد تفاصيل مسجلة لهذه السنة الدراسية."
                )
                empty_label.setObjectName("dayLessonsTeacherEmpty")
                empty_label.setWordWrap(True)
                self.school_info_content_layout.addWidget(empty_label)
            self.school_info_content_layout.addStretch(1)
        finally:
            self.school_info_card.setUpdatesEnabled(True)

    @staticmethod
    def _teacher_info_value_card(title, fields):
        group = QFrame()
        group.setObjectName("dayLessonsTeacherGroup")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(10, 10, 10, 10)
        group_layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("dayLessonsTeacherGroupTitle")
        group_layout.addWidget(heading)

        for label_text, value_text in fields:
            if not value_text:
                continue
            row = QFrame()
            row.setObjectName("dayLessonsTeacherField")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(2)
            label = QLabel(label_text)
            label.setObjectName("dayLessonsTeacherFieldLabel")
            value = QLabel(value_text)
            value.setObjectName("dayLessonsTeacherFieldValue")
            value.setWordWrap(True)
            row_layout.addWidget(label)
            row_layout.addWidget(value)
            group_layout.addWidget(row)
        return group

    def _set_day_available(self, available):
        self.print_button.setEnabled(available)
        self.export_pdf_button.setEnabled(available)
        self.preview_pdf_button.setEnabled(available)
        self.export_json_button.setEnabled(available)
        self.day_status.setText(
            f"اليوم: {self.day_text}" if available else
            "لا توجد حصص أو جلسات نوادٍ مسجلة لهذا اليوم."
        )

    def _restore_calendar_selection(self, displayed_date):
        previous_date = QDate.fromString(self.day_text, "yyyy-MM-dd")
        if previous_date.isValid():
            self.calendar.setSelectedDate(previous_date)
            self.date_edit.setDate(previous_date)
        self.calendar.setCurrentPage(displayed_date.year(), displayed_date.month())

    def _reopen_calendar_popup(self):
        popup = self.calendar.window()
        popup.show()
        popup.raise_()

    def on_calendar_date_clicked(self, selected_date):
        selected_day = selected_date.toString("yyyy-MM-dd")
        if selected_day not in self.calendar.recorded_dates:
            self._restore_calendar_selection(selected_date)
            self.day_status.setText("هذا اليوم غير مسجل. اختر يوماً مميزاً في الأجندة.")
            QTimer.singleShot(0, self._reopen_calendar_popup)
            return

        try:
            day_id = self._day_ids_by_year_date.get(
                (self.day_year_id, selected_day)
            )
            if not day_id:
                self._restore_calendar_selection(selected_date)
                self.day_status.setText("هذا اليوم غير مسجل. اختر يوماً مميزاً في الأجندة.")
                QTimer.singleShot(0, self._reopen_calendar_popup)
                return
            self.set_day(
                day_id, selected_day, year_id=self.day_year_id
            )
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "تعذر تحميل اليوم", f"حدث خطأ أثناء تحميل الحصص:\n{exc}")

    def _clear_lesson_cards(self):
        self._compact_card_padding_layouts.clear()
        self._lesson_metadata_views.clear()
        while self.lessons_layout.count() > 1:
            item = self.lessons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def load_lesson_cards(self):
        self._clear_lesson_cards()
        cultural_clubs = self.db.cultural_clubs(self.day_year_id)
        group_labels = {
            group_key: group["level_label"]
            for group_key, group in self.db.class_groups().items()
        }
        with self.db.connect() as con:
            lessons = con.execute("""
                SELECT h.id, h.hessa_number,
                    COALESCE(g.group_key, c.name), m.name, h.heure,
                    h.time, h.wehda_number, lm.name
                FROM hessa h JOIN classe c ON c.id=h.classe_id
                LEFT JOIN class_group g ON g.id=h.class_group_id
                LEFT JOIN majal m ON m.id=h.majal_id
                LEFT JOIN learning_mode lm ON lm.id=h.learning_mode_id
                WHERE h.day_data_id=?
            """, (self.day_id,)).fetchall()
            lessons = sorted(
                lessons,
                key=lambda lesson: _day_lesson_teaching_time_key(
                    lesson[4], lesson[0]
                ),
            )

            for lesson in lessons:
                (
                    lesson_id, lesson_number, classe, majal, heure, duration,
                    unit_number, learning_mode
                ) = lesson
                class_name = str(classe or "").strip()
                display_class_name = (
                    f"{classe} — {group_labels[classe]}"
                    if classe in group_labels else classe
                )
                club_lesson_title = None
                activities = con.execute("""
                    SELECT n.id, n.title, n.time, cl.name
                    FROM nachat n
                    LEFT JOIN classe cl ON cl.id=n.classe_id
                    WHERE n.hessa_id=?
                    ORDER BY n.id
                """, (lesson_id,)).fetchall()
                activity_rows = []
                for activity_id, title, activity_time, class_name in activities:
                    club_title = _cultural_club_display_title(
                        cultural_clubs, title, class_name, majal
                    )
                    details = con.execute("""
                        SELECT key_name, value_text
                        FROM nachat_detail
                        WHERE nachat_id=?
                        ORDER BY id
                    """, (activity_id,)).fetchall()
                    activity_rows.append(
                        (
                            club_title or (
                                f"{title} — {class_name}"
                                if class_name else title
                            ),
                            activity_time,
                            details,
                        )
                    )
                    if club_title:
                        club_lesson_title = club_title
                self._add_lesson_card(
                    lesson_number,
                    club_lesson_title or display_class_name,
                    majal, heure, duration,
                    _arabic_month_name(self.day_text)
                    if club_lesson_title else unit_number,
                    learning_mode, activity_rows,
                    "الشهر" if club_lesson_title else "الوحدة",
                )

        club_sessions = self.db.cultural_club_daily_sessions(
            self.day_text
        )
        for club_session in club_sessions:
            self._add_club_session_card(club_session)
        self._update_school_info()
        self._set_day_available(bool(lessons or club_sessions))

    def _add_club_session_card(self, session):
        accent, tint, border = "#7C3AED", "#F5F3FF", "#DDD6FE"
        card = QFrame()
        card.setObjectName("dayCulturalClubSessionCard")
        card.setStyleSheet(
            "QFrame#dayCulturalClubSessionCard {"
            f"background:#FFFFFF; border:1px solid {border};"
            f"border-right:5px solid {accent}; border-radius:12px;"
            "}"
        )
        layout = QVBoxLayout(card)
        normal_margins = (14, 12, 14, 14)
        layout.setContentsMargins(*normal_margins)
        self._register_card_padding_layout(layout, normal_margins)
        layout.setSpacing(8)
        title = QLabel(
            f"جلسة نادي {session.get('club_name') or '—'}"
        )
        title.setObjectName("dayCulturalClubSessionTitle")
        title.setStyleSheet(
            f"color:{accent}; font-size:12pt; font-weight:700;"
            "background:transparent; border:none;"
        )
        layout.addWidget(title)
        metadata = QLabel(
            f"النوع: {session.get('club_type') or '—'}  |  "
            f"الساعة: {session.get('hour_interval') or '—'}  |  "
            f"المدة: {session.get('duration_minutes') or '—'} دقيقة"
        )
        metadata.setWordWrap(True)
        metadata.setStyleSheet(
            f"color:#334155; background:{tint};"
            f"border:1px solid {border}; border-radius:7px; "
            f"padding:{3 if self._is_compact_layout() else 7}px;"
        )
        layout.addWidget(metadata)
        for prop in session.get("properties", []):
            property_label = QLabel(
                f"{prop.get('key_name') or '—'}: "
                f"{prop.get('value_text') or '—'}"
            )
            property_label.setWordWrap(True)
            property_label.setStyleSheet(
                "color:#334155; background:transparent; border:none;"
            )
            layout.addWidget(property_label)
        self.lessons_layout.insertWidget(
            self.lessons_layout.count() - 1, card
        )

    def _add_lesson_card(
        self, lesson_number, classe, majal, heure, duration, unit_number,
        learning_mode, activities, unit_label="الوحدة",
    ):
        colors = (
            ("#2563EB", "#EFF6FF", "#BFDBFE"),
            ("#059669", "#ECFDF5", "#A7F3D0"),
            ("#D97706", "#FFFBEB", "#FDE68A"),
            ("#7C3AED", "#F5F3FF", "#DDD6FE"),
            ("#DB2777", "#FDF2F8", "#FBCFE8"),
            ("#0891B2", "#ECFEFF", "#A5F3FC"),
            ("#DC2626", "#FEF2F2", "#FECACA"),
            ("#4F46E5", "#EEF2FF", "#C7D2FE"),
        )
        accent, tint, border = colors[
            (self.lessons_layout.count() - 1) % len(colors)
        ]

        lesson_card = QFrame()
        lesson_card.setObjectName("dayLessonCard")
        lesson_card.setStyleSheet(
            "QFrame#dayLessonCard {"
            f"background: #FFFFFF; border: 1px solid {border};"
            f"border-right: 5px solid {accent}; border-radius: 12px;"
            "}"
        )
        card_layout = QVBoxLayout(lesson_card)
        normal_card_margins = (14, 12, 14, 14)
        card_layout.setContentsMargins(*normal_card_margins)
        self._register_card_padding_layout(
            card_layout, normal_card_margins
        )
        card_layout.setSpacing(10)

        title = QLabel(str(classe or "—"))
        title.setStyleSheet(
            f"color: {accent}; font-size: 12pt; font-weight: 700;"
            "background: transparent; border: none;"
        )
        card_layout.addWidget(title)

        metadata = (
            ("المجال", majal),
            ("ساعة التدريس", heure),
            ("التوقيت", duration),
            (unit_label, unit_number),
            ("الحصة", lesson_number),
            ("نمط التعلم", learning_mode),
        )
        metadata_container = QWidget(lesson_card)
        metadata_container.setObjectName("dayLessonMetadata")
        metadata_container_layout = QVBoxLayout(metadata_container)
        metadata_container_layout.setContentsMargins(0, 0, 0, 0)
        metadata_container_layout.setSpacing(0)
        metadata_chips = QWidget(metadata_container)
        metadata_chips.setObjectName("dayLessonMetadataChips")
        metadata_row = QGridLayout(metadata_chips)
        metadata_row.setHorizontalSpacing(8)
        metadata_row.setVerticalSpacing(6)
        for index, (label, value) in enumerate(metadata):
            chip = QLabel(f"{label}: {value or '—'}")
            chip.setWordWrap(True)
            chip.setStyleSheet(
                f"color: #334155; background: {tint};"
                f"border: 1px solid {border}; border-radius: 7px;"
                "padding: 5px 8px;"
            )
            metadata_row.addWidget(chip, index // 3, index % 3)
        metadata_container_layout.addWidget(metadata_chips)
        compact_values = " | ".join(
            (
                f"{label}: {value or '—'}"
                if label in (unit_label, "الحصة")
                else str(value or "—")
            )
            for label, value in metadata
        )
        compact_metadata = QLabel(compact_values, metadata_container)
        compact_metadata.setObjectName("dayLessonMetadataCompact")
        compact_metadata.setAccessibleName("بيانات الحصة")
        compact_metadata.setWordWrap(True)
        compact_metadata.setStyleSheet(
            f"color: #334155; background: {tint};"
            f"border: 1px solid {border}; border-radius: 7px;"
            "padding: 3px;"
        )
        metadata_container_layout.addWidget(compact_metadata)
        compact = self._is_compact_layout()
        metadata_chips.setVisible(not compact)
        compact_metadata.setVisible(compact)
        self._lesson_metadata_views.append(
            (metadata_chips, compact_metadata)
        )
        card_layout.addWidget(metadata_container)

        activities_title = QLabel(f"الأنشطة ({len(activities)})")
        activities_title.setStyleSheet(
            "color: #475569; font-weight: 700;"
            "background: transparent; border: none;"
        )
        card_layout.addWidget(activities_title)
        if not activities:
            empty_label = QLabel("لا توجد أنشطة مسجلة لهذه الحصة.")
            empty_label.setStyleSheet(
                "color: #64748B; padding: 6px;"
                "background: transparent; border: none;"
            )
            card_layout.addWidget(empty_label)
        for activity_title, activity_time, details in activities:
            activity_card = QFrame()
            activity_card.setObjectName("dayActivityCard")
            activity_card.setStyleSheet(
                "QFrame#dayActivityCard {"
                f"background: {tint}; border: 1px solid {border};"
                "border-radius: 9px;"
                "}"
            )
            activity_layout = QVBoxLayout(activity_card)
            normal_activity_margins = (10, 8, 10, 8)
            activity_layout.setContentsMargins(*normal_activity_margins)
            self._register_card_padding_layout(
                activity_layout, normal_activity_margins
            )
            activity_layout.setSpacing(5)
            activity_heading = QLabel(
                f"{activity_title or 'نشاط دون عنوان'}"
                + (f"  ·  {activity_time}" if activity_time else "")
            )
            activity_heading.setWordWrap(True)
            activity_heading.setStyleSheet(
                f"color: {accent}; font-weight: 700;"
                "background: transparent; border: none;"
            )
            activity_layout.addWidget(activity_heading)
            ordered_details = sorted(
                enumerate(details),
                key=lambda indexed_detail: (
                    0
                    if str(indexed_detail[1][0] or "").strip().casefold()
                    in {"مكوّن الكفاية", "مكون الكفاية"}
                    else 1
                    if str(indexed_detail[1][0] or "").strip().casefold()
                    in {"الهدف المميز", "الأهداف المميزة"}
                    else 2,
                    indexed_detail[0],
                ),
            )
            for _index, (key_name, value_text) in ordered_details:
                value_text = _target_criteria_display_value(
                    learning_mode, key_name, value_text
                )
                detail_label = QLabel()
                detail_label.setTextFormat(Qt.TextFormat.RichText)
                escaped_key = html.escape(
                    str(key_name or "—"), quote=True
                )
                escaped_value = html.escape(
                    str(value_text or "—"), quote=True
                ).replace("\n", "<br/>")
                detail_label.setText(
                    f"<span style='color:{accent}; font-weight:700;'>"
                    f"{escaped_key}:</span> "
                    f"<span style='color:#334155;'>{escaped_value}</span>"
                )
                detail_label.setWordWrap(True)
                detail_label.setStyleSheet(
                    "color: #334155; background: transparent;"
                    "border: none;"
                )
                activity_layout.addWidget(detail_label)
            card_layout.addWidget(activity_card)

        self.lessons_layout.insertWidget(
            self.lessons_layout.count() - 1, lesson_card
        )

    def _day_payload(self):
        return self._build_day_payload(
            self.db.path, self.day_year_id, self.day_id
        )

    @staticmethod
    def _build_day_payload(database_path, school_year_id, day_id):
        with connect_database(database_path) as con:
            con.row_factory = sqlite3.Row
            day_row = con.execute("""
                SELECT id, date FROM day_data
                WHERE id=? AND ann_scolaire_id=?
            """, (day_id, school_year_id)).fetchone()
            if not day_row:
                raise ValueError("اليوم المحدد لم يعد موجوداً في قاعدة البيانات.")

            school_info = con.execute("""
                SELECT nom_annee, nom_ecole, nom_enseignant, nom_inspecteur, grade
                FROM ann_scolaire WHERE id=?
            """, (school_year_id,)).fetchone()
            year, school, teacher, inspector, grade = school_info or ("", "", "", "", "")
            payload = {
                "date": day_row["date"],
                "school_info": {
                    "nom_annee": year or "",
                    "nom_ecole": school or "",
                    "nom_enseignant": teacher or "",
                    "nom_inspecteur": inspector or "",
                    "grade": grade or "",
                },
                "lessons": [],
                "club_sessions": [],
            }
            cultural_clubs_by_id = {}
            club_rows = con.execute("""
                SELECT c.id, c.name, c.club_type, s.section_name
                FROM cultural_club c
                LEFT JOIN cultural_club_section s ON s.club_id=c.id
                WHERE c.ann_scolaire_id=?
                ORDER BY c.id, s.id
            """, (school_year_id,)).fetchall()
            for club_row in club_rows:
                club = cultural_clubs_by_id.setdefault(
                    club_row["id"],
                    {
                        "id": club_row["id"],
                        "name": club_row["name"] or "",
                        "club_type": club_row["club_type"] or "",
                        "sections": [],
                    },
                )
                section_name = str(
                    club_row["section_name"] or ""
                ).strip()
                if section_name:
                    club["sections"].append({
                        "section_name": section_name,
                    })
            cultural_clubs = list(cultural_clubs_by_id.values())
            lessons = con.execute("""
                SELECT h.id, COALESCE(g.group_key, c.name) AS classe,
                    l.name AS classe_level, g.group_key AS class_group_key,
                    m.name AS majal, h.heure, h.time, h.wehda_number,
                    h.hessa_number, lm.name AS namat_taallom
                FROM hessa h
                JOIN classe c ON c.id=h.classe_id
                LEFT JOIN class_group g ON g.id=h.class_group_id
                JOIN level l ON l.id=c.level_id
                LEFT JOIN majal m ON m.id=h.majal_id
                LEFT JOIN learning_mode lm ON lm.id=h.learning_mode_id
                WHERE h.day_data_id=?
            """, (day_id,)).fetchall()
            lessons = sorted(
                lessons,
                key=lambda lesson: _day_lesson_teaching_time_key(
                    lesson["heure"], lesson["id"]
                ),
            )
            for lesson in lessons:
                lesson_data = {
                    "id": lesson["id"],
                    "classe": lesson["classe"] or "",
                    "classe_level": lesson["classe_level"] or "",
                    "class_group_key": lesson["class_group_key"],
                    "majal": lesson["majal"] or "",
                    "heure": lesson["heure"] or "",
                    "time": lesson["time"] or "",
                    "wehda_number": lesson["wehda_number"],
                    "hessa_number": lesson["hessa_number"],
                    "namat_taallom": lesson["namat_taallom"] or "",
                    "activities": [],
                }
                lesson_data["class_members"] = [
                    {
                        "classe": member["name"],
                        "level": member["level"],
                    }
                    for member in con.execute("""
                        SELECT cl.name, l.name AS level
                        FROM hessa_class_member hm
                        JOIN classe cl ON cl.id=hm.classe_id
                        JOIN level l ON l.id=cl.level_id
                        WHERE hm.hessa_id=? ORDER BY hm.position
                    """, (lesson["id"],)).fetchall()
                ]
                seen_club_activities = set()
                activities = con.execute("""
                    SELECT n.id, n.title, n.time, cl.name AS classe
                    FROM nachat n
                    LEFT JOIN classe cl ON cl.id=n.classe_id
                    WHERE n.hessa_id=? ORDER BY n.id
                """, (lesson["id"],)).fetchall()
                for activity in activities:
                    details = con.execute("""
                        SELECT key_name, value_text FROM nachat_detail
                        WHERE nachat_id=? ORDER BY id
                    """, (activity["id"],)).fetchall()
                    activity_data = {
                        "id": activity["id"],
                        "title": activity["title"] or "",
                        "time": activity["time"] or "",
                        "classe": activity["classe"],
                        "details": [
                            {
                                "key_name": detail["key_name"] or "",
                                "value_text": _target_criteria_display_value(
                                    lesson_data["namat_taallom"],
                                    detail["key_name"],
                                    detail["value_text"],
                                ),
                            }
                            for detail in details
                        ],
                    }
                    club_display_title = _cultural_club_display_title(
                        cultural_clubs,
                        activity["title"],
                        activity["classe"],
                        lesson_data["majal"],
                    )
                    if club_display_title:
                        activity_key = (
                            club_display_title.casefold(),
                            str(activity["title"] or "").strip().casefold(),
                            str(activity["time"] or "").strip().casefold(),
                            tuple(
                                (detail["key_name"], detail["value_text"])
                                for detail in details
                            ),
                        )
                        if activity_key in seen_club_activities:
                            continue
                        seen_club_activities.add(activity_key)
                        lesson_data["display_classe"] = club_display_title
                        activity_data["display_title"] = club_display_title
                        month_name = _arabic_month_name(day_row["date"])
                        if month_name:
                            lesson_data["display_unit_label"] = "الشهر"
                            lesson_data["display_unit_value"] = month_name
                    lesson_data["activities"].append(activity_data)
                payload["lessons"].append(lesson_data)
            club_sessions = con.execute("""
                SELECT daily.id, daily.club_id, club.name, club.club_type,
                    daily.session_date, daily.hour_interval,
                    daily.duration_minutes, daily.monthly_session_id,
                    COALESCE(monthly.absent_count, 0)
                FROM cultural_club_daily_session daily
                JOIN cultural_club club ON club.id=daily.club_id
                LEFT JOIN cultural_club_monthly_session monthly
                    ON monthly.id=daily.monthly_session_id
                WHERE daily.ann_scolaire_id=? AND daily.session_date=?
                ORDER BY daily.hour_interval, club.name COLLATE NOCASE,
                    daily.id
            """, (school_year_id, day_row["date"])).fetchall()
            for session in club_sessions:
                (
                    session_id, club_id, club_name, club_type, session_date,
                    hour_interval, duration, monthly_session_id, absent_count,
                ) = session
                sections = con.execute("""
                    SELECT section_name, female_count, male_count
                    FROM cultural_club_section
                    WHERE club_id=? ORDER BY id
                """, (club_id,)).fetchall()
                properties = con.execute("""
                    SELECT key_name, value_text
                    FROM cultural_club_daily_property
                    WHERE daily_session_id=? ORDER BY position, id
                """, (session_id,)).fetchall()
                if not properties and monthly_session_id is not None:
                    properties = con.execute("""
                        SELECT key_name, value_text
                        FROM cultural_club_monthly_property
                        WHERE session_id=? ORDER BY position, id
                    """, (monthly_session_id,)).fetchall()
                participant_count = sum(
                    female_count + male_count
                    for _name, female_count, male_count in sections
                )
                payload["club_sessions"].append({
                    "id": session_id,
                    "club_id": club_id,
                    "club_name": club_name or "",
                    "club_type": club_type or "",
                    "session_date": session_date,
                    "hour_interval": hour_interval,
                    "duration_minutes": duration,
                    "absent_count": absent_count,
                    "participant_count": participant_count,
                    "present_count": max(0, participant_count - absent_count),
                    "sections": [
                        {
                            "section_name": section_name,
                            "female_count": female_count,
                            "male_count": male_count,
                        }
                        for section_name, female_count, male_count in sections
                    ],
                    "properties": [
                        {"key_name": key, "value_text": value}
                        for key, value in properties
                    ],
                })
        if not payload["lessons"] and not payload["club_sessions"]:
            raise ValueError(
                "لا توجد حصص أو جلسات نوادٍ مسجلة لهذا اليوم."
            )
        return payload

    def export_json(self):
        import json

        default_path = (
            Path.home() / "Documents" / f"school_day_{self.day_text}.json"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self, "تصدير اليوم بصيغة JSON", str(default_path),
            "ملفات JSON (*.json)"
        )
        if not file_path:
            return
        if Path(file_path).suffix.lower() != ".json":
            file_path += ".json"

        database_path = self.db.path
        year_id = self.day_year_id
        day_id = self.day_id

        def export_day_json():
            payload = self._build_day_payload(
                database_path, year_id, day_id
            )
            with open(file_path, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, indent=4)

        start_background_task(
            self,
            export_day_json,
            lambda _result: QMessageBox.information(
                self, "نجاح التصدير", f"تم تصدير اليوم إلى:\n{file_path}"
            ),
            lambda error: QMessageBox.critical(
                self, "تعذر تصدير JSON",
                f"حدث خطأ أثناء تصدير اليوم:\n{error}",
            ),
        )

    def print_day(self, pdf_path=None):
        database_path = self.db.path
        year_id = self.day_year_id
        day_id = self.day_id

        def open_day_print(payload):
            try:
                payload = filter_print_details(
                    payload, load_print_detail_exclusions()
                )
                if pdf_path:
                    dialog = DayPdfPreviewDialog(payload, self)
                    dialog._export_pages_async(
                        pdf_path,
                        lambda exported_path: QMessageBox.information(
                            self,
                            "نجاح التصدير",
                            f"تم تصدير اليوم إلى:\n{exported_path}",
                        ),
                        lambda error: QMessageBox.critical(
                            self,
                            "تعذر تصدير PDF",
                            f"حدث خطأ أثناء تصدير اليوم:\n{error}",
                        ),
                    )
                    return

                preview_dialog = DayPdfPreviewDialog(payload, self)
                preview_dialog.print_pages()
            except (OSError, ValueError, RuntimeError) as exc:
                title = "تعذر تصدير PDF" if pdf_path else "تعذر طباعة اليوم"
                message = (
                    "حدث خطأ أثناء تصدير اليوم"
                    if pdf_path else "حدث خطأ أثناء الطباعة"
                )
                QMessageBox.critical(self, title, f"{message}:\n{exc}")

        start_background_task(
            self,
            lambda: self._build_day_payload(
                database_path, year_id, day_id
            ),
            open_day_print,
            lambda error: QMessageBox.critical(
                self,
                "تعذر تجهيز الطباعة",
                f"حدث خطأ أثناء تجهيز بيانات اليوم:\n{error}",
            ),
            keep_overlay_until_window=True,
        )

    def export_pdf(self):
        database_path = self.db.path
        year_id = self.day_year_id
        day_id = self.day_id

        def export_payload(payload):
            try:
                payload = filter_print_details(
                    payload, load_print_detail_exclusions()
                )
                dialog = DayPdfPreviewDialog(payload, self)
                dialog.export_pdf()
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.critical(
                    self, "تعذر تصدير PDF",
                    f"حدث خطأ أثناء تجهيز التصدير:\n{exc}",
                )

        start_background_task(
            self,
            lambda: self._build_day_payload(
                database_path, year_id, day_id
            ),
            export_payload,
            lambda error: QMessageBox.critical(
                self, "تعذر تصدير PDF",
                f"حدث خطأ أثناء تصدير اليوم:\n{error}",
            ),
        )

    def preview_pdf(self):
        database_path = self.db.path
        year_id = self.day_year_id
        day_id = self.day_id

        def open_preview(payload):
            try:
                payload = filter_print_details(
                    payload, load_print_detail_exclusions()
                )
                DayPdfPreviewDialog(payload, self).exec()
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.critical(
                    self, "تعذرت معاينة اليوم",
                    f"حدث خطأ أثناء تجهيز المعاينة:\n{exc}",
                )

        start_background_task(
            self,
            lambda: self._build_day_payload(
                database_path, year_id, day_id
            ),
            open_preview,
            lambda error: QMessageBox.critical(
                self, "تعذرت معاينة اليوم",
                f"حدث خطأ أثناء تجهيز المعاينة:\n{error}",
            ),
            keep_overlay_until_window=True,
        )


class OfficialProgramsWidget(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setLayoutDirection(Qt.RightToLeft)
        
        self.selected_level_id = None
        self.selected_majal_id = None
        self.selected_competence_matiere_id = None
        self.selected_moukawan_id = None
        self.selected_objectif_id = None
        self.program_tree_dialog = None

        main_layout = QVBoxLayout(self)
        filters_group = QGroupBox("الفلاتر واختيار البرامج")
        filters_layout = QHBoxLayout(filters_group)

        self.combo_level = QComboBox()
        self.combo_level.currentIndexChanged.connect(self.on_level_changed)

        self.combo_majal = QComboBox()
        self.combo_majal.currentIndexChanged.connect(self.on_majal_changed)

        self.combo_matiere = QComboBox()
        self.combo_matiere.currentIndexChanged.connect(self.on_matiere_changed)

        self.show_tree_button = QPushButton("عرض الشجرة")
        self.show_tree_button.setProperty("actionType", "browse")
        self.show_tree_button.clicked.connect(self.open_program_tree)

        filters_layout.addWidget(QLabel("المستوى:"))
        filters_layout.addWidget(self.combo_level, 1)
        filters_layout.addWidget(QLabel("المجال:"))
        filters_layout.addWidget(self.combo_majal, 1)
        filters_layout.addWidget(QLabel("المادة/الكفاية:"))
        filters_layout.addWidget(self.combo_matiere, 2)
        filters_layout.addWidget(self.show_tree_button)

        main_layout.addWidget(filters_group)

        competences_group = QGroupBox("الكفايات الأساسية (المجال والمادة)")
        comp_layout = QVBoxLayout(competences_group)

        majal_comp_layout = QHBoxLayout()
        self.txt_competence_majal = QLineEdit()
        self.txt_competence_majal.setReadOnly(True)
        btn_copy_majal = QPushButton("")
        btn_copy_majal.setProperty("actionType", "copy_paste")
        btn_copy_majal.setFixedWidth(60)
        btn_copy_majal.clicked.connect(lambda: self.copy_text(self.txt_competence_majal))
        
        btn_edit_majal = QPushButton("")
        btn_edit_majal.setProperty("actionType", "edit")
        btn_edit_majal.setFixedWidth(60)
        btn_edit_majal.clicked.connect(self.edit_competence_majal)

        majal_comp_layout.addWidget(QLabel("كفاية المجال:"))
        majal_comp_layout.addWidget(self.txt_competence_majal, 1)
        majal_comp_layout.addWidget(btn_copy_majal)
        majal_comp_layout.addWidget(btn_edit_majal)
        comp_layout.addLayout(majal_comp_layout)

        matiere_comp_layout = QHBoxLayout()
        self.txt_competence_matiere = QLineEdit()
        self.txt_competence_matiere.setReadOnly(True)
        btn_copy_matiere = QPushButton("")
        btn_copy_matiere.setProperty("actionType", "copy_paste")
        btn_copy_matiere.setFixedWidth(60)
        btn_copy_matiere.clicked.connect(lambda: self.copy_text(self.txt_competence_matiere))

        btn_edit_matiere = QPushButton("")
        btn_edit_matiere.setProperty("actionType", "edit")
        btn_edit_matiere.setFixedWidth(60)
        btn_edit_matiere.clicked.connect(self.edit_competence_matiere)

        matiere_comp_layout.addWidget(QLabel("كفاية المادة:"))
        matiere_comp_layout.addWidget(self.txt_competence_matiere, 1)
        matiere_comp_layout.addWidget(btn_copy_matiere)
        matiere_comp_layout.addWidget(btn_edit_matiere)
        comp_layout.addLayout(matiere_comp_layout)

        main_layout.addWidget(competences_group)

        tables_splitter = QSplitter(Qt.Horizontal)

        # 1. جدول مكونات الكفاية (مع التفاف النص وتوسيع الصفوف تلقائياً)
        moukawan_widget = QGroupBox("مكونات الكفاية")
        moukawan_layout = QVBoxLayout(moukawan_widget)
        moukawan_btns = QHBoxLayout()
        for text, slot, act_type in [
            ("إضافة", self.add_moukawan, "add"), 
            ("تعديل", self.edit_moukawan, "edit"), 
            ("حذف", self.delete_moukawan, "delete"), 
            ("نسخ", self.copy_moukawan, "copy_paste"), 
            ("لصق", self.paste_moukawan, "copy_paste")
        ]:
            b = QPushButton(text)
            b.setMinimumWidth(38)
            b.setFixedHeight(28)
            b.setProperty("actionType", act_type)
            b.clicked.connect(slot)
            moukawan_btns.addWidget(b)
        moukawan_btns.addStretch()
        
        moukawan_layout.addLayout(moukawan_btns)
        moukawan_layout.addSpacing(8)
        self.tbl_moukawan = self.create_clean_table(["مكون الكفاية"])
        self.tbl_moukawan.setWordWrap(True)
        self.tbl_moukawan.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_moukawan.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_moukawan.itemSelectionChanged.connect(self.on_moukawan_selected)
        moukawan_layout.addWidget(self.tbl_moukawan)
        tables_splitter.addWidget(moukawan_widget)

        # 2. جدول الأهداف المميزة (مع التفاف النص وتوسيع الصفوف تلقائياً)
        objectif_widget = QGroupBox("الأهداف المميزة")
        objectif_layout = QVBoxLayout(objectif_widget)
        objectif_btns = QHBoxLayout()
        for text, slot, act_type in [
            ("إضافة", self.add_objectif, "add"), 
            ("تعديل", self.edit_objectif, "edit"), 
            ("حذف", self.delete_objectif, "delete"), 
            ("نسخ", self.copy_objectif, "copy_paste"), 
            ("لصق", self.paste_objectif, "copy_paste")
        ]:
            b = QPushButton(text)
            b.setMinimumWidth(38)
            b.setFixedHeight(28)
            b.setProperty("actionType", act_type)
            b.clicked.connect(slot)
            objectif_btns.addWidget(b)
        objectif_btns.addStretch()
        
        objectif_layout.addLayout(objectif_btns)
        objectif_layout.addSpacing(8)
        self.tbl_objectif = self.create_clean_table(["الهدف المميز"])
        self.tbl_objectif.setWordWrap(True)
        self.tbl_objectif.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_objectif.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_objectif.itemSelectionChanged.connect(self.on_objectif_selected)
        objectif_layout.addWidget(self.tbl_objectif)
        tables_splitter.addWidget(objectif_widget)

        # 3. جدول المحتويات (مع التفاف النص وتوسيع الصفوف تلقائياً)
        content_widget = QGroupBox("المحتويات")
        content_layout = QVBoxLayout(content_widget)
        content_btns = QHBoxLayout()
        for text, slot, act_type in [
            ("إضافة", self.add_content, "add"), 
            ("تعديل", self.edit_content, "edit"), 
            ("حذف", self.delete_content, "delete"), 
            ("نسخ", self.copy_content, "copy_paste"), 
            ("لصق", self.paste_content, "copy_paste")
        ]:
            b = QPushButton(text)
            b.setMinimumWidth(38)
            b.setFixedHeight(28)
            b.setProperty("actionType", act_type)
            b.clicked.connect(slot)
            content_btns.addWidget(b)
        content_btns.addStretch()
        
        content_layout.addLayout(content_btns)
        content_layout.addSpacing(8)
        self.tbl_content = self.create_clean_table(["المحتوى"])
        self.tbl_content.setWordWrap(True)
        self.tbl_content.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_content.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        content_layout.addWidget(self.tbl_content)
        tables_splitter.addWidget(content_widget)

        tables_splitter.setSizes([330, 330, 330])
        main_layout.addWidget(tables_splitter, 1)

        self.load_levels_and_majals()

    def multi_input_dialog(self, title, fields_info):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(600)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        
        text_editors = []
        for label_text, default_text in fields_info:
            txt = QTextEdit()
            txt.setAcceptRichText(False)
            txt.setPlainText(default_text)
            
            font_metrics = txt.fontMetrics()
            txt.setFixedHeight(font_metrics.lineSpacing() * 5 + 16)
            
            form.addRow(label_text, txt)
            text_editors.append(txt)
            
        layout.addLayout(form)
        
        btns = QDialogButtonBox()
        btns.addButton("موافق", QDialogButtonBox.AcceptRole)
        btns.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        if dlg.exec() == QDialog.Accepted:
            results = [editor.toPlainText().strip() for editor in text_editors]
            return results, True
        return [], False

    def create_clean_table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def load_levels_and_majals(self):
        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                self.combo_level.blockSignals(True)
                self.combo_level.clear()
                for lid, lname in cursor.execute("SELECT id, name FROM level").fetchall():
                    self.combo_level.addItem(lname, lid)
                self.combo_level.blockSignals(False)

                self.combo_majal.blockSignals(True)
                self.combo_majal.clear()
                for mid, mname in cursor.execute("SELECT id, name FROM majal").fetchall():
                    self.combo_majal.addItem(mname, mid)
                self.combo_majal.blockSignals(False)

            self.update_matieres_combo()
        except Exception as e:
            print(f"Error loading filters: {e}")

    def on_level_changed(self):
        self.selected_level_id = self.combo_level.currentData()
        self.update_matieres_combo()

    def on_majal_changed(self):
        self.selected_majal_id = self.combo_majal.currentData()
        self.update_matieres_combo()

    def update_matieres_combo(self):
        self.combo_matiere.blockSignals(True)
        self.combo_matiere.clear()
        self.selected_level_id = self.combo_level.currentData()
        self.selected_majal_id = self.combo_majal.currentData()
        
        if not self.selected_level_id or not self.selected_majal_id:
            self.combo_matiere.blockSignals(False)
            return

        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                query = """
                    cm.id, cm.matiere, cm.competence, cm.id_competence_majal,
                    cmajal.competence AS majal_competence
                    FROM competence_matiere cm
                    JOIN competence_majal cmajal ON cm.id_competence_majal = cmajal.id
                    WHERE cmajal.id_majal = ? AND cmajal.id_level = ?
                """
                params = [self.selected_majal_id, self.selected_level_id]

                for row in cursor.execute(f"SELECT {query}", params).fetchall():
                    display_text = f"{row[1]} — {row[2]}"
                    self.combo_matiere.addItem(display_text, {
                        "competence_matiere_id": row[0],
                        "matiere": row[1],
                        "competence_matiere": row[2],
                        "id_competence_majal": row[3],
                        "majal_competence": row[4]
                    })
        except Exception as e:
            print(f"Error updating matieres: {e}")
        
        self.combo_matiere.blockSignals(False)
        self.on_matiere_changed()

    def open_program_tree(self):
        level_id = self.combo_level.currentData()
        if not level_id:
            QMessageBox.information(self, "اختيار المستوى", "يرجى اختيار المستوى الدراسي أولاً.")
            return

        if self.program_tree_dialog is None:
            try:
                self.program_tree_dialog = OfficialProgramsTreeWidget(
                    self.db,
                    level_id,
                    self.combo_level.currentText(),
                    self.combo_majal.currentData(),
                    self.combo_majal.currentText(),
                    self
                )
            except sqlite3.Error as exc:
                QMessageBox.critical(
                    self, "تعذر عرض البرامج",
                    f"تعذر تحميل شجرة البرامج الرسمية:\n{exc}"
                )
                return
        else:
            self.program_tree_dialog.level_id = level_id
            self.program_tree_dialog.level_name = self.combo_level.currentText()
            self.program_tree_dialog.majal_id = self.combo_majal.currentData()
            self.program_tree_dialog.majal_name = self.combo_majal.currentText()
            try:
                self.program_tree_dialog.refresh_tree()
            except sqlite3.Error as exc:
                QMessageBox.critical(self, "تعذر عرض البرامج", f"تعذر تحميل شجرة البرامج الرسمية:\n{exc}")
                return

        self.program_tree_dialog.setWindowModality(Qt.NonModal)
        self.program_tree_dialog.showMaximized()
        self.program_tree_dialog.raise_()
        self.program_tree_dialog.activateWindow()

    def on_matiere_changed(self):
        data = self.combo_matiere.currentData()
        if not data:
            self.txt_competence_majal.clear()
            self.txt_competence_matiere.clear()
            self.selected_competence_matiere_id = None
            self.tbl_moukawan.setRowCount(0)
            self.tbl_objectif.setRowCount(0)
            self.tbl_content.setRowCount(0)
            return

        self.selected_competence_matiere_id = data["competence_matiere_id"]
        self.txt_competence_majal.setText(data["majal_competence"])
        self.txt_competence_matiere.setText(data["competence_matiere"])
        self.load_moukawan_data()

    def load_moukawan_data(self):
        self.tbl_moukawan.setRowCount(0)
        self.tbl_objectif.setRowCount(0)
        self.tbl_content.setRowCount(0)
        if not self.selected_competence_matiere_id:
            return

        try:
            with self.db.connect() as con:
                for row in con.execute("SELECT id, competence FROM moukawan_kifaya WHERE id_competence_matiere = ?", (self.selected_competence_matiere_id,)).fetchall():
                    r = self.tbl_moukawan.rowCount()
                    self.tbl_moukawan.insertRow(r)
                    item_comp = QTableWidgetItem(row[1])
                    item_comp.setData(Qt.UserRole, row[0])
                    self.tbl_moukawan.setItem(r, 0, item_comp)
            
            # تكييف الارتفاع تلقائياً لعرض النصوص الطويلة بالكامل
            self.tbl_moukawan.resizeRowsToContents()
        except Exception as e:
            print(f"Error loading moukawan: {e}")

    def on_moukawan_selected(self):
        row = self.tbl_moukawan.currentRow()
        if row < 0:
            self.selected_moukawan_id = None
            self.tbl_objectif.setRowCount(0)
            return
        item = self.tbl_moukawan.item(row, 0)
        self.selected_moukawan_id = item.data(Qt.UserRole) if item else None
        self.load_objectif_data()

    def load_objectif_data(self):
        self.tbl_objectif.setRowCount(0)
        self.tbl_content.setRowCount(0)
        if not self.selected_moukawan_id:
            return

        try:
            with self.db.connect() as con:
                for row in con.execute("SELECT id, objectif_specifique, description FROM objectif_specifique WHERE id_moukawa_kifaya = ?", (self.selected_moukawan_id,)).fetchall():
                    r = self.tbl_objectif.rowCount()
                    self.tbl_objectif.insertRow(r)
                    item_obj = QTableWidgetItem(row[1])
                    item_obj.setData(Qt.UserRole, row[0])
                    item_obj.setData(Qt.UserRole + 1, row[2] or "")
                    self.tbl_objectif.setItem(r, 0, item_obj)
            
            self.tbl_objectif.resizeRowsToContents()
        except Exception as e:
            print(f"Error loading objectifs: {e}")

    def on_objectif_selected(self):
        row = self.tbl_objectif.currentRow()
        if row < 0:
            self.selected_objectif_id = None
            self.tbl_content.setRowCount(0)
            return
        item = self.tbl_objectif.item(row, 0)
        self.selected_objectif_id = item.data(Qt.UserRole) if item else None
        self.load_content_data()

    def load_content_data(self):
        self.tbl_content.setRowCount(0)
        if not self.selected_objectif_id:
            return

        try:
            with self.db.connect() as con:
                for row in con.execute("SELECT id, content, description FROM content WHERE id_objectif_specifique = ?", (self.selected_objectif_id,)).fetchall():
                    r = self.tbl_content.rowCount()
                    self.tbl_content.insertRow(r)
                    item_cnt = QTableWidgetItem(row[1])
                    item_cnt.setData(Qt.UserRole, row[0])
                    item_cnt.setData(Qt.UserRole + 1, row[2] or "")
                    self.tbl_content.setItem(r, 0, item_cnt)
            
            # تكييف الارتفاع تلقائياً لعرض النصوص الطويلة بالكامل
            self.tbl_content.resizeRowsToContents()
        except Exception as e:
            print(f"Error loading contents: {e}")

    def copy_text(self, line_edit):
        line_edit.selectAll()
        line_edit.copy()

    def edit_competence_majal(self):
        data = self.combo_matiere.currentData()
        if not data:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد المادة أولاً.")
            return
        new_val, ok = self.input_dialog("تعديل كفاية المجال", "أدخل النص الجديد:", self.txt_competence_majal.text())
        if ok and new_val:
            try:
                with self.db.connect() as con:
                    con.execute("UPDATE competence_majal SET competence = ? WHERE id = ?", (new_val, data["id_competence_majal"]))
                    con.commit()
                self.update_matieres_combo()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر التحديث: {e}")

    def edit_competence_matiere(self):
        data = self.combo_matiere.currentData()
        if not data:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد المادة أولاً.")
            return
        new_val, ok = self.input_dialog("تعديل كفاية المادة", "أدخل النص الجديد:", self.txt_competence_matiere.text())
        if ok and new_val:
            try:
                with self.db.connect() as con:
                    con.execute("UPDATE competence_matiere SET competence = ? WHERE id = ?", (new_val, data["competence_matiere_id"]))
                    con.commit()
                self.update_matieres_combo()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر التحديث: {e}")

    def add_moukawan(self):
        if not self.selected_competence_matiere_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار المادة أولاً.")
            return
        val, ok = self.input_dialog("إضافة مكون كفاية", "أدخل مكون الكفاية:")
        if ok and val:
            try:
                with self.db.connect() as con:
                    con.execute("INSERT INTO moukawan_kifaya (competence, id_competence_matiere) VALUES (?, ?)", (val, self.selected_competence_matiere_id))
                    con.commit()
                self.load_moukawan_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الإضافة: {e}")

    def edit_moukawan(self):
        row = self.tbl_moukawan.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد مكون كفاية للتعديل.")
            return
        item = self.tbl_moukawan.item(row, 0)
        rec_id = item.data(Qt.UserRole)
        val, ok = self.input_dialog("تعديل مكون الكفاية", "أدخل النص الجديد:", item.text())
        if ok and val:
            try:
                with self.db.connect() as con:
                    con.execute("UPDATE moukawan_kifaya SET competence = ? WHERE id = ?", (val, rec_id))
                    con.commit()
                self.load_moukawan_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر التعديل: {e}")

    def delete_moukawan(self):
        row = self.tbl_moukawan.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد مكون كفاية للحذف.")
            return
        item = self.tbl_moukawan.item(row, 0)
        rec_id = item.data(Qt.UserRole)
        if QMessageBox.question(self, "تأكيد", "هل أنت متأكد من الحذف؟") == QMessageBox.Yes:
            try:
                with self.db.connect() as con:
                    con.execute("DELETE FROM moukawan_kifaya WHERE id = ?", (rec_id,))
                    con.commit()
                self.load_moukawan_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الحذف: {e}")

    def copy_moukawan(self):
        row = self.tbl_moukawan.currentRow()
        if row >= 0:
            item = self.tbl_moukawan.item(row, 0)
            self.copied_moukawan_text = item.text()
            moukawan_id = item.data(Qt.UserRole)
            self.copied_moukawan_data = {
                "competence": self.copied_moukawan_text,
                "objectifs": [],
            }
            with self.db.connect() as con:
                objectifs = con.execute(
                    """SELECT id, objectif_specifique, description
                       FROM objectif_specifique
                       WHERE id_moukawa_kifaya = ?
                       ORDER BY id""",
                    (moukawan_id,),
                ).fetchall()
                for objectif_id, objectif_text, objectif_description in objectifs:
                    contents = con.execute(
                        """SELECT content, description FROM content
                           WHERE id_objectif_specifique = ? ORDER BY id""",
                        (objectif_id,),
                    ).fetchall()
                    self.copied_moukawan_data["objectifs"].append({
                        "objectif_specifique": objectif_text,
                        "description": objectif_description or "",
                        "contents": [
                            {"content": content_text, "description": description or ""}
                            for content_text, description in contents
                        ],
                    })
            QApplication.clipboard().setText(self.copied_moukawan_text)

    def paste_moukawan(self):
        if hasattr(self, 'copied_moukawan_text') and self.selected_competence_matiere_id:
            try:
                with self.db.connect() as con:
                    cursor = con.execute(
                        "INSERT INTO moukawan_kifaya (competence, id_competence_matiere) VALUES (?, ?)",
                        (self.copied_moukawan_text, self.selected_competence_matiere_id),
                    )
                    new_moukawan_id = cursor.lastrowid
                    copied_data = getattr(self, "copied_moukawan_data", None)
                    if copied_data:
                        for objectif in copied_data["objectifs"]:
                            objectif_cursor = con.execute(
                                """INSERT INTO objectif_specifique
                                   (objectif_specifique, id_moukawa_kifaya, description)
                                   VALUES (?, ?, ?)""",
                                (
                                    objectif["objectif_specifique"],
                                    new_moukawan_id,
                                    objectif["description"],
                                ),
                            )
                            new_objectif_id = objectif_cursor.lastrowid
                            for content in objectif["contents"]:
                                con.execute(
                                    """INSERT INTO content
                                       (content, id_objectif_specifique, description)
                                       VALUES (?, ?, ?)""",
                                    (
                                        content["content"],
                                        new_objectif_id,
                                        content["description"],
                                    ),
                                )
                    con.commit()
                self.load_moukawan_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر اللصق: {e}")

    def add_objectif(self):
        if not self.selected_moukawan_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار مكون كفاية أولاً.")
            return
            
        fields = [
            ("الهدف المميز:", ""),
            ("الملاحظات:", "")
        ]
        vals, ok = self.multi_input_dialog("إضافة هدف مميز جديد", fields)
        
        if ok and vals[0]:
            val = vals[0]
            desc = vals[1]
            try:
                with self.db.connect() as con:
                    con.execute(
                        "INSERT INTO objectif_specifique (objectif_specifique, id_moukawa_kifaya, description) VALUES (?, ?, ?)", 
                        (val, self.selected_moukawan_id, desc)
                    )
                    con.commit()
                self.load_objectif_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الإضافة: {e}")

    def edit_objectif(self):
        row = self.tbl_objectif.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد هدف مميز للتعديل.")
            return
        item_obj = self.tbl_objectif.item(row, 0)
        rec_id = item_obj.data(Qt.UserRole)
        current_text = item_obj.text()
        current_desc = item_obj.data(Qt.UserRole + 1) or ""
        
        fields = [
            ("تعديل الهدف المميز:", current_text),
            ("تعديل الملاحظات:", current_desc)
        ]
        vals, ok = self.multi_input_dialog("تعديل الهدف المميز", fields)
        
        if ok and vals[0]:
            val = vals[0]
            desc = vals[1]
            try:
                with self.db.connect() as con:
                    con.execute(
                        "UPDATE objectif_specifique SET objectif_specifique = ?, description = ? WHERE id = ?", 
                        (val, desc, rec_id)
                    )
                    con.commit()
                self.load_objectif_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر التعديل: {e}")

    def delete_objectif(self):
        row = self.tbl_objectif.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد هدف مميز للحذف.")
            return
        item = self.tbl_objectif.item(row, 0)
        rec_id = item.data(Qt.UserRole)
        if QMessageBox.question(self, "تأكيد", "هل أنت متأكد من الحذف؟") == QMessageBox.Yes:
            try:
                with self.db.connect() as con:
                    con.execute("DELETE FROM objectif_specifique WHERE id = ?", (rec_id,))
                    con.commit()
                self.load_objectif_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الحذف: {e}")

    def copy_objectif(self):
        row = self.tbl_objectif.currentRow()
        if row >= 0:
            item = self.tbl_objectif.item(row, 0)
            self.copied_obj_text = item.text()
            self.copied_obj_desc = item.data(Qt.UserRole + 1) or ""
            objectif_id = item.data(Qt.UserRole)
            with self.db.connect() as con:
                contents = con.execute(
                    """SELECT content, description FROM content
                       WHERE id_objectif_specifique = ? ORDER BY id""",
                    (objectif_id,),
                ).fetchall()
            self.copied_obj_contents = [
                {"content": content_text, "description": description or ""}
                for content_text, description in contents
            ]
            QApplication.clipboard().setText(self.copied_obj_text)

    def paste_objectif(self):
        if hasattr(self, 'copied_obj_text') and self.selected_moukawan_id:
            try:
                with self.db.connect() as con:
                    cursor = con.execute(
                        """INSERT INTO objectif_specifique
                           (objectif_specifique, id_moukawa_kifaya, description)
                           VALUES (?, ?, ?)""",
                        (self.copied_obj_text, self.selected_moukawan_id, self.copied_obj_desc),
                    )
                    new_objectif_id = cursor.lastrowid
                    for content in getattr(self, "copied_obj_contents", []):
                        con.execute(
                            """INSERT INTO content
                               (content, id_objectif_specifique, description)
                               VALUES (?, ?, ?)""",
                            (
                                content["content"],
                                new_objectif_id,
                                content["description"],
                            ),
                        )
                    con.commit()
                self.load_objectif_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر اللصق: {e}")

    def add_content(self):
        if not self.selected_objectif_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار هدف مميز أولاً.")
            return
            
        fields = [
            ("المحتوى:", ""),
            ("الملاحظات (اختياري):", "")
        ]
        vals, ok = self.multi_input_dialog("إضافة محتوى جديد", fields)
        
        if ok and vals[0]:
            val = vals[0]
            desc = vals[1]
            try:
                with self.db.connect() as con:
                    con.execute(
                        "INSERT INTO content (content, id_objectif_specifique, description) VALUES (?, ?, ?)", 
                        (val, self.selected_objectif_id, desc)
                    )
                    con.commit()
                self.load_content_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الإضافة: {e}")

    def edit_content(self):
        row = self.tbl_content.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد محتوى للتعديل.")
            return
        item_cnt = self.tbl_content.item(row, 0)
        rec_id = item_cnt.data(Qt.UserRole)
        current_text = item_cnt.text()
        current_desc = item_cnt.data(Qt.UserRole + 1) or ""
        
        fields = [
            ("تعديل المحتوى:", current_text),
            ("تعديل الملاحظات:", current_desc)
        ]
        vals, ok = self.multi_input_dialog("تعديل المحتوى", fields)
        
        if ok and vals[0]:
            val = vals[0]
            desc = vals[1]
            try:
                with self.db.connect() as con:
                    con.execute(
                        "UPDATE content SET content = ?, description = ? WHERE id = ?", 
                        (val, desc, rec_id)
                    )
                    con.commit()
                self.load_content_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر التعديل: {e}")

    def delete_content(self):
        row = self.tbl_content.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد محتوى للحذف.")
            return
        item = self.tbl_content.item(row, 0)
        rec_id = item.data(Qt.UserRole)
        if QMessageBox.question(self, "تأكيد", "هل أنت متأكد من الحذف؟") == QMessageBox.Yes:
            try:
                with self.db.connect() as con:
                    con.execute("DELETE FROM content WHERE id = ?", (rec_id,))
                    con.commit()
                self.load_content_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الحذف: {e}")

    def copy_content(self):
        row = self.tbl_content.currentRow()
        if row >= 0:
            item = self.tbl_content.item(row, 0)
            self.copied_cnt_text = item.text()
            self.copied_cnt_desc = item.data(Qt.UserRole + 1) or ""
            self.copied_cnt_data = {
                "content": self.copied_cnt_text,
                "description": self.copied_cnt_desc,
            }
            QApplication.clipboard().setText(self.copied_cnt_text)

    def paste_content(self):
        if hasattr(self, 'copied_cnt_text') and self.selected_objectif_id:
            try:
                with self.db.connect() as con:
                    copied_data = getattr(self, "copied_cnt_data", None) or {
                        "content": self.copied_cnt_text,
                        "description": self.copied_cnt_desc,
                    }
                    con.execute(
                        """INSERT INTO content
                           (content, id_objectif_specifique, description)
                           VALUES (?, ?, ?)""",
                        (
                            copied_data["content"],
                            self.selected_objectif_id,
                            copied_data["description"],
                        ),
                    )
                    con.commit()
                self.load_content_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر اللصق: {e}")

    def input_dialog(self, title, label_text, default_text=""):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(450)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        
        txt = QTextEdit() if len(default_text) > 30 or "\n" in default_text or "المجال" in title or "المادة" in title else QLineEdit()
        if isinstance(txt, QTextEdit):
            txt.setPlainText(default_text)
            txt.setMinimumHeight(100)
        else:
            txt.setText(default_text)
            
        form.addRow(label_text, txt)
        layout.addLayout(form)
        
        btns = QDialogButtonBox()
        btns.addButton("موافق", QDialogButtonBox.AcceptRole)
        btns.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        
        if dlg.exec() == QDialog.Accepted:
            val = txt.toPlainText().strip() if isinstance(txt, QTextEdit) else txt.text().strip()
            return val, True
        return "", False
