# -*- coding: utf-8 -*-
"""الواجهة الرئيسية (SchoolPlanner) — بقية الكود مقسم إلى:
app_config, database, completion, dialogs, widgets.
"""
import argparse
from app_config import (
    APP_DIR,
    DB_PATH,
    ICON_PATH,
    LEVEL_FIRAKS,
    PLANS_NAMES,
    SCHOOL_INFO_COLUMNS,
    TEACHER_AVATAR_ICONS,
    TEACHER_GENDER_OPTIONS,
    ArabicDialogTranslator,
    is_small_window,
    install_action_button_icon_filter,
    install_dialog_size_filter,
    level_firak_label,
    load_custom_font,
    set_application_button_scale,
    set_card_action_type,
    set_action_button_type,
)
from database import (
    Database, activity_completion_issues,
    duration_minutes, lesson_completion_issues,
    required_activity_properties,
)
from completion import warm_completion_cache
from activity_duration_suggestions import warm_activity_duration_cache
from dialogs import (ActivityEntryDialog, BulkLessonEntryDialog, CompetenceManagerDialog,
                     ConceptManagerDialog,
                     CustomCalendarWidget, DaySelectionDialog,
                     DetailEntryDialog, EntryDialog, LessonEntryDialog,
                     LessonScheduleEditDialog,
                     MonthlyClubPlanDialog,
                     MonthlyClubSessionDetailsDialog,
                     MonthlyClubSessionSelectionDialog,
                     RepeatActivitiesSelectionDialog,
                     SchoolYearSelectionDialog,
                     TeachingAssignmentsDialog, TimetableDialog,
                     YearImportDialog)
from widgets import (CompetencesCbaBrowsePage, DayLessonsBrowsePage,
                     OfficialProgramsBrowsePage, OfficialProgramsWidget)
from teacher_timetable import TeacherTimetablePage
from plans import (
    WEEKDAYS, OfficialHolidaysPage, TeachingPlanViewPage, TeachingPlansPage,
)
from lesson_book_settings import LessonBookSettingsPage
from assessment_file_management import AssessmentFileManagementPage
from exam_schedule import ExamSchedulePage
from smart_navigation_search import (
    decode_database_result_key,
    NavigationSearchHistory,
    NavigationSearchTask,
    NavigationSearchPopup,
    SmartNavigationSearchIndex,
)
from busy_overlay import start_background_task

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

import html
import json
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
import qtawesome as qta
from database_connection import connect_database
import sqlite3
from PySide6.QtCore import (
    Qt, QDate, QTime, QLocale, QObject, QThread, QTimer, Signal, Slot, QSize,
    QEvent,
    QMimeData, QPoint, QThreadPool,
)
from PySide6.QtGui import (
    QAction, QIcon, QFont, QColor, QBrush, QDrag, QPalette,
    QTextBlockFormat, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QAbstractButton,
    QVBoxLayout, QHBoxLayout,
    QStackedWidget, QGridLayout, QSplitter, QGroupBox, QDialog,
    QDialogButtonBox,
    QLabel, QLineEdit, QDateEdit, QCheckBox, QBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QMessageBox,
    QHeaderView, QAbstractItemView, QMenu, QToolButton, QScrollArea,
    QSizePolicy, QWidgetAction, QTextEdit, QPlainTextEdit, QSpinBox,
    QProgressBar, QTimeEdit, QFormLayout, QListWidget,
    QListWidgetItem, QListView, QComboBox, QInputDialog,
    QTabWidget,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
)
import sys


SCHOOL_INFO_DIALOG_FIELDS = [
    ("السنة الدراسية", "text", ""),
    ("المؤسسة", "text", ""),
    ("المعلم", "text", ""),
    ("المتفقد", "text", ""),
    ("اسم المساعد البيداغوجي", "text", ""),
    ("الرتبة", "text", ""),
    ("الشهادة العلمية", "text", ""),
    ("تاريخ الانتداب", "date", ""),
    ("تاريخ الترسيم", "date", ""),
    ("تاريخ الزيارة الأخيرة", "date", ""),
    ("العدد البيداغوجي المسند", "text", ""),
    ("خلاصة تقرير الزيارة", "plaintext", ""),
    ("اللغة", "text", ""),
    ("الهاتف", "text", ""),
    ("البريد الإلكتروني", "text", ""),
    ("الحالة العائلية", "text", ""),
    ("عدد الأطفال", "nonnegative_int", 0),
    ("المندوبية الجهوية للتربية بـ", "text", ""),
    ("دائرة التفقد", "text", ""),
    ("رمز المؤسسة", "text", ""),
    ("هاتف المؤسسة", "text", ""),
    ("مدير المدرسة", "text", ""),
    ("تاريخ الارتقاء إليها", "date", ""),
    ("متفقد التقرير البيداغوجي", "text", ""),
    ("المعرف الوحيد", "text", ""),
    ("البريد الإلكتروني للمتفقد", "text", ""),
    ("البريد الإلكتروني لمدير المدرسة", "text", ""),
    ("البريد الإلكتروني للمساعد البيداغوجي", "text", ""),
    ("عنوان المدرسة", "text", ""),
    ("الشهادة التكوينية", "text", ""),
    ("الجنس", "gender", ""),
]

SCHEDULED_LESSONS_MIME = "application/x-schoolplanner-scheduled-lessons+json"


class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


def _is_cultural_club_lesson(lesson):
    return len(lesson) > 6 and lesson[6] == "cultural_club"


def _split_scheduled_lessons(lessons):
    pedagogical_lessons = []
    club_lessons = []
    for lesson in lessons:
        target = (
            club_lessons
            if _is_cultural_club_lesson(lesson)
            else pedagogical_lessons
        )
        target.append(lesson)
    return pedagogical_lessons, club_lessons


def _decode_scheduled_lessons_drop(event, *, cultural_club_only=None):
    if not event.mimeData().hasFormat(SCHEDULED_LESSONS_MIME):
        return None
    try:
        lessons = json.loads(
            bytes(event.mimeData().data(SCHEDULED_LESSONS_MIME))
            .decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(lessons, list)
        or any(
            not isinstance(lesson, list) or len(lesson) < 4
            for lesson in lessons
        )
        or (
            cultural_club_only is not None
            and any(
                _is_cultural_club_lesson(lesson) != cultural_club_only
                for lesson in lessons
            )
        )
    ):
        return None
    return lessons


def _create_card_action_button(
    parent, tooltip, action, action_type, callback, item_id,
    enabled=True,
):
    button = QPushButton("", parent)
    button.setObjectName("cardActionButton")
    button.setFixedSize(25, 25)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    set_card_action_type(button, action_type)
    button.setEnabled(enabled)
    button.clicked.connect(
        lambda _checked=False: callback(action, item_id)
    )
    return button


def _configure_icon_button(button, standard_icon, accessible_name):
    button.setText("")
    button.setIcon(QApplication.style().standardIcon(standard_icon))
    button.setToolTip(accessible_name)
    button.setAccessibleName(accessible_name)


NAVIGATION_ICON_FILES = {
    "lesson_book": "nav_lesson_book.ico",
    "school_year": "nav_school_year.ico",
    "official_programs": "nav_official_programs.ico",
    "statistics": "nav_statistics.ico",
    "plans": "nav_plans.ico",
    "assessment": "nav_assessment.ico",
    "settings": "nav_settings.ico",
    "about": "nav_about.ico",
}


def _configure_navigation_icon(button, accessible_name, icon_filename):
    icon_path = Path(__file__).resolve().parent / "icons" / icon_filename
    icon = QIcon(str(icon_path))
    if icon.isNull():
        raise FileNotFoundError(
            f"تعذر تحميل أيقونة التنقل: {icon_path}"
        )
    button.setText("")
    button.setIcon(icon)
    action = button.defaultAction()
    if action is not None:
        action.setIcon(icon)
    button.setIconSize(QSize(44, 44))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setProperty("navigationIcon", True)
    button.setAutoRaise(False)
    button.setFixedSize(48, 48)
    button.setToolTip(accessible_name)
    button.setAccessibleName(accessible_name)


def _parse_hour_interval(value):
    cleaned = (
        str(value or "")
        .replace("ـ", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace(" ", "")
    )
    parts = cleaned.split("-")
    if len(parts) != 2:
        raise ValueError("صيغة ساعة التدريس غير صالحة.")
    try:
        start = datetime.strptime(parts[0], "%H:%M")
        end = datetime.strptime(parts[1], "%H:%M")
    except ValueError as exc:
        raise ValueError("صيغة ساعة التدريس غير صالحة.") from exc
    start_minute = start.hour * 60 + start.minute
    end_minute = end.hour * 60 + end.minute
    if end_minute <= start_minute:
        raise ValueError("وقت نهاية الحصة يجب أن يكون بعد بدايتها.")
    return start_minute, end_minute


def _default_detail_key(namat, details):
    if str(namat or "").strip() != "منهجي":
        return None
    if any(
        str(detail[1] or "").strip() == "هدف الحصة"
        for detail in details
    ):
        return None
    return "هدف الحصة"


def _has_unoccupied_work_time(
    lessons, work_start, work_end, excluded_lesson_id=None
):
    return bool(_unoccupied_work_intervals(
        lessons, work_start, work_end, excluded_lesson_id
    ))


def _unoccupied_work_intervals(
    lessons, work_start, work_end, excluded_lesson_id=None
):
    intervals = []
    for lesson in lessons:
        if excluded_lesson_id is not None and lesson[0] == excluded_lesson_id:
            continue
        start, end = _parse_hour_interval(lesson[4])
        start = max(start, work_start)
        end = min(end, work_end)
        if start < end:
            intervals.append((start, end))

    intervals.sort()
    cursor = work_start
    available = []
    for start, end in intervals:
        if start > cursor:
            available.append((cursor, start))
        cursor = max(cursor, end)
        if cursor >= work_end:
            break
    if cursor < work_end:
        available.append((cursor, work_end))
    return available


def _hour_interval_is_available(
    hour_interval, lessons, work_bounds=None, excluded_lesson_id=None
):
    start, end = _parse_hour_interval(hour_interval)
    if work_bounds is not None:
        work_start, work_end = work_bounds
        if start < work_start or end > work_end:
            return False
    for lesson in lessons:
        if excluded_lesson_id is not None and lesson[0] == excluded_lesson_id:
            continue
        occupied_start, occupied_end = _parse_hour_interval(lesson[4])
        if start < occupied_end and occupied_start < end:
            return False
    return True


def _manual_lesson_activity_names(recorded_lessons, scheduled_lessons):
    activities_by_slot = {}
    for lesson in scheduled_lessons:
        if len(lesson) <= 5 or not str(lesson[5] or "").strip():
            continue
        class_names = (
            lesson[7]
            if len(lesson) > 7 and lesson[6] == "cultural_club"
            else [lesson[0]]
        )
        for class_name in class_names:
            slot = (
                str(class_name or "").strip(),
                str(lesson[1] or "").strip(),
                _parse_hour_interval(lesson[2]),
            )
            activities_by_slot[slot] = str(lesson[5]).strip()

    activity_names = {}
    for lesson in recorded_lessons:
        slot = (
            str(lesson[2] or "").strip(),
            str(lesson[3] or "").strip(),
            _parse_hour_interval(lesson[4]),
        )
        activity_name = activities_by_slot.get(slot)
        if activity_name:
            activity_names[int(lesson[0])] = activity_name
    return activity_names


def _cultural_club_activity_title(title, class_name, clubs):
    def normalized_name(value):
        name = str(value or "").strip().casefold()
        for prefix in ("نادي ", "ناد "):
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        return name

    title_key = normalized_name(title)
    class_key = str(class_name or "").strip().casefold()
    if not title_key or not class_key:
        return None
    for club in clubs:
        club_name = str(club.get("name") or "").strip()
        section_names = {
            str(section.get("section_name") or "").strip().casefold()
            for section in club.get("sections", [])
        }
        if (
            title_key == normalized_name(club_name)
            and class_key in section_names
        ):
            club_type = str(club.get("club_type") or "").strip()
            return f"ناد — {club_type}\n{club_name}"
    return None


def _manual_lesson_cultural_club_details(
    recorded_lessons, heading_names, clubs
):
    def normalized_name(value):
        name = str(value or "").strip().casefold()
        for prefix in ("نادي ", "ناد "):
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        return name

    details_by_lesson = {}
    for lesson in recorded_lessons:
        lesson_id = int(lesson[0])
        heading_name = normalized_name(heading_names.get(lesson_id))
        class_name = str(lesson[2] or "").strip().casefold()
        domain = str(lesson[3] or "").strip().casefold()
        if not heading_name or not class_name:
            continue
        for club in clubs:
            club_name = str(club.get("name") or "").strip()
            club_type = str(club.get("club_type") or "").strip()
            section_names = {
                str(section.get("section_name") or "").strip().casefold()
                for section in club.get("sections", [])
            }
            if (
                heading_name == normalized_name(club_name)
                and class_name in section_names
                and domain == club_type.casefold()
            ):
                details_by_lesson[lesson_id] = {
                    "club_name": club_name,
                    "club_type": club_type,
                }
                break
    return details_by_lesson


def _scheduled_lesson_is_recorded(scheduled_lesson, recorded_lessons):
    is_cultural_club = (
        len(scheduled_lesson) > 7
        and scheduled_lesson[6] == "cultural_club"
    )
    if is_cultural_club:
        try:
            scheduled_slots = {
                (
                    str(class_name or "").strip(),
                    str(scheduled_lesson[1] or "").strip(),
                    _parse_hour_interval(scheduled_lesson[2]),
                )
                for class_name in scheduled_lesson[7]
            }
        except (IndexError, TypeError, ValueError):
            return False
        if not scheduled_slots:
            return False
        recorded_slots = set()
        for lesson in recorded_lessons:
            try:
                recorded_slots.add((
                    str(lesson[2] or "").strip(),
                    str(lesson[3] or "").strip(),
                    _parse_hour_interval(lesson[4]),
                ))
            except (IndexError, ValueError):
                continue
        return scheduled_slots.issubset(recorded_slots)

    try:
        scheduled_slot = (
            str(scheduled_lesson[0] or "").strip(),
            str(scheduled_lesson[1] or "").strip(),
            _parse_hour_interval(scheduled_lesson[2]),
        )
    except (IndexError, ValueError):
        return False

    for recorded_lesson in recorded_lessons:
        try:
            recorded_slot = (
                str(recorded_lesson[2] or "").strip(),
                str(recorded_lesson[3] or "").strip(),
                _parse_hour_interval(recorded_lesson[4]),
            )
        except (IndexError, ValueError):
            continue
        if recorded_slot == scheduled_slot:
            return True
    return False


def _new_clear_confirmation_code():
    return "-".join(
        f"{secrets.randbelow(10000):04d}" for _ in range(4)
    )


def _clear_confirmation_code_matches(entered_code, expected_code):
    entered = str(entered_code or "").replace("-", "").replace(" ", "")
    expected = str(expected_code or "").replace("-", "").replace(" ", "")
    return entered == expected


class ClearAllConfirmationDialog(QDialog):
    def __init__(self, confirmation_code, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تأكيد مسح جميع الحصص")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        instruction = QLabel(
            "هذا الإجراء سيمسح جميع الحصص والأنشطة والخصائص من قاعدة البيانات.\n"
            "اكتب الرمز التسلسلي التالي للتأكيد:"
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        code_label = QLabel(confirmation_code)
        code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        code_label.setStyleSheet(
            "font-size: 16pt; font-weight: 700; color: #B91C1C;"
            "padding: 8px;"
        )
        layout.addWidget(code_label)

        self.code_edit = QLineEdit()
        self.code_edit.setObjectName("clearAllConfirmationCodeEdit")
        self.code_edit.setInputMask("0000-0000-0000-0000;_")
        self.code_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_edit.setPlaceholderText("0000-0000-0000-0000")
        layout.addWidget(self.code_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("تأكيد المسح")
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setProperty("actionType", "clear")
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setEnabled(False)
        buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("إلغاء")
        self.code_edit.textChanged.connect(
            lambda _text: buttons.button(
                QDialogButtonBox.StandardButton.Ok
            ).setEnabled(self.code_edit.hasAcceptableInput())
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ScheduledLessonsListWidget(QListWidget):
    emptyCardActivated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._compact_mode = False
        self._normal_card_style_sheet = (
            "QListWidget { border: none; background: transparent; }"
            "QListWidget::item {"
            "background: #FFFFFF; border: 1px solid #CBD5E1;"
            "border-right: 4px solid #2563EB; border-radius: 9px;"
            "padding: 9px; color: #0F172A; }"
            "QListWidget::item:selected {"
            "background: #DBEAFE; border: 2px solid #2563EB; }"
        )
        self.setObjectName("scheduledLessonCards")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self._normal_spacing = 7
        self.setSpacing(self._normal_spacing)
        self.itemDoubleClicked.connect(self._activate_empty_card)
        self.setStyleSheet(self._normal_card_style_sheet)

    def set_compact_mode(self, compact):
        self._compact_mode = bool(compact)
        self.setSpacing(3 if self._compact_mode else self._normal_spacing)
        self.setStyleSheet(
            self._normal_card_style_sheet.replace(
                "padding: 9px;",
                f"padding: {3 if self._compact_mode else 9}px;",
            )
        )
        for row in range(self.count()):
            item = self.item(row)
            normal_size = item.data(Qt.UserRole + 1)
            if normal_size is None:
                continue
            width = (
                round(normal_size.width() * 0.8)
                if self._compact_mode else normal_size.width()
            )
            item.setSizeHint(QSize(width, normal_size.height()))
            card = self.itemWidget(item)
            if card is not None and card.layout() is not None:
                margins = (
                    (3, 1, 3, 1)
                    if self._compact_mode else (4, 2, 4, 2)
                )
                card.layout().setContentsMargins(*margins)

    @staticmethod
    def _lesson_sort_key(entry):
        hour_text = str(entry[2] or "").strip().replace("ـ", "-")
        start_text = hour_text.replace(" ", "").split("-", 1)[0]
        try:
            return 0, datetime.strptime(start_text, "%H:%M").time()
        except ValueError:
            return 1, datetime.max.time()

    def set_lessons(
        self, lessons, disabled_intervals=(), allow_manual_add=True,
        recorded_lessons=(), include_manual_card=True,
        warn_unrecorded=False, manual_card_text=None,
        recorded_exam_ids=(),
    ):
        self.clear()
        disabled_intervals = set(disabled_intervals)
        recorded_lessons = list(recorded_lessons)
        recorded_exam_ids = {
            int(exam_id) for exam_id in recorded_exam_ids
        }
        ordered_lessons = sorted(lessons, key=self._lesson_sort_key)
        for lesson in ordered_lessons:
            class_name, domain, hours, duration = (
                str(value or "").strip() for value in lesson[:4]
            )
            is_scheduled_exam = (
                len(lesson) > 7 and lesson[6] == "scheduled_exam"
            )
            is_cultural_club = (
                len(lesson) > 6 and lesson[6] == "cultural_club"
            )
            club_name = str(lesson[5] or "").strip() if is_cultural_club else ""
            heading = club_name if is_cultural_club else (
                f"تقييم {lesson[5]} · {class_name}"
                if is_scheduled_exam else f"{class_name} · {domain}"
            )
            lesson_text = (
                f"{heading}\n"
                f"{hours or 'التوقيت غير محدد'}  |  "
                f"{duration or 'المدة غير محددة'}"
            )
            item = QListWidgetItem()
            item.setData(Qt.UserRole, tuple(lesson))
            normal_size = QSize(220, 66)
            item.setData(Qt.UserRole + 1, normal_size)
            item.setSizeHint(
                QSize(
                    round(normal_size.width() * 0.8)
                    if self._compact_mode else normal_size.width(),
                    normal_size.height(),
                )
            )
            if is_cultural_club:
                tooltip = f"النادي: {club_name}\n"
            elif is_scheduled_exam:
                activities = "، ".join(
                    str(activity) for activity in lesson[8]
                )
                tooltip = (
                    f"القسم: {class_name}\nالمادة: {lesson[5]}\n"
                    f"الأنشطة: {activities}\n"
                    f"ساعة التقييم: {hours}\nالمدة: {duration}\n"
                    "اسحب البطاقة إلى دفتر اليوم أو انقر عليها مرتين "
                    "لإضافتها."
                )
            else:
                tooltip = f"القسم: {class_name}\nالمجال: {domain}\n" + (
                    f"ساعة العمل: {hours}\nالمدة: {duration}\n"
                    "اسحب البطاقة لإضافتها إلى دفتر اليوم."
                )
            item.setToolTip(tooltip)
            self.addItem(item)
            card = QWidget()
            card.setLayoutDirection(Qt.RightToLeft)
            card.setStyleSheet("background: transparent;")
            card_layout = QHBoxLayout(card)
            card_margins = (
                (3, 1, 3, 1)
                if self._compact_mode else (4, 2, 4, 2)
            )
            card_layout.setContentsMargins(*card_margins)
            card_layout.setSpacing(8)
            if is_scheduled_exam:
                is_missing = (
                    warn_unrecorded
                    and int(lesson[7]) not in recorded_exam_ids
                )
            else:
                is_missing = (
                    bool(recorded_lessons or warn_unrecorded)
                    and not _scheduled_lesson_is_recorded(
                        lesson, recorded_lessons
                    )
                )
            if is_missing:
                indicator = LessonStatusIndicator(
                    [
                        "حصة التقييم المبرمجة لم تُضف إلى دفتر اليوم."
                        if is_scheduled_exam else
                        "هذه الحصة المجدولة لم تُضف إلى حصص العمل."
                    ],
                    card,
                )
                indicator.setAccessibleName(
                    (
                        "تنبيه: حصة التقييم المبرمجة غير مضافة"
                        if is_scheduled_exam else
                        "تنبيه: الحصة المجدولة غير مضافة إلى حصص العمل"
                    )
                )
                card_layout.addWidget(indicator, 0, Qt.AlignVCenter)
            text_label = QLabel(lesson_text, card)
            text_label.setWordWrap(True)
            text_label.setToolTip(tooltip)
            text_label.setStyleSheet(
                "color: #0F172A; background: transparent; border: none;"
            )
            card_layout.addWidget(text_label, 1)
            self.setItemWidget(item, card)
            if _parse_hour_interval(hours) in disabled_intervals:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setToolTip("هذا التوقيت مشغول بحصة أخرى.")

        if include_manual_card:
            empty_item = QListWidgetItem(
                manual_card_text
                or "＋ حصة غير مبرمجة\nانقر مرتين لإدخالها يدويًا"
            )
            empty_item.setData(Qt.UserRole, None)
            normal_size = QSize(220, 58)
            empty_item.setData(Qt.UserRole + 1, normal_size)
            empty_item.setSizeHint(
                QSize(
                    round(normal_size.width() * 0.8)
                    if self._compact_mode else normal_size.width(),
                    normal_size.height(),
                )
            )
            empty_item.setForeground(QColor("#475569"))
            empty_item.setToolTip("إضافة حصة يدويًا خارج جدول الأوقات.")
            if not allow_manual_add:
                empty_item.setFlags(empty_item.flags() & ~Qt.ItemIsEnabled)
                empty_item.setToolTip(
                    "لا توجد فترة عمل شاغرة لإضافة حصة جديدة."
                )
            self.addItem(empty_item)
        elif not lessons:
            empty_item = QListWidgetItem(
                "لا توجد حصص مجدولة في هذه الفئة."
            )
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            normal_size = QSize(220, 54)
            empty_item.setData(Qt.UserRole + 1, normal_size)
            empty_item.setSizeHint(
                QSize(
                    round(normal_size.width() * 0.8)
                    if self._compact_mode else normal_size.width(),
                    normal_size.height(),
                )
            )
            self.addItem(empty_item)

    def has_missing_lesson_warnings(self):
        return any(
            label.accessibleName().startswith("تنبيه:")
            for row in range(self.count())
            if (card := self.itemWidget(self.item(row))) is not None
            for label in card.findChildren(QLabel)
        )

    def selected_lessons(self):
        return [
            item.data(Qt.UserRole)
            for item in self.selectedItems()
            if item.data(Qt.UserRole) is not None
        ]

    def _activate_empty_card(self, item):
        if item.data(Qt.UserRole) is None:
            self.emptyCardActivated.emit()

    def startDrag(self, supported_actions):
        lessons = self.selected_lessons()
        if not lessons:
            return
        mime_data = QMimeData()
        mime_data.setData(
            SCHEDULED_LESSONS_MIME,
            json.dumps(lessons, ensure_ascii=False).encode("utf-8"),
        )
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.CopyAction)


class RecordedLessonCardsWidget(QListWidget):
    actionRequested = Signal(str, int)
    lessonsDropped = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._compact_mode = False
        self._responsive_cards = []
        self.setObjectName("recordedLessonCards")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setGridSize(QSize(404, 176))
        self._normal_spacing = 4
        self.setSpacing(4)
        self._normal_card_style_sheet = (
            "QListWidget { border: none; background: transparent; }"
            "QListWidget::item { border: 1px solid transparent;"
            "border-radius: 12px; padding: 2px; }"
            "QListWidget::item:selected { background: #DBEAFE;"
            "border: 2px solid #60A5FA; }"
        )
        self.setStyleSheet(self._normal_card_style_sheet)

    def set_compact_mode(self, compact):
        self._compact_mode = bool(compact)
        self.setGridSize(
            QSize() if self._compact_mode else QSize(404, 176)
        )
        self.setSpacing(2 if self._compact_mode else self._normal_spacing)
        self.setStyleSheet(
            self._normal_card_style_sheet.replace(
                "padding: 2px;",
                f"padding: {0 if self._compact_mode else 2}px;",
            )
        )
        for card_controls in self._responsive_cards:
            self._apply_compact_mode_to_card(card_controls)

    def _apply_compact_mode_to_card(self, card_controls):
        for label, property_label in card_controls["properties"]:
            is_teaching_time = label == "ساعة التدريس"
            property_label.setVisible(
                not self._compact_mode or is_teaching_time
            )
            property_tooltip = (
                card_controls["hidden_properties_tooltip"]
                if self._compact_mode and is_teaching_time
                else ""
            )
            property_label.setToolTip(property_tooltip)
        for button in card_controls["action_buttons"]:
            button.setVisible(not self._compact_mode)
        card_controls["actions_menu_button"].setVisible(
            self._compact_mode
        )
        actions_menu = card_controls["actions_menu"]
        actions_menu.setProperty("smallProfile", self._compact_mode)
        actions_menu.style().unpolish(actions_menu)
        actions_menu.style().polish(actions_menu)
        actions_menu.update()
        card_controls["card"].setToolTip(
            card_controls["hidden_properties_tooltip"]
            if self._compact_mode else ""
        )
        progress_bar = card_controls["progress_bar"]
        if progress_bar is not None:
            progress_bar.setVisible(not self._compact_mode)
        self._apply_card_geometry(card_controls)

    def _apply_card_geometry(self, card_controls):
        card = card_controls["card"]
        card_layout = card_controls["card_layout"]
        item = card_controls["item"]
        normal_width = card_controls["normal_width"]
        if self._compact_mode:
            card.setMinimumSize(0, 0)
            card.setMaximumSize(16777215, 16777215)
            card_layout.setContentsMargins(5, 3, 5, 4)
            card_layout.setSpacing(3)
            card_controls["properties_layout"].setHorizontalSpacing(3)
            card_controls["properties_layout"].setVerticalSpacing(2)
            for property_label in card_controls["property_widgets"]:
                property_label.setMinimumHeight(24)
                property_label.setStyleSheet(
                    property_label.property("normalStyleSheet").replace(
                        "padding: 2px 5px;", "padding: 2px 3px;"
                    )
                )
            card.adjustSize()
            compact_width = min(
                normal_width,
                max(240, card.sizeHint().width()),
            )
            card.setFixedWidth(compact_width)
            height = max(76, card.sizeHint().height())
            card.setFixedHeight(height)
            item.setSizeHint(QSize(compact_width + 8, height + 8))
            return

        card.setFixedSize(normal_width, 160)
        card_layout.setContentsMargins(9, 7, 9, 8)
        card_layout.setSpacing(5)
        card_controls["properties_layout"].setHorizontalSpacing(7)
        card_controls["properties_layout"].setVerticalSpacing(4)
        for property_label in card_controls["property_widgets"]:
            property_label.setMinimumHeight(34)
            property_label.setStyleSheet(
                property_label.property("normalStyleSheet")
            )
        item.setSizeHint(QSize(396, 168))

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.itemAt(event.position().toPoint()) is None
        ):
            event.accept()
            return
        super().mousePressEvent(event)

    def set_lessons(
        self, lessons, heading_names=None, completion_issues=None,
        plan_progress=None, repeat_lesson_ids=None,
        repeat_lesson_statuses=None, cultural_club_details=None,
    ):
        self.clear()
        self._responsive_cards.clear()
        heading_names = heading_names or {}
        cultural_club_details = cultural_club_details or {}
        completion_issues = completion_issues or {}
        plan_progress = plan_progress or {}
        repeat_lesson_ids = set(int(lesson_id) for lesson_id in (repeat_lesson_ids or []))
        repeat_lesson_statuses = {
            int(lesson_id): status
            for lesson_id, status in (repeat_lesson_statuses or {}).items()
        }
        card_colors = (
            ("#EFF6FF", "#3B82F6", "#DBEAFE"),
            ("#ECFDF5", "#10B981", "#D1FAE5"),
            ("#FFFBEB", "#F59E0B", "#FEF3C7"),
            ("#F5F3FF", "#8B5CF6", "#EDE9FE"),
            ("#FDF2F8", "#EC4899", "#FCE7F3"),
            ("#ECFEFF", "#06B6D4", "#CFFAFE"),
            ("#FFF7ED", "#F97316", "#FFEDD5"),
            ("#F0FDF4", "#22C55E", "#DCFCE7"),
        )
        for index, lesson in enumerate(lessons):
            lesson_id, lesson_number, class_name, domain, hours, duration, unit, mode = lesson
            background, accent, property_background = card_colors[
                index % len(card_colors)
            ]
            item = QListWidgetItem()
            item.setData(Qt.UserRole, int(lesson_id))
            card = QFrame()
            card.setObjectName("recordedLessonCard")
            card.setFixedSize(388, 160)
            card.setStyleSheet(
                "QFrame#recordedLessonCard {"
                f"background: {background}; border: 1px solid {accent};"
                f"border-right: 5px solid {accent}; border-radius: 11px;"
                "}"
                "QLabel { border: none; background: transparent; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(9, 7, 9, 8)
            card_layout.setSpacing(5)
            heading_row = QHBoxLayout()
            heading_row.setSpacing(3)
            status_indicator = LessonStatusIndicator(
                completion_issues.get(int(lesson_id), []),
                card,
                repeat_requested=(
                    int(lesson_id) in repeat_lesson_ids
                    or int(lesson_id) in repeat_lesson_statuses
                ),
            )
            status_indicator.set_issues(
                completion_issues.get(int(lesson_id), []),
                repeat_applied=(
                    repeat_lesson_statuses.get(int(lesson_id)) == "applied"
                ),
            )
            heading_row.addWidget(status_indicator)
            heading_name = heading_names.get(int(lesson_id), domain)
            club_details = cultural_club_details.get(int(lesson_id))
            heading = QLabel(
                (
                    f"ناد — {club_details['club_type']}\n"
                    f"{club_details['club_name']}"
                )
                if club_details else
                f"{class_name or '—'} · {heading_name or domain or '—'}"
            )
            heading.setStyleSheet(
                f"font-size: 10pt; font-weight: 700; color: {accent};"
            )
            heading.setWordWrap(True)
            heading_row.addWidget(heading, 1)
            progress = plan_progress.get(int(lesson_id))
            progress_bar = None
            if progress:
                progress_lesson, total_lessons = progress
                percentage = min(
                    100, round(progress_lesson * 100 / total_lessons)
                )
                progress_bar = QProgressBar(card)
                progress_bar.setObjectName("recordedLessonPlanProgress")
                progress_bar.setRange(0, 100)
                progress_bar.setValue(percentage)
                progress_bar.setTextVisible(False)
                progress_bar.setFixedSize(72, 9)
                progress_bar.setAccessibleName(
                    f"تقدم المخطط: الحصة {progress_lesson} من "
                    f"{total_lessons}"
                )
                progress_bar.setToolTip(
                    f"الحصة {progress_lesson} من {total_lessons} "
                    f"({percentage}٪)"
                )
                progress_bar.setStyleSheet(
                    "QProgressBar { background: #DCFCE7;"
                    "border: 1px solid #86EFAC; border-radius: 4px;"
                    "padding: 0px; }"
                    "QProgressBar::chunk { background: #16A34A;"
                    "border-radius: 3px; }"
                )
                heading_row.addWidget(progress_bar)
            action_buttons = []
            action_specs = (
                ("تعديل الحصة", "edit", "edit"),
                ("نسخ الحصة", "copy", "copy_paste"),
                ("حذف الحصة", "delete", "delete"),
            )
            actions_menu_button = QToolButton(card)
            actions_menu_button.setObjectName("recordedLessonActionsMenu")
            actions_menu_button.setText("")
            actions_menu_button.setAccessibleName("إجراءات الحصة")
            actions_menu_button.setToolTip("إجراءات الحصة")
            actions_menu_button.setFixedSize(25, 25)
            actions_menu_button.setAutoRaise(True)
            actions_menu_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            set_action_button_type(actions_menu_button, "menu")
            actions_menu = QMenu(actions_menu_button)
            actions_menu.setObjectName("recordedLessonActionsPopup")
            actions_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            for tooltip, action, action_type in action_specs:
                button = _create_card_action_button(
                    card,
                    tooltip,
                    action,
                    action_type,
                    self.actionRequested.emit,
                    int(lesson_id),
                )
                heading_row.addWidget(button)
                action_buttons.append(button)
                menu_action = QAction(tooltip, actions_menu)
                menu_action.setIcon(button.icon())
                menu_action.triggered.connect(
                    lambda _checked=False, selected_action=action,
                    selected_lesson_id=int(lesson_id):
                    self.actionRequested.emit(
                        selected_action, selected_lesson_id
                    )
                )
                actions_menu.addAction(menu_action)
            actions_menu_button.setMenu(actions_menu)
            actions_menu_button.setPopupMode(
                QToolButton.ToolButtonPopupMode.InstantPopup
            )
            heading_row.addWidget(actions_menu_button)
            card_layout.addLayout(heading_row)

            properties = QGridLayout()
            properties.setObjectName("recordedLessonProperties")
            property_labels = []
            property_widgets = []
            properties.setHorizontalSpacing(7)
            properties.setVerticalSpacing(4)
            for index, (label, value) in enumerate((
                ("المجال", domain),
                ("ساعة التدريس", hours),
                ("التوقيت", duration),
                ("الوحدة", unit),
                ("عدد الحصة", lesson_number),
                ("نمط التعلم", mode),
            )):
                property_label = QLabel(
                    f"{label}: {value if value not in (None, '') else '—'}"
                )
                property_label.setWordWrap(False)
                property_label.setObjectName("recordedLessonProperty")
                property_label.setAlignment(Qt.AlignCenter)
                property_label.setMinimumHeight(34)
                property_label.setStyleSheet(
                    "color: #334155; "
                    f"background: {property_background};"
                    "border-radius: 5px; padding: 2px 5px; font-size: 9pt;"
                )
                property_label.setProperty(
                    "normalStyleSheet", property_label.styleSheet()
                )
                properties.addWidget(property_label, index // 2, index % 2)
                property_labels.append((label, property_label))
                property_widgets.append(property_label)
            card_layout.addLayout(properties)
            hidden_properties_tooltip = "\n".join(
                f"{label}: {value if value not in (None, '') else '—'}"
                for label, value in (
                    ("المجال", domain),
                    ("التوقيت", duration),
                    ("الوحدة", unit),
                    ("عدد الحصة", lesson_number),
                    ("نمط التعلم", mode),
                )
            )
            self.addItem(item)
            self.setItemWidget(item, card)
            card_controls = {
                "card": card,
                "item": item,
                "card_layout": card_layout,
                "normal_width": 388,
                "properties": property_labels,
                "property_widgets": property_widgets,
                "properties_layout": properties,
                "action_buttons": action_buttons,
                "actions_menu_button": actions_menu_button,
                "actions_menu": actions_menu,
                "progress_bar": progress_bar,
                "hidden_properties_tooltip": hidden_properties_tooltip,
            }
            self._responsive_cards.append(card_controls)
            self._apply_compact_mode_to_card(card_controls)

    def select_lesson(self, lesson_id):
        self.clearSelection()
        if lesson_id is None:
            self.setCurrentItem(None)
            return
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.UserRole) == int(lesson_id):
                item.setSelected(True)
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return

    def selected_lesson_ids(self):
        return [
            int(item.data(Qt.UserRole))
            for item in self.selectedItems()
            if item.data(Qt.UserRole) is not None
        ]

    def dragEnterEvent(self, event):
        if _decode_scheduled_lessons_drop(
            event, cultural_club_only=False
        ) is not None:
            self._set_drop_target_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if _decode_scheduled_lessons_drop(
            event, cultural_club_only=False
        ) is not None:
            self._set_drop_target_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_target_active(False)
        event.accept()

    def dropEvent(self, event):
        lessons = _decode_scheduled_lessons_drop(
            event, cultural_club_only=False
        )
        self._set_drop_target_active(False)
        if lessons is None:
            event.ignore()
            return
        self.lessonsDropped.emit(lessons)
        event.acceptProposedAction()

    def _set_drop_target_active(self, active):
        background = "#DBEAFE" if active else "transparent"
        border = "#2563EB" if active else "transparent"
        self.setStyleSheet(
            "QListWidget {"
            f"background:{background}; border:2px solid {border};"
            "border-radius:10px; }"
            "QListWidget::item { border:1px solid transparent;"
            "border-radius:12px; padding:2px; }"
            "QListWidget::item:selected { background:#DBEAFE;"
            "border:2px solid #60A5FA; }"
        )


class CulturalClubDailySessionEditDialog(QDialog):
    def __init__(
        self, session, parent=None, clubs=None, allow_repeat=False,
        repeat_requested=False, repeat_reason="",
    ):
        super().__init__(parent)
        self.setWindowTitle(
            "إضافة حصة نادٍ غير مبرمجة"
            if clubs is not None else "تعديل جلسة النادي"
        )
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.club_combo = None
        if clubs is not None:
            self.club_combo = QComboBox(self)
            for club in clubs:
                self.club_combo.addItem(
                    str(club["name"]), int(club["id"])
                )
            form.addRow("النادي:", self.club_combo)
        start_text, _, end_text = str(
            session.get("hour_interval") or ""
        ).partition("-")
        self.start_time = QTimeEdit(
            QTime.fromString(start_text.strip(), "HH:mm")
        )
        self.end_time = QTimeEdit(
            QTime.fromString(end_text.strip(), "HH:mm")
        )
        self.start_time.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.end_time.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.start_time.setDisplayFormat("HH:mm")
        self.end_time.setDisplayFormat("HH:mm")
        form.addRow("وقت البداية:", self.start_time)
        form.addRow("وقت النهاية:", self.end_time)
        layout.addLayout(form)

        self.properties_table = QTableWidget(
            len(session.get("properties") or []), 2, self
        )
        self.properties_table.setHorizontalHeaderLabels([
            "اسم الخاصية", "القيمة",
        ])
        self.properties_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.properties_table.verticalHeader().setVisible(False)
        self.properties_table.setMinimumHeight(140)
        self.properties_table.cellDoubleClicked.connect(
            self._edit_property_value
        )
        for row, prop in enumerate(session.get("properties") or []):
            self.properties_table.setItem(
                row, 0, QTableWidgetItem(str(prop.get("key_name") or ""))
            )
            value_item = QTableWidgetItem(
                str(prop.get("value_text") or "")
            )
            value_item.setFlags(
                value_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.properties_table.setItem(row, 1, value_item)
        layout.addWidget(QLabel("توابع الجلسة:"))
        layout.addWidget(self.properties_table)

        property_actions = QHBoxLayout()
        add_property_button = QPushButton("إضافة خاصية")
        add_property_button.clicked.connect(self._add_property)
        remove_property_button = QPushButton("حذف الخاصية المحددة")
        remove_property_button.clicked.connect(self._remove_properties)
        property_actions.addWidget(add_property_button)
        property_actions.addWidget(remove_property_button)
        layout.addLayout(property_actions)

        self.repeat_checkbox = QCheckBox(
            "إعادة خصائص الحصة في الجلسة الشهرية التالية للنادي"
        )
        self.repeat_checkbox.setVisible(allow_repeat)
        self.repeat_checkbox.setChecked(repeat_requested)
        self.repeat_checkbox.toggled.connect(self._toggle_repeat_fields)
        layout.addWidget(self.repeat_checkbox)

        self.repeat_reason_label = QLabel("سبب إعادة الحصة:")
        self.repeat_reason_edit = QLineEdit(str(repeat_reason or ""))
        self.repeat_reason_edit.setPlaceholderText(
            "غير مكتملة / طارئ / لم تنجح"
        )
        self.repeat_reason_row = QWidget(self)
        repeat_reason_layout = QHBoxLayout(self.repeat_reason_row)
        repeat_reason_layout.setContentsMargins(0, 0, 0, 0)
        repeat_reason_layout.addWidget(self.repeat_reason_label)
        repeat_reason_layout.addWidget(self.repeat_reason_edit, 1)
        layout.addWidget(self.repeat_reason_row)
        self.confirm_repeat_checkbox = QCheckBox(
            "أؤكد إعادة خصائص الحصة إلى الجلسة الشهرية التالية"
        )
        self.confirm_repeat_checkbox.setChecked(repeat_requested)
        layout.addWidget(self.confirm_repeat_checkbox)
        self._toggle_repeat_fields(repeat_requested)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Save
        ).setText("حفظ")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_club_id(self):
        if self.club_combo is None:
            return None
        return self.club_combo.currentData()

    def _add_property(self):
        row = self.properties_table.rowCount()
        self.properties_table.insertRow(row)
        self.properties_table.setItem(row, 0, QTableWidgetItem(""))
        value_item = QTableWidgetItem("")
        value_item.setFlags(
            value_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self.properties_table.setItem(row, 1, value_item)
        self.properties_table.setCurrentCell(row, 0)
        self.properties_table.editItem(self.properties_table.item(row, 0))

    def _edit_property_value(self, row, column):
        if column != 1:
            return
        value_item = self.properties_table.item(row, column)
        if value_item is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("تعديل قيمة الخاصية")
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(dialog)
        editor.setPlainText(value_item.text())
        current_alignment = (
            editor.document().defaultTextOption().alignment()
        )
        target_alignment = (
            Qt.AlignmentFlag.AlignRight
            if current_alignment & Qt.AlignmentFlag.AlignLeft
            else Qt.AlignmentFlag.AlignLeft
        )
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        block_format.setAlignment(target_alignment)
        cursor.mergeBlockFormat(block_format)
        editor.setTextCursor(cursor)
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        editor.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        editor.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        editor.setFixedHeight(
            editor.fontMetrics().lineSpacing() * 5
            + editor.contentsMargins().top()
            + editor.contentsMargins().bottom()
            + 12
        )
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Save
        ).setText("حفظ")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            value_item.setText(editor.toPlainText())

    def _remove_properties(self):
        selected_rows = {
            index.row() for index in self.properties_table.selectedIndexes()
        }
        if self.properties_table.currentRow() >= 0:
            selected_rows.add(self.properties_table.currentRow())
        selected_rows = sorted(selected_rows, reverse=True)
        for row in selected_rows:
            self.properties_table.removeRow(row)

    def values(self):
        start = self.start_time.time()
        end = self.end_time.time()
        duration = start.msecsTo(end) // 60000
        interval = (
            f"{start.toString('HH:mm')} - {end.toString('HH:mm')}"
        )
        properties = []
        for row in range(self.properties_table.rowCount()):
            key_item = self.properties_table.item(row, 0)
            value_item = self.properties_table.item(row, 1)
            properties.append({
                "key_name": key_item.text() if key_item else "",
                "value_text": value_item.text() if value_item else "",
            })
        return interval, duration, properties

    def repeat_values(self):
        return (
            self.repeat_checkbox.isChecked(),
            self.repeat_reason_edit.text().strip(),
        )

    def _toggle_repeat_fields(self, checked):
        self.repeat_reason_row.setVisible(checked)
        self.confirm_repeat_checkbox.setVisible(checked)

    def _accept_if_valid(self):
        interval, duration, properties = self.values()
        if duration not in (60, 120):
            QMessageBox.warning(
                self, "مدة غير صالحة",
                "يجب أن تكون مدة جلسة النادي 60 أو 120 دقيقة.",
            )
            return
        try:
            _parse_hour_interval(interval)
        except ValueError:
            QMessageBox.warning(
                self, "توقيت غير صالح",
                "يجب أن يكون وقت النهاية بعد وقت البداية.",
            )
            return
        if self.club_combo is not None and self.club_combo.currentIndex() < 0:
            QMessageBox.warning(
                self, "النادي غير محدد", "اختر النادي المراد إضافته."
            )
            return
        if any(not prop["key_name"].strip() for prop in properties):
            QMessageBox.warning(
                self, "خاصية غير مكتملة",
                "أدخل اسم الخاصية أو احذف السطر الفارغ.",
            )
            return
        repeat_requested, repeat_reason = self.repeat_values()
        if repeat_requested and not repeat_reason:
            QMessageBox.warning(
                self, "سبب الإعادة مطلوب",
                "أدخل سبب إعادة حصة النادي.",
            )
            return
        if (
            repeat_requested
            and not self.confirm_repeat_checkbox.isChecked()
        ):
            QMessageBox.warning(
                self, "تأكيد الإعادة مطلوب",
                "أكد إعادة خصائص الحصة إلى الجلسة الشهرية التالية.",
            )
            return
        self.accept()


class CulturalClubDailySessionDetailsDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle("الاطلاع على حصة النادي")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(560, 520)
        layout = QVBoxLayout(self)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        content = QWidget(scroll_area)
        content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        content_layout = QVBoxLayout(content)

        details = QFormLayout()
        for label, key in (
            ("النادي:", "club_name"),
            ("النوع:", "club_type"),
            ("التاريخ:", "session_date"),
            ("التوقيت:", "hour_interval"),
            ("المدة:", "duration_minutes"),
            ("عدد المشاركين:", "participant_count"),
            ("عدد الحاضرين:", "present_count"),
            ("عدد الغائبين:", "absent_count"),
        ):
            value = session.get(key)
            if key == "duration_minutes":
                value = f"{value or '—'} دقيقة"
            details.addRow(label, QLabel(str(value or "—"), content))
        content_layout.addLayout(details)

        sections = session.get("sections") or []
        if sections:
            content_layout.addWidget(QLabel("الأقسام والمشاركون:", content))
            sections_table = QTableWidget(len(sections), 3, content)
            sections_table.setHorizontalHeaderLabels([
                "القسم", "بنات", "بنون",
            ])
            sections_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            sections_table.verticalHeader().setVisible(False)
            sections_table.setEditTriggers(
                QAbstractItemView.EditTrigger.NoEditTriggers
            )
            for row, section in enumerate(sections):
                for column, key in enumerate((
                    "section_name", "female_count", "male_count",
                )):
                    sections_table.setItem(
                        row, column,
                        QTableWidgetItem(str(section.get(key) or 0)),
                    )
            sections_table.setFixedHeight(
                sections_table.horizontalHeader().height()
                + sections_table.verticalHeader().defaultSectionSize()
                * len(sections)
                + 4
            )
            content_layout.addWidget(sections_table)

        properties = session.get("properties") or []
        content_layout.addWidget(QLabel("خصائص الحصة:", content))
        properties_table = QTableWidget(len(properties), 2, content)
        properties_table.setHorizontalHeaderLabels([
            "اسم الخاصية", "القيمة",
        ])
        properties_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        properties_table.verticalHeader().setVisible(False)
        properties_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        for row, prop in enumerate(properties):
            properties_table.setItem(
                row, 0,
                QTableWidgetItem(str(prop.get("key_name") or "—")),
            )
            properties_table.setItem(
                row, 1,
                QTableWidgetItem(str(prop.get("value_text") or "—")),
            )
        properties_table.setFixedHeight(
            properties_table.horizontalHeader().height()
            + properties_table.verticalHeader().defaultSectionSize()
            * max(1, len(properties))
            + 4
        )
        content_layout.addWidget(properties_table)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=self
        )
        buttons.rejected.connect(self.reject)
        buttons.button(
            QDialogButtonBox.StandardButton.Close
        ).clicked.connect(self.accept)
        layout.addWidget(buttons)


def _position_cultural_club_plan_progress(card):
    progress_bar = card.findChild(
        QProgressBar, "culturalClubPlanProgress"
    )
    title = card.findChild(QLabel, "culturalClubSessionTitle")
    if progress_bar is None or title is None:
        return
    left = 8 + 3 * 36
    right = title.x() - 8
    progress_bar.setGeometry(
        left,
        title.y() + (title.height() - progress_bar.height()) // 2,
        max(0, right - left),
        progress_bar.height(),
    )
    progress_bar.raise_()


class CulturalClubSessionCard(QFrame):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout() is not None:
            self.layout().activate()
        _position_cultural_club_plan_progress(self)


class CulturalClubSessionCardsWidget(QListWidget):
    actionRequested = Signal(str, int)
    lessonsDropped = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._compact_mode = False
        self._responsive_sessions = []
        self.setObjectName("culturalClubSessionCards")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setViewMode(QListView.ListMode)
        self._normal_spacing = 8
        self.setSpacing(8)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._normal_card_style_sheet = (
            "QListWidget { border: none; background: transparent; }"
            "QListWidget::item { border: 1px solid transparent;"
            "border-radius: 12px; padding: 2px; }"
            "QListWidget::item:selected { background: #EDE9FE;"
            "border: 2px solid #A78BFA; }"
        )
        self.setStyleSheet(self._normal_card_style_sheet)

    def set_compact_mode(self, compact):
        self._compact_mode = bool(compact)
        self.setSpacing(3 if self._compact_mode else self._normal_spacing)
        self.setStyleSheet(
            self._normal_card_style_sheet.replace(
                "padding: 2px;",
                f"padding: {0 if self._compact_mode else 2}px;",
            )
        )
        for controls in self._responsive_sessions:
            self._apply_compact_mode_to_session(controls)
        for row in range(self.count()):
            item = self.item(row)
            card = self.itemWidget(item)
            if card is not None:
                self._resize_card_item(item, card)

    def _apply_compact_mode_to_session(self, controls):
        controls["metadata"].setVisible(not self._compact_mode)
        controls["compact_time"].setVisible(self._compact_mode)
        controls["actions_menu_button"].setVisible(self._compact_mode)
        actions_menu = controls["actions_menu"]
        actions_menu.setProperty("smallProfile", self._compact_mode)
        actions_menu.style().unpolish(actions_menu)
        actions_menu.style().polish(actions_menu)
        actions_menu.update()
        for button in controls["action_buttons"]:
            button.setVisible(not self._compact_mode)
        progress_bar = controls["progress_bar"]
        if progress_bar is not None:
            progress_bar.setVisible(not self._compact_mode)
        card = controls["card"]
        card.setToolTip(
            controls["hidden_details_tooltip"]
            if self._compact_mode else ""
        )

    def set_sessions(self, sessions):
        self.clear()
        self._responsive_sessions.clear()
        if not sessions:
            empty_item = QListWidgetItem(
                "اسحب بطاقة حصة نادٍ مجدولة إلى هنا لإضافتها لهذا اليوم."
            )
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setSizeHint(QSize(420, 54))
            self.addItem(empty_item)
            return

        for session in sessions:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, session.get("id"))
            card = CulturalClubSessionCard()
            card.setObjectName("culturalClubSessionCard")
            card.setStyleSheet(
                "QFrame#culturalClubSessionCard {"
                "background:#FFFFFF; border:1px solid #DDD6FE;"
                "border-right:5px solid #7C3AED; border-radius:12px;"
                "}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 14)
            card_layout.setSpacing(8)

            action_buttons = [
                self._create_session_action_button(
                    card, session, "delete", "مسح حصة النادي", 0
                ),
                self._create_session_action_button(
                    card, session, "edit", "تعديل حصة النادي", 1
                ),
                self._create_session_action_button(
                    card, session, "browse", "إطلاع على حصص النادي", 2
                ),
            ]

            title = QLabel(
                f"نادي {session.get('club_name') or '—'}"
            )
            title.setObjectName("culturalClubSessionTitle")
            title.setStyleSheet(
                "color:#6D28D9; font-size:12pt; font-weight:700;"
                "background:transparent; border:none;"
            )
            heading_row = QHBoxLayout()
            heading_row.setSpacing(6)
            title.setAlignment(Qt.AlignmentFlag.AlignRight)
            heading_row.addWidget(title)
            heading_row.addStretch(1)
            actions_menu_button = QToolButton(card)
            actions_menu_button.setObjectName(
                "culturalClubActionsMenu"
            )
            actions_menu_button.setText("")
            actions_menu_button.setAccessibleName("إجراءات حصة النادي")
            actions_menu_button.setToolTip("إجراءات حصة النادي")
            actions_menu_button.setFixedSize(25, 25)
            actions_menu_button.setAutoRaise(True)
            actions_menu_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            set_action_button_type(actions_menu_button, "menu")
            actions_menu = QMenu(actions_menu_button)
            actions_menu.setObjectName("culturalClubActionsPopup")
            actions_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            for button in action_buttons:
                action = QAction(button.accessibleName(), actions_menu)
                action.setIcon(button.icon())
                action.triggered.connect(button.click)
                actions_menu.addAction(action)
            actions_menu_button.setMenu(actions_menu)
            actions_menu_button.setPopupMode(
                QToolButton.ToolButtonPopupMode.InstantPopup
            )
            heading_row.addWidget(actions_menu_button)
            plan_session_number = session.get("plan_session_number")
            plan_session_count = session.get("plan_session_count")
            progress_bar = None
            if (
                plan_session_number is not None
                and plan_session_count
                and plan_session_count > 0
            ):
                percentage = min(
                    100,
                    round(plan_session_number * 100 / plan_session_count),
                )
                progress_bar = QProgressBar(card)
                progress_bar.setObjectName(
                    "culturalClubPlanProgress"
                )
                progress_bar.setRange(0, 100)
                progress_bar.setValue(percentage)
                progress_bar.setTextVisible(False)
                progress_bar.setFixedHeight(9)
                progress_bar.setMinimumWidth(0)
                progress_bar.setSizePolicy(
                    QSizePolicy.Policy.Ignored,
                    QSizePolicy.Policy.Fixed,
                )
                progress_bar.setAccessibleName(
                    f"تقدم المخطط: الحصة {plan_session_number} من "
                    f"{plan_session_count}"
                )
                progress_bar.setToolTip(
                    f"الحصة {plan_session_number} من "
                    f"{plan_session_count} ({percentage}٪)"
                )
                progress_bar.setStyleSheet(
                    "QProgressBar { background:#DCFCE7;"
                    "border:1px solid #86EFAC; border-radius:4px;"
                    "padding:0px; }"
                    "QProgressBar::chunk { background:#16A34A;"
                    "border-radius:3px; }"
                )
            card_layout.addLayout(heading_row)

            metadata = QLabel(
                f"النوع: {session.get('club_type') or '—'}  |  "
                f"التوقيت: {session.get('hour_interval') or '—'}  |  "
                f"المدة: {session.get('duration_minutes') or '—'} دقيقة"
            )
            metadata.setWordWrap(True)
            metadata.setStyleSheet(
                "color:#334155; background:#F5F3FF;"
                "border:1px solid #DDD6FE; border-radius:7px; padding:7px;"
            )
            card_layout.addWidget(metadata)
            compact_time = QLabel(
                f"التوقيت: {session.get('hour_interval') or '—'}"
            )
            compact_time.setObjectName("culturalClubCompactTime")
            compact_time.setAccessibleName("توقيت حصة النادي")
            compact_time.setWordWrap(True)
            compact_time.setStyleSheet(
                "color:#334155; background:#F5F3FF;"
                "border:1px solid #DDD6FE; border-radius:7px; padding:3px;"
            )
            card_layout.addWidget(compact_time)

            hidden_details = [
                f"النوع: {session.get('club_type') or '—'}",
                f"المدة: {session.get('duration_minutes') or '—'} دقيقة",
            ]
            hidden_details.extend(
                f"{prop.get('key_name') or '—'}: "
                f"{prop.get('value_text') or '—'}"
                for prop in session.get("properties") or []
            )

            self.addItem(item)
            self.setItemWidget(item, card)
            card.setMinimumWidth(0)
            controls = {
                "item": item,
                "card": card,
                "card_layout": card_layout,
                "title": title,
                "metadata": metadata,
                "compact_time": compact_time,
                "action_buttons": action_buttons,
                "actions_menu_button": actions_menu_button,
                "actions_menu": actions_menu,
                "progress_bar": progress_bar,
                "hidden_details_tooltip": "\n".join(hidden_details),
            }
            card._responsive_controls = controls
            self._responsive_sessions.append(controls)
            self._apply_compact_mode_to_session(controls)
            self._resize_card_item(item, card)

    def _create_session_action_button(
        self, card, session, action, tooltip, index
    ):
        button = QToolButton(card)
        button.setObjectName(f"culturalClubSession{action.title()}Button")
        set_card_action_type(button, f"card_{action}")
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(30, 30)
        button.clicked.connect(
            lambda _checked=False, requested_action=action,
            session_id=int(session["id"]):
            self.actionRequested.emit(requested_action, session_id)
        )
        button.move(8 + index * 36, 8)
        button.raise_()
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for row in range(self.count()):
            item = self.item(row)
            card = self.itemWidget(item)
            if card is not None:
                self._resize_card_item(item, card)
                controls = getattr(card, "_responsive_controls", None)
                if controls is not None:
                    for index, button in enumerate(
                        controls["action_buttons"]
                    ):
                        button.move(8 + index * 36, 8)
                        button.raise_()

    def _resize_card_item(self, item, card):
        available_width = max(100, self.viewport().width() - 8)
        width = (
            max(200, round(available_width * 0.8))
            if self._compact_mode else available_width
        )
        width = min(width, available_width)
        card.setFixedWidth(width)
        card_layout = card.layout()
        if self._compact_mode:
            card_layout.setContentsMargins(5, 3, 5, 4)
            card_layout.setSpacing(3)
        else:
            card_layout.setContentsMargins(14, 12, 14, 14)
            card_layout.setSpacing(8)
        card.adjustSize()
        card.layout().activate()
        _position_cultural_club_plan_progress(card)
        height = card.sizeHint().height()
        if self._compact_mode:
            card.setFixedHeight(height)
        item.setSizeHint(QSize(width + 8, height + 8))

    def has_sessions(self):
        return any(
            self.item(row).data(Qt.ItemDataRole.UserRole) is not None
            for row in range(self.count())
        )

    def dragEnterEvent(self, event):
        if _decode_scheduled_lessons_drop(
            event, cultural_club_only=True
        ) is not None:
            self._set_drop_target_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if _decode_scheduled_lessons_drop(
            event, cultural_club_only=True
        ) is not None:
            self._set_drop_target_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_target_active(False)
        event.accept()

    def dropEvent(self, event):
        lessons = _decode_scheduled_lessons_drop(
            event, cultural_club_only=True
        )
        self._set_drop_target_active(False)
        if lessons is None:
            event.ignore()
            return
        self.lessonsDropped.emit(lessons)
        event.acceptProposedAction()

    def _set_drop_target_active(self, active):
        background = "#EDE9FE" if active else "transparent"
        border = "#7C3AED" if active else "transparent"
        self.setStyleSheet(
            "QListWidget {"
            f"background:{background}; border:2px solid {border};"
            "border-radius:10px; }"
            "QListWidget::item { border:1px solid transparent;"
            "border-radius:12px; padding:2px; }"
            "QListWidget::item:selected { background:#EDE9FE;"
            "border:2px solid #A78BFA; }"
        )
        card_background = "#EDE9FE" if active else "#FFFFFF"
        card_border = "#7C3AED" if active else "#DDD6FE"
        for row in range(self.count()):
            card = self.itemWidget(self.item(row))
            if card is not None:
                card.setStyleSheet(
                    "QFrame#culturalClubSessionCard {"
                    f"background:{card_background};"
                    f"border:1px solid {card_border};"
                    "border-right:5px solid #7C3AED;"
                    "border-radius:12px; }"
                )

    def set_read_only(self, read_only):
        for row in range(self.count()):
            card = self.itemWidget(self.item(row))
            if card is None:
                continue
            for button in card.findChildren(QToolButton):
                button.setEnabled(not read_only)


class LessonStatusIndicator(QLabel):
    def __init__(self, issues, parent=None, item_type="الحصة", repeat_requested=False):
        super().__init__(parent)
        self.item_type = item_type
        self.issues = list(issues)
        self.repeat_requested = bool(repeat_requested)
        self.repeat_applied = False
        self._warning_visible = True
        self.setFixedSize(22, 22)
        self.setObjectName("lessonStatusIndicator")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: none; background: transparent;")
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_warning)
        self.set_issues(issues)

    def _status_text(self, complete):
        if self.item_type == "النشاط":
            return "النشاط مكتمل" if complete else "تنبيه: النشاط غير مكتمل"
        if self.repeat_requested:
            if self.repeat_applied:
                return "تمت إعادة الحصة"
            return "الحصة ستُعاد في المرة القادمة"
        return "الحصة مكتملة" if complete else "تنبيه: توجد مشكلة في الحصة"

    def _status_tooltip(self, complete):
        if self.repeat_requested:
            if self.repeat_applied:
                return "تمت إعادة الحصة."
            if complete:
                return "تمت الموافقة على إعادة هذه الحصة في المرة القادمة."
            return (
                "تمت الموافقة على إعادة هذه الحصة في المرة القادمة، "
                "وتوجد مشكلات تحتاج إلى استكمال:\n• "
                + "\n• ".join(self.issues)
            )
        if complete:
            if self.item_type == "النشاط":
                return "النشاط مكتمل: البيانات المطلوبة موجودة."
            return (
                "الحصة سليمة: مدد الأنشطة مكتملة والبيانات المطلوبة موجودة."
            )
        subject = "النشاط يحتاج إلى استكمال" if self.item_type == "النشاط" else "الحصة تحتاج إلى استكمال"
        return subject + ":\n• " + "\n• ".join(self.issues)

    def set_issues(self, issues, repeat_requested=None, repeat_applied=None):
        if repeat_requested is not None:
            self.repeat_requested = bool(repeat_requested)
        if repeat_applied is not None:
            self.repeat_applied = bool(repeat_applied)
        self.issues = list(issues)
        if self.repeat_requested and self.item_type == "الحصة":
            self._blink_timer.stop()
            self._warning_visible = True
            self.setText("↻")
            self.setToolTip(self._status_tooltip(not self.issues))
            self.setAccessibleName(self._status_text(not self.issues))
            self.setStyleSheet(
                "QLabel { color: white; background: "
                f"{'#16A34A' if self.repeat_applied else '#2563EB'};"
                f"border: 1px solid {'#15803D' if self.repeat_applied else '#1D4ED8'};"
                "border-radius: 11px;"
                "font-weight: 700; font-size: 13px; }"
            )
            return
        if self.issues:
            self.setText("!")
            self.setToolTip(self._status_tooltip(False))
            self.setAccessibleName(self._status_text(False))
            self._warning_visible = True
            self._apply_warning_style()
            if not self._blink_timer.isActive():
                self._blink_timer.start()
            return

        self._blink_timer.stop()
        self._warning_visible = True
        self.setText("✓")
        self.setToolTip(self._status_tooltip(True))
        self.setAccessibleName(self._status_text(True))
        self.setStyleSheet(
            "QLabel { color: white; background: #16A34A;"
            "border: 1px solid #15803D; border-radius: 11px;"
            "font-weight: 700; font-size: 13px; }"
        )

    def _apply_warning_style(self):
        background = "#F97316" if self._warning_visible else "#FFEDD5"
        foreground = "white" if self._warning_visible else "#C2410C"
        self.setStyleSheet(
            "QLabel {"
            f"color: {foreground}; background: {background};"
            "border: 1px solid #EA580C; border-radius: 11px;"
            "font-weight: 700; font-size: 14px;"
            "}"
        )

    def _toggle_warning(self):
        self._warning_visible = not self._warning_visible
        self._apply_warning_style()


def _school_info_to_dialog_values(values):
    return list(values[:4]) + [values[5], values[4]] + list(values[6:])


def _school_info_from_dialog_values(values):
    return list(values[:4]) + [values[5], values[4]] + list(values[6:])


def _navigation_widget_text(widget):
    if isinstance(widget, QGroupBox):
        return widget.title()
    return widget.text()


def _normalize_navigation_match_character(character):
    normalized = unicodedata.normalize("NFKC", character).casefold()
    normalized_text = []
    for normalized_part in normalized:
        if normalized_part == "ـ" or "\u064b" <= normalized_part <= "\u065f":
            continue
        normalized_text.append(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ى": "ي",
                "ة": "ه",
            }.get(normalized_part, normalized_part)
        )
    return "".join(normalized_text)


def _navigation_search_ranges(text, query):
    normalized_text = []
    source_positions = []
    for source_index, character in enumerate(str(text or "")):
        for normalized_part in _normalize_navigation_match_character(
            character
        ):
            normalized_text.append(normalized_part)
            source_positions.append(source_index)

    normalized_text = "".join(normalized_text)
    normalized_query = "".join(
        _normalize_navigation_match_character(character)
        for character in str(query or "")
    )
    query_terms = set(re.findall(r"\w+", normalized_query))
    ranges = []
    for term in query_terms:
        if not term:
            continue
        start = normalized_text.find(term)
        while start >= 0:
            end = start + len(term)
            ranges.append(
                (source_positions[start], source_positions[end - 1] + 1)
            )
            start = normalized_text.find(term, start + 1)

    merged_ranges = []
    for start, end in sorted(set(ranges)):
        if merged_ranges and start <= merged_ranges[-1][1]:
            merged_ranges[-1] = (
                merged_ranges[-1][0], max(merged_ranges[-1][1], end)
            )
        else:
            merged_ranges.append((start, end))
    return merged_ranges


class _NavigationSearchMatchController:
    _BACKGROUND = "#FFF176"
    _ACTIVE_BACKGROUND = "#FFD54F"

    def __init__(self, page, query, result_title=""):
        self.page = page
        self.query = query
        self.matches = []
        self.index = -1
        self.bar = None
        self._label_text = {}
        self._editor_selections = {}
        self._line_edit_palettes = {}
        self._component_styles = {}
        self._item_backgrounds = []
        self._item_background_keys = set()
        self._scan_page()
        if self.matches:
            self._create_bar(result_title)
            self.go_to(0)

    def _add_text_matches(self, widget, text, kind):
        for start, end in _navigation_search_ranges(text, self.query):
            self.matches.append(
                {
                    "widget": widget,
                    "text": text,
                    "start": start,
                    "end": end,
                    "kind": kind,
                }
            )

    def _scan_item_view(self, view):
        model = view.model()
        if model is None:
            return

        def scan(parent_index):
            for row in range(model.rowCount(parent_index)):
                first_column = model.index(row, 0, parent_index)
                for column in range(model.columnCount(parent_index)):
                    index = model.index(row, column, parent_index)
                    text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
                    for start, end in _navigation_search_ranges(
                        text, self.query
                    ):
                        self.matches.append(
                            {
                                "widget": view,
                                "index": index,
                                "text": text,
                                "start": start,
                                "end": end,
                                "kind": "item",
                            }
                        )
                if model.rowCount(first_column):
                    scan(first_column)

        scan(view.rootIndex())

    def _scan_page(self):
        for widget in self.page.findChildren(QWidget):
            if widget.objectName() == "navigationSearchMatchBar":
                continue
            if isinstance(widget, QLabel):
                text = widget.text()
                if (
                    widget.textFormat() == Qt.TextFormat.PlainText
                    or not Qt.mightBeRichText(text)
                ):
                    ranges = _navigation_search_ranges(text, self.query)
                    if ranges:
                        self._label_text[widget] = (
                            text, widget.textFormat()
                        )
                        self._add_text_matches(widget, text, "label")
            elif isinstance(widget, QLineEdit):
                if widget.echoMode() == QLineEdit.EchoMode.Normal:
                    self._add_text_matches(widget, widget.text(), "line_edit")
                    if any(
                        match["widget"] is widget
                        for match in self.matches
                    ):
                        self._line_edit_palettes[widget] = widget.palette()
            elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
                text = widget.toPlainText()
                self._add_text_matches(widget, text, "text_edit")
                if any(
                    match["widget"] is widget
                    for match in self.matches
                ):
                    self._editor_selections[widget] = (
                        widget.extraSelections()
                    )
            elif isinstance(widget, QHeaderView):
                continue
            elif isinstance(widget, QAbstractItemView):
                self._scan_item_view(widget)
            elif isinstance(widget, (QAbstractButton, QGroupBox)):
                text = _navigation_widget_text(widget)
                self._add_text_matches(widget, text, "component")
                if any(
                    match["widget"] is widget
                    for match in self.matches
                ):
                    self._component_styles[widget] = widget.styleSheet()

        self.matches.sort(key=self._match_sort_key)

    def _match_sort_key(self, match):
        widget = match["widget"]
        point = widget.mapTo(self.page, QPoint(0, 0))
        if match["kind"] == "item":
            point.setY(point.y() + widget.visualRect(match["index"]).top())
        return point.y(), point.x(), match["start"]

    def _create_bar(self, result_title):
        self.bar = QFrame(self.page)
        self.bar.setObjectName("navigationSearchMatchBar")
        self.bar.setFrameShape(QFrame.Shape.StyledPanel)
        self.bar.setStyleSheet(
            "QFrame#navigationSearchMatchBar {"
            "background: #FFF8CC; border: 1px solid #E8C547; "
            "border-radius: 4px; padding: 3px;}"
        )
        layout = QHBoxLayout(self.bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        label_text = f"عبارة البحث: «{self.query}»"
        if result_title:
            label_text += f" | {result_title}"
        self.query_label = QLabel(label_text, self.bar)
        self.query_label.setTextFormat(Qt.TextFormat.PlainText)
        self.query_label.setWordWrap(True)
        if result_title:
            self.query_label.setToolTip(result_title)
        layout.addWidget(self.query_label, 1)
        self.position_label = QLabel(self.bar)
        self.position_label.setObjectName("navigationSearchMatchPosition")
        layout.addWidget(self.position_label)
        self.previous_button = QPushButton("السابق", self.bar)
        self.next_button = QPushButton("التالي", self.bar)
        self.previous_button.setToolTip("الانتقال إلى الموضع السابق")
        self.next_button.setToolTip("الانتقال إلى الموضع التالي")
        self.previous_button.clicked.connect(
            lambda: self.go_to(self.index - 1)
        )
        self.next_button.clicked.connect(
            lambda: self.go_to(self.index + 1)
        )
        layout.addWidget(self.previous_button)
        layout.addWidget(self.next_button)
        self.previous_button.setEnabled(bool(self.matches))
        self.next_button.setEnabled(bool(self.matches))

        page_layout = self.page.layout()
        if page_layout is None:
            page_layout = QVBoxLayout(self.page)
        if isinstance(page_layout, QBoxLayout):
            page_layout.insertWidget(0, self.bar)
        elif isinstance(page_layout, QGridLayout):
            page_layout.addWidget(
                self.bar, 0, 0, 1, max(1, page_layout.columnCount())
            )
        elif isinstance(page_layout, QFormLayout):
            page_layout.insertRow(0, self.bar)
        else:
            page_layout.addWidget(self.bar)

    @staticmethod
    def _qt_position(text, python_position):
        return len(text[:python_position].encode("utf-16-le")) // 2

    def _render_label(self, widget, active_match):
        text, _text_format = self._label_text[widget]
        widget_matches = [
            match for match in self.matches
            if match["widget"] is widget and match["kind"] == "label"
        ]
        html_parts = []
        cursor = 0
        for match in widget_matches:
            html_parts.append(
                html.escape(text[cursor:match["start"]]).replace("\n", "<br>")
            )
            color = (
                self._ACTIVE_BACKGROUND
                if match is active_match
                else self._BACKGROUND
            )
            html_parts.append(
                f'<span style="background-color:{color}; color:#111827;">'
                f'{html.escape(text[match["start"]:match["end"]])}'
                "</span>"
            )
            cursor = match["end"]
        html_parts.append(html.escape(text[cursor:]).replace("\n", "<br>"))
        widget.setTextFormat(Qt.TextFormat.RichText)
        widget.setText("".join(html_parts))

    def _apply_highlights(self, active_match):
        for widget in self._label_text:
            self._render_label(widget, active_match)

        for widget, original_selections in self._editor_selections.items():
            selections = list(original_selections)
            for match in self.matches:
                if (
                    match["widget"] is not widget
                    or match["kind"] != "text_edit"
                ):
                    continue
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(widget.document())
                selection.cursor.setPosition(
                    self._qt_position(match["text"], match["start"])
                )
                selection.cursor.setPosition(
                    self._qt_position(match["text"], match["end"]),
                    QTextCursor.MoveMode.KeepAnchor,
                )
                selection.format.setBackground(
                    QColor(
                        self._ACTIVE_BACKGROUND
                        if match is active_match
                        else self._BACKGROUND
                    )
                )
                selection.format.setForeground(QColor("#111827"))
                selections.append(selection)
            widget.setExtraSelections(selections)

        for widget, original_palette in self._line_edit_palettes.items():
            widget.deselect()
            widget.setPalette(original_palette)
        if active_match is not None and active_match["kind"] == "line_edit":
            widget = active_match["widget"]
            palette = widget.palette()
            palette.setColor(
                QPalette.ColorRole.Highlight,
                QColor(self._ACTIVE_BACKGROUND),
            )
            palette.setColor(
                QPalette.ColorRole.HighlightedText, QColor("#111827")
            )
            widget.setPalette(palette)
            widget.setSelection(
                active_match["start"],
                active_match["end"] - active_match["start"],
            )

        active_item = (
            active_match
            if active_match is not None and active_match["kind"] == "item"
            else None
        )
        item_colors = {}
        for match in self.matches:
            if match["kind"] != "item":
                continue
            view = match["widget"]
            model = view.model()
            index = match["index"]
            key = (id(model), index)
            if key not in self._item_background_keys:
                self._item_background_keys.add(key)
                self._item_backgrounds.append(
                    (model, index, index.data(Qt.ItemDataRole.BackgroundRole))
                )
            item_colors[key] = (
                self._ACTIVE_BACKGROUND
                if active_item is not None
                and active_item["widget"] is view
                and active_item["index"] == index
                else item_colors.get(key, self._BACKGROUND)
            )
        for model, index, _background in self._item_backgrounds:
            key = (id(model), index)
            if key not in item_colors:
                continue
            model.setData(
                index,
                QBrush(QColor(item_colors[key])),
                Qt.ItemDataRole.BackgroundRole,
            )

        active_component = (
            active_match
            if active_match is not None
            and active_match["kind"] == "component"
            else None
        )
        for widget, original_style in self._component_styles.items():
            color = (
                self._ACTIVE_BACKGROUND
                if active_component is not None
                and active_component["widget"] is widget
                else self._BACKGROUND
            )
            if isinstance(widget, QGroupBox):
                rule = f"QGroupBox {{ border: 2px solid {color}; }}"
            else:
                widget_type = (
                    "QToolButton"
                    if isinstance(widget, QToolButton)
                    else "QPushButton"
                )
                rule = (
                    f"{widget_type} {{ background-color: {color}; }}"
                )
            widget.setStyleSheet(f"{original_style}\n{rule}")

    def _reveal(self, match):
        widget = match["widget"]
        for tab_widget in self.page.findChildren(QTabWidget):
            for tab_index in range(tab_widget.count()):
                tab_page = tab_widget.widget(tab_index)
                if tab_page is widget or tab_page.isAncestorOf(widget):
                    tab_widget.setCurrentIndex(tab_index)
                    break
        for stack in self.page.findChildren(QStackedWidget):
            for stack_index in range(stack.count()):
                stack_page = stack.widget(stack_index)
                if stack_page is widget or stack_page.isAncestorOf(widget):
                    stack.setCurrentIndex(stack_index)
                    break

        for scroll_area in self.page.findChildren(QScrollArea):
            content = scroll_area.widget()
            if content is not None and (
                content is widget or content.isAncestorOf(widget)
            ):
                scroll_area.ensureWidgetVisible(widget, 0, 24)

        if match["kind"] == "item":
            view = widget
            index = match["index"]
            parent_index = index.parent()
            while parent_index.isValid() and hasattr(view, "expand"):
                view.expand(parent_index)
                parent_index = parent_index.parent()
            view.setCurrentIndex(index)
            view.scrollTo(
                index, QAbstractItemView.ScrollHint.PositionAtCenter
            )
        elif match["kind"] in ("line_edit", "text_edit"):
            widget.setFocus(Qt.FocusReason.OtherFocusReason)
            if match["kind"] == "text_edit":
                cursor = QTextCursor(widget.document())
                cursor.setPosition(
                    self._qt_position(match["text"], match["start"])
                )
                cursor.setPosition(
                    self._qt_position(match["text"], match["end"]),
                    QTextCursor.MoveMode.KeepAnchor,
                )
                widget.setTextCursor(cursor)
                widget.ensureCursorVisible()
        elif match["kind"] == "component":
            widget.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            for scroll_area in self.page.findChildren(QScrollArea):
                content = scroll_area.widget()
                if content is not None and content.isAncestorOf(widget):
                    scroll_area.ensureWidgetVisible(widget, 0, 24)

    def go_to(self, index):
        if not self.matches:
            return
        self.index = index % len(self.matches)
        match = self.matches[self.index]
        self.position_label.setText(
            f"{self.index + 1} / {len(self.matches)}"
        )
        self._apply_highlights(match)
        self._reveal(match)

    def clear(self):
        for widget, (text, text_format) in self._label_text.items():
            self._restore_widget(
                lambda widget=widget, text=text, text_format=text_format: (
                    widget.setTextFormat(text_format), widget.setText(text)
                )
            )
        for widget, selections in self._editor_selections.items():
            self._restore_widget(
                lambda widget=widget, selections=selections:
                widget.setExtraSelections(selections)
            )
        for widget, palette in self._line_edit_palettes.items():
            self._restore_widget(
                lambda widget=widget, palette=palette: (
                    widget.deselect(), widget.setPalette(palette)
                )
            )
        for widget, style in self._component_styles.items():
            self._restore_widget(
                lambda widget=widget, style=style: widget.setStyleSheet(style)
            )
        for model, index, background in self._item_backgrounds:
            self._restore_widget(
                lambda model=model, index=index, background=background:
                model.setData(index, background, Qt.ItemDataRole.BackgroundRole)
            )
        if self.bar is not None:
            self._restore_widget(self.bar.hide)
            self._restore_widget(lambda: self.bar.setParent(None))
            self._restore_widget(self.bar.deleteLater)

    @staticmethod
    def _restore_widget(restore):
        try:
            restore()
        except RuntimeError:
            pass


def _build_navigation_search_actions(
    page_navigation_actions, page_descriptions, linked_menu_actions
):
    search_actions = {}
    linked_actions = []
    for action, page in page_navigation_actions:
        if action not in linked_menu_actions:
            continue
        linked_actions.append((action, page))
        action_label = action.text().replace("&", "").strip()
        if action_label:
            search_actions.setdefault(action_label, action)

    for page, (page_title, _description) in page_descriptions.items():
        page_action = next(
            (
                action for action, target in linked_actions
                if target is page
            ),
            None,
        )
        if page_action is not None and page_title:
            search_actions.setdefault(page_title, page_action)
    return search_actions


def _build_navigation_toolbar_content(toolbar, left_section, menu_section):
    content = QWidget(toolbar)
    content.setObjectName("navigationToolbarContent")
    content.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    content.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    content.setMinimumHeight(60)
    content.setMinimumWidth(0)

    layout = QGridLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(0)
    layout.setVerticalSpacing(0)
    for column in range(3):
        layout.setColumnStretch(column, 1)

    layout.addWidget(
        left_section, 0, 0,
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    layout.addWidget(
        menu_section, 0, 1, 1, 1,
        Qt.AlignmentFlag.AlignCenter,
    )
    right_section = QWidget(content)
    right_section.setObjectName("navigationRightSection")
    layout.addWidget(right_section, 0, 2)
    return content


def _configure_navigation_menu_layout(layout):
    layout.parentWidget().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    layout.setContentsMargins(8, 0, 8, 0)
    layout.setSpacing(8)
    layout.setDirection(QBoxLayout.Direction.LeftToRight)


class _ClearSearchFocusOnOutsideClick(QObject):
    def __init__(
        self, search, popup=None, on_empty_focus=None, on_focus_out=None
    ):
        super().__init__(search)
        self._search = search
        self._popup = popup
        self._on_empty_focus = on_empty_focus
        self._on_focus_out = on_focus_out

    def eventFilter(self, watched, event):
        if watched is self._search and event.type() == QEvent.Type.FocusIn:
            if self._on_empty_focus is not None:
                QTimer.singleShot(0, self._on_empty_focus)
        if watched is self._search and event.type() == QEvent.Type.FocusOut:
            if self._on_focus_out is not None:
                self._on_focus_out()
        if watched is self._search and event.type() == QEvent.Type.KeyPress:
            if self._popup is not None and self._popup.isVisible():
                if event.key() == Qt.Key.Key_Down:
                    self._popup.select_next()
                    return True
                if event.key() == Qt.Key.Key_Up:
                    self._popup.select_previous()
                    return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._popup.activate_current()
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self._popup.hide()
                    return True
        if event.type() == QEvent.Type.MouseButtonPress:
            target = watched if isinstance(watched, QWidget) else None
            clicked_search = (
                target is not None
                and (
                    target is self._search
                    or self._search.isAncestorOf(target)
                )
            )
            clicked_popup = (
                self._popup is not None
                and target is not None
                and (
                    target is self._popup
                    or self._popup.isAncestorOf(target)
                )
            )
            if (
                clicked_search
                and not self._search.text().strip()
                and self._on_empty_focus is not None
            ):
                QTimer.singleShot(0, self._on_empty_focus)
            if (
                target is not None
                and not clicked_search
                and not clicked_popup
            ):
                if self._popup is not None:
                    self._popup.hide()
                self._search.clearFocus()
        return False


class ActivityCardsWidget(QListWidget):
    actionRequested = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._read_only = False
        self._compact_mode = False
        self.setObjectName("lessonActivityCards")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setGridSize(QSize(162, 140))
        self.setSpacing(6)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setStyleSheet(
            "QListWidget { border: none; background: transparent; }"
            "QListWidget::item { border: 1px solid transparent;"
            "border-radius: 10px; padding: 1px; }"
        )
        self.itemSelectionChanged.connect(self._sync_selected_cards)

    def set_compact_mode(self, compact):
        self._compact_mode = bool(compact)
        if self._compact_mode:
            self.setViewMode(QListView.ListMode)
            self.setWrapping(False)
            self.setGridSize(QSize())
        else:
            self.setViewMode(QListView.IconMode)
            self.setWrapping(True)
            self.setGridSize(QSize(162, 140))
        self._resize_cards_to_viewport()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_cards_to_viewport()

    def _resize_cards_to_viewport(self):
        card_width = (
            max(0, self.viewport().width() - 4)
            if self._compact_mode else 150
        )
        item_width = card_width + (0 if self._compact_mode else 10)
        for row in range(self.count()):
            item = self.item(row)
            card = self.itemWidget(item)
            if card is None:
                continue
            card.setMinimumWidth(0)
            card.setFixedWidth(card_width)
            item.setSizeHint(QSize(item_width, 138))

    def set_activities(self, activities, completion_issues=None, select_id=None):
        self.clear()
        completion_issues = completion_issues or {}
        colors = (
            ("#EFF6FF", "#2563EB", "#BFDBFE"),
            ("#ECFDF5", "#059669", "#A7F3D0"),
            ("#FFFBEB", "#D97706", "#FDE68A"),
            ("#FDF2F8", "#DB2777", "#FBCFE8"),
            ("#ECFEFF", "#0891B2", "#A5F3FC"),
            ("#FFF7ED", "#EA580C", "#FED7AA"),
            ("#F5F3FF", "#7C3AED", "#DDD6FE"),
        )
        selected_item = None
        for index, (activity_id, title, duration) in enumerate(activities):
            background, accent, border = colors[index % len(colors)]
            item = QListWidgetItem()
            item.setData(Qt.UserRole, int(activity_id))
            item.setSizeHint(QSize(160, 138))
            self.addItem(item)

            card = QFrame(self)
            card.setObjectName("lessonActivityCard")
            card.setFixedSize(150, 130)
            card.setProperty("selected", False)
            card.setStyleSheet(
                "QFrame#lessonActivityCard {"
                f"background: {background}; border: 1px solid {border};"
                f"border-right: 5px solid {accent}; border-radius: 9px;"
                "}"
                "QFrame#lessonActivityCard[selected=\"true\"] {"
                f"border: 2px solid {accent}; border-right: 5px solid {accent};"
                "}"
                "QLabel { border: none; background: transparent; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(7, 6, 7, 6)
            card_layout.setSpacing(4)
            heading_layout = QHBoxLayout()
            heading_layout.setSpacing(5)
            status = LessonStatusIndicator(
                completion_issues.get(int(activity_id), []),
                card,
                item_type="النشاط",
            )
            heading_layout.addWidget(status, 0, Qt.AlignTop)
            title_label = QLabel(str(title or "نشاط دون عنوان"), card)
            title_label.setObjectName("lessonActivityTitle")
            title_label.setWordWrap(True)
            title_label.setStyleSheet(
                f"color: {accent}; font-weight: 700; font-size: 10pt;"
            )
            heading_layout.addWidget(title_label, 1)
            card_layout.addLayout(heading_layout, 1)
            duration_label = QLabel(f"المدة: {duration or '—'}", card)
            duration_label.setObjectName("lessonActivityDuration")
            duration_label.setStyleSheet("color: #475569; font-size: 9pt;")
            duration_label.setWordWrap(True)
            duration_label.setAlignment(Qt.AlignCenter)
            duration_label.setMinimumWidth(0)
            card_layout.addWidget(duration_label)
            actions_layout = QHBoxLayout()
            actions_layout.setSpacing(4)
            actions_layout.addStretch(1)
            for tooltip, action, action_type in (
                ("تعديل النشاط", "edit", "edit"),
                ("حذف النشاط", "delete", "delete"),
            ):
                button = _create_card_action_button(
                    card,
                    tooltip,
                    action,
                    action_type,
                    self.actionRequested.emit,
                    int(activity_id),
                    enabled=not self._read_only,
                )
                actions_layout.addWidget(button)
            actions_layout.addStretch(1)
            card_layout.addLayout(actions_layout)
            self.setItemWidget(item, card)
            if select_id is not None and int(activity_id) == int(select_id):
                selected_item = item

        self._resize_cards_to_viewport()
        if (
            selected_item is None
            and select_id is not False
            and self.count()
        ):
            selected_item = self.item(0)
        if selected_item is not None:
            self.setCurrentItem(selected_item)
        self._sync_selected_cards()

    def set_read_only(self, read_only):
        self._read_only = bool(read_only)
        for row in range(self.count()):
            card = self.itemWidget(self.item(row))
            if card is None:
                continue
            for button in card.findChildren(QPushButton):
                button.setEnabled(not self._read_only)

    def _sync_selected_cards(self):
        for row in range(self.count()):
            item = self.item(row)
            card = self.itemWidget(item)
            if card is None:
                continue
            card.setProperty("selected", item.isSelected())
            card.style().unpolish(card)
            card.style().polish(card)


class DetailCardsWidget(QListWidget):
    actionRequested = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._read_only = False
        self.setObjectName("lessonDetailCards")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSpacing(6)
        self.setStyleSheet(
            "QListWidget { border: none; background: transparent; }"
            "QListWidget::item { border: 1px solid transparent;"
            "border-radius: 9px; padding: 1px; }"
        )
        self.itemSelectionChanged.connect(self._sync_selected_cards)

    def set_details(self, details, select_id=None):
        self.clear()
        colors = (
            ("#EFF6FF", "#2563EB", "#BFDBFE"),
            ("#ECFDF5", "#059669", "#A7F3D0"),
            ("#FFFBEB", "#D97706", "#FDE68A"),
            ("#FDF2F8", "#DB2777", "#FBCFE8"),
            ("#ECFEFF", "#0891B2", "#A5F3FC"),
            ("#FFF7ED", "#EA580C", "#FED7AA"),
        )
        selected_item = None
        for index, (detail_id, key_name, value_text) in enumerate(details):
            background, accent, border = colors[index % len(colors)]
            item = QListWidgetItem()
            item.setData(Qt.UserRole, int(detail_id))
            item.setSizeHint(QSize(340, 88))
            self.addItem(item)

            card = QFrame(self)
            card.setObjectName("lessonDetailCard")
            card.setProperty("selected", False)
            card.setStyleSheet(
                "QFrame#lessonDetailCard {"
                f"background: {background}; border: 1px solid {border};"
                f"border-right: 5px solid {accent}; border-radius: 9px;"
                "}"
                "QFrame#lessonDetailCard[selected=\"true\"] {"
                f"border: 2px solid {accent}; border-right: 5px solid {accent};"
                "}"
                "QLabel { border: none; background: transparent; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 7, 10, 7)
            card_layout.setSpacing(3)
            heading_layout = QHBoxLayout()
            heading_layout.setSpacing(4)
            key_label = QLabel(str(key_name or "خاصية دون اسم"), card)
            key_label.setObjectName("lessonDetailKey")
            key_label.setWordWrap(True)
            key_label.setStyleSheet(
                f"color: {accent}; font-weight: 700; font-size: 10pt;"
            )
            heading_layout.addWidget(key_label, 1)
            for tooltip, action, action_type in (
                ("تعديل الخاصية", "edit", "edit"),
                ("حذف الخاصية", "delete", "delete"),
            ):
                button = _create_card_action_button(
                    card,
                    tooltip,
                    action,
                    action_type,
                    self.actionRequested.emit,
                    int(detail_id),
                    enabled=not self._read_only,
                )
                heading_layout.addWidget(button)
            card_layout.addLayout(heading_layout)
            value_label = QLabel(str(value_text or "—"), card)
            value_label.setObjectName("lessonDetailValue")
            value_label.setWordWrap(True)
            value_label.setStyleSheet("color: #334155; font-size: 9pt;")
            card_layout.addWidget(value_label)
            self.setItemWidget(item, card)
            if select_id is not None and int(detail_id) == int(select_id):
                selected_item = item

        if selected_item is None and self.count():
            selected_item = self.item(0)
        if selected_item is not None:
            self.setCurrentItem(selected_item)
        self._sync_selected_cards()

    def set_read_only(self, read_only):
        self._read_only = bool(read_only)
        for row in range(self.count()):
            card = self.itemWidget(self.item(row))
            if card is None:
                continue
            for button in card.findChildren(QPushButton):
                button.setEnabled(not self._read_only)

    def _sync_selected_cards(self):
        for row in range(self.count()):
            item = self.item(row)
            card = self.itemWidget(item)
            if card is None:
                continue
            card.setProperty("selected", item.isSelected())
            card.style().unpolish(card)
            card.style().polish(card)


class _NavigationMenuItemButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._menu_icon_label = QLabel(self)
        self._menu_icon_label.setObjectName("navigationMenuItemIcon")
        self._menu_icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self._menu_icon_label.setFixedSize(16, 16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._menu_icon_label.move(
            self.width() - 14 - self._menu_icon_label.width(),
            (self.height() - self._menu_icon_label.height()) // 2,
        )


def _insert_menu_action_button(menu, original_action):
    item_button = _NavigationMenuItemButton(menu)
    item_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    item_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    item_button.setIconSize(QSize(16, 16))
    item_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    item_button.setMinimumHeight(42)
    item_button.setMinimumWidth(180)
    item_button.setCursor(Qt.PointingHandCursor)
    item_button.setObjectName("centeredNavigationMenuItem")
    item_button.setProperty("responsiveTextRequired", True)
    widget_action = QWidgetAction(menu)

    def sync_action():
        text = original_action.text().replace("&&", "\0")
        item_button.setText(text.replace("&", "").replace("\0", "&"))
        action_icon = (
            original_action.icon()
            if not original_action.icon().isNull()
            else qta.icon(
                _navigation_menu_icon_name(text),
                color="#475569",
            )
        )
        item_button.setIcon(action_icon)
        item_button._menu_icon_label.setPixmap(
            action_icon.pixmap(item_button.iconSize())
        )
        item_button.setEnabled(original_action.isEnabled())
        item_button.setVisible(original_action.isVisible())
        item_button.setCheckable(original_action.isCheckable())
        item_button.setChecked(original_action.isChecked())
        widget_action.setEnabled(original_action.isEnabled())
        widget_action.setVisible(original_action.isVisible())

        required_width = (
            item_button.fontMetrics().horizontalAdvance(item_button.text())
            + item_button.iconSize().width()
            + 40
        )
        menu_width = max(
            menu.minimumWidth(),
            item_button.sizeHint().width() + 12,
            required_width + 12,
        )
        item_button.setFixedWidth(menu_width - 12)
        menu.setMinimumWidth(menu_width)

    widget_action.setDefaultWidget(item_button)
    item_button.clicked.connect(original_action.trigger)
    item_button.clicked.connect(menu.close)
    original_action.changed.connect(sync_action)
    sync_action()
    menu.insertAction(original_action, widget_action)
    menu.removeAction(original_action)


def _navigation_menu_icon_name(text):
    normalized_text = str(text or "").strip().casefold()
    icon_keywords = (
        (("تصدير", "pdf"), "fa5s.file-pdf"),
        ("استيراد", "fa5s.file-import"),
        ("تصدير", "fa5s.file-export"),
        ("حذف", "fa5s.trash"),
        ("مسح", "fa5s.eraser"),
        ("إضافة", "fa5s.plus"),
        ("اضافة", "fa5s.plus"),
        ("جديدة", "fa5s.plus"),
        ("إدارة", "fa5s.cogs"),
        ("مفهوم", "fa5s.lightbulb"),
        ("كفاية", "fa5s.lightbulb"),
        ("إحصائ", "fa5s.chart-bar"),
        ("احصائ", "fa5s.chart-bar"),
        ("معلم", "fa5s.user"),
        ("معلمة", "fa5s.user"),
        ("قسم", "fa5s.users"),
        ("أقسام", "fa5s.users"),
        ("تعيين", "fa5s.users"),
        ("جدول", "fa5s.calendar-alt"),
        ("أوقات", "fa5s.calendar-alt"),
        ("عطلة", "fa5s.umbrella-beach"),
        ("العطل", "fa5s.umbrella-beach"),
        ("سنة دراسية", "fa5s.calendar"),
        ("السنوات الدراسية", "fa5s.calendar"),
        ("مخطط", "fa5s.book-open"),
        ("مخططات", "fa5s.book-open"),
        ("دفتر", "fa5s.book"),
        ("الدفتر", "fa5s.book"),
        ("طباعة", "fa5s.print"),
        ("معاينة", "fa5s.eye"),
        ("تصفح", "fa5s.eye"),
        ("عرض", "fa5s.eye"),
        ("إعداد", "fa5s.cogs"),
        ("ضبط", "fa5s.cogs"),
        ("json", "fa5s.file-code"),
    )
    for keyword, icon_name in icon_keywords:
        if (
            all(part in normalized_text for part in keyword)
            if isinstance(keyword, tuple)
            else keyword in normalized_text
        ):
            return icon_name
    return "fa5s.info-circle"


def center_menu_items(menu):
    menu.setLayoutDirection(Qt.RightToLeft)
    menu.setMinimumWidth(230)
    for action in tuple(menu.actions()):
        if not action.isSeparator() and action.menu() is None:
            _insert_menu_action_button(menu, action)


class TeacherInfoCard(QFrame):
    editToggled = Signal(bool)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._editing = False
        self.setObjectName("teacherInfoCard")
        self.setStyleSheet(
            "QFrame#teacherInfoCard { background:#FFFFFF; "
            "border:1px solid #CBD5E1; border-radius:8px; }"
        )
        self.edit_button = QToolButton(self)
        self.edit_button.setObjectName("teacherInfoCardEditButton")
        self.edit_button.setText("")
        set_card_action_type(self.edit_button, "edit")
        self.edit_button.setToolTip("تعديل بيانات البطاقة")
        self.edit_button.setAccessibleName("تعديل بيانات البطاقة")
        self.edit_button.setFixedSize(30, 30)
        self.edit_button.clicked.connect(self.toggle_editing)

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(16, 14, 16, 16)
        self.content_layout.setSpacing(12)
        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet(
            "font-size:13px; font-weight:700; color:#1E3A8A;"
        )
        self.content_layout.addWidget(self.title_label)

    def toggle_editing(self):
        self._editing = not self._editing
        self.edit_button.setProperty(
            "actionType", "save" if self._editing else "edit"
        )
        self.edit_button.setToolTip(
            "إنهاء التعديل" if self._editing else "تعديل بيانات البطاقة"
        )
        self.edit_button.setAccessibleName(self.edit_button.toolTip())
        self.editToggled.emit(self._editing)

    def set_editing_allowed(self, allowed):
        self.edit_button.setEnabled(bool(allowed))
        if not allowed and self._editing:
            self._editing = False
            set_card_action_type(self.edit_button, "edit")
            self.edit_button.setToolTip("تعديل بيانات البطاقة")
            self.edit_button.setAccessibleName("تعديل بيانات البطاقة")
            self.editToggled.emit(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.edit_button.move(10, 8)
        self.edit_button.raise_()


class TeacherInfoPage(QWidget):
    saveRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("teacherInfoPage")
        self.setLayoutDirection(Qt.RightToLeft)
        self.inputs = [None] * len(SCHOOL_INFO_DIALOG_FIELDS)
        self._loading_values = False
        self._read_only = False
        self._cards = []
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(700)
        self._autosave_timer.timeout.connect(self.saveRequested)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("teacherInfoScrollArea")
        self.scroll_area.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 18)
        content_layout.setSpacing(14)

        self.tabs = QTabWidget(content)
        self.tabs.setObjectName("teacherInfoTabs")
        self._add_tab(
            "بيانات المدرسة",
            [("بيانات المؤسسة", (17, 18, 19, 20, 1, 28, 0))],
        )
        self._add_tab(
            "بيانات الإطار الإداري والبيداغوجي",
            [("الإطار الإداري والبيداغوجي", (3, 21, 4, 25, 26, 27))],
        )
        self._add_tab(
            "بيانات المعلم الشخصية",
            [("البيانات الشخصية", (2, 24, 6, 29, 13, 14, 15, 16, 30))],
        )
        self._add_tab(
            "بيانات المسار المهني للمعلم",
            [
                ("المسار الوظيفي", (5, 22, 7, 8)),
                ("التقييم والمتابعة", (9, 10, 23, 12, 11)),
            ],
        )
        content_layout.addWidget(self.tabs, 1)
        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area)

    def _add_tab(self, title, cards):
        tab = QWidget(self.tabs)
        tab.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 12, 0, 0)
        tab_layout.setSpacing(12)
        for card_title, field_indices in cards:
            self._add_field_card(tab_layout, card_title, field_indices)
        tab_layout.addStretch(1)
        self.tabs.addTab(tab, title)

    def _add_field_card(self, parent_layout, title, field_indices):
        card = TeacherInfoCard(title, self.tabs)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        editors = []
        field_widgets = []
        for field_index in field_indices:
            label_text, kind, default = SCHOOL_INFO_DIALOG_FIELDS[field_index]
            if kind == "nonnegative_int":
                editor = QSpinBox(card)
                editor.setRange(0, 999)
                editor.setValue(int(default or 0))
                editor.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
                editor.setEnabled(False)
                editor.valueChanged.connect(self._schedule_autosave)
            elif kind == "gender":
                editor = QComboBox(card)
                editor.addItems(TEACHER_GENDER_OPTIONS)
                editor.setEnabled(False)
                editor.currentTextChanged.connect(self._schedule_autosave)
            elif kind == "plaintext":
                editor = QTextEdit(card)
                editor.setAcceptRichText(False)
                editor.setMinimumHeight(110)
                editor.setReadOnly(True)
                editor.textChanged.connect(self._schedule_autosave)
            else:
                editor = QLineEdit(str(default or ""), card)
                editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
                editor.setReadOnly(True)
                if kind == "date":
                    editor.setPlaceholderText("YYYY-MM-DD")
                editor.textChanged.connect(self._schedule_autosave)

            label = QLabel(label_text, card)
            label.setObjectName("teacherInfoFieldLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            field_widgets.append((label, editor, kind))
            self.inputs[field_index] = editor
            editors.append(editor)

        regular_fields = [
            field for field in field_widgets if field[2] != "plaintext"
        ]
        text_fields = [
            field for field in field_widgets if field[2] == "plaintext"
        ]
        for local_index, (label, editor, _kind) in enumerate(regular_fields):
            column = local_index % 3
            row = (local_index // 3) * 2
            grid.addWidget(label, row, column)
            grid.addWidget(editor, row + 1, column)
        text_row = ((len(regular_fields) + 2) // 3) * 2
        for text_index, (label, editor, _kind) in enumerate(text_fields):
            row = text_row + text_index * 2
            grid.addWidget(label, row, 0, 1, 3)
            grid.addWidget(editor, row + 1, 0, 1, 3)

        card.content_layout.addLayout(grid)
        card.editToggled.connect(
            lambda editing, widgets=tuple(editors):
            self._set_card_editable(widgets, editing)
        )
        self._cards.append(card)
        parent_layout.addWidget(card)

    @staticmethod
    def _set_card_editable(editors, editable):
        for editor in editors:
            if isinstance(editor, (QLineEdit, QTextEdit)):
                editor.setReadOnly(not editable)
            else:
                editor.setEnabled(editable)

    def set_values(self, values):
        self._loading_values = True
        self._autosave_timer.stop()
        try:
            for editor, value in zip(self.inputs, values):
                if isinstance(editor, QSpinBox):
                    editor.setValue(int(value or 0))
                elif isinstance(editor, QTextEdit):
                    editor.setPlainText(str(value or ""))
                elif isinstance(editor, QComboBox):
                    editor.setCurrentIndex(
                        max(editor.findText(str(value or "")), 0)
                    )
                else:
                    editor.setText(str(value or ""))
        finally:
            self._loading_values = False

    def _schedule_autosave(self, *_):
        if not self._loading_values and not self._read_only:
            self._autosave_timer.start()

    def values(self):
        result = []
        for editor in self.inputs:
            if isinstance(editor, QSpinBox):
                result.append(editor.value())
            elif isinstance(editor, QTextEdit):
                result.append(editor.toPlainText().strip())
            elif isinstance(editor, QComboBox):
                result.append(editor.currentText().strip())
            else:
                result.append(editor.text().strip())
        return result

    def set_read_only(self, read_only):
        self._read_only = bool(read_only)
        if self._read_only:
            self._autosave_timer.stop()
        for card in self._cards:
            card.set_editing_allowed(not self._read_only)


class StatisticsLoadWorker(QObject):
    result_ready = Signal(object, int, bool)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, database_path, force_refresh=False):
        super().__init__()
        self.database_path = database_path
        self.cache_path = f"{database_path}.analytics.sqlite3"
        self.force_refresh = force_refresh

    @Slot()
    def run(self):
        import pandas as pd

        try:
            with connect_database(self.database_path, timeout=10) as con:
                con.execute("BEGIN")
                revision_row = con.execute(
                    "SELECT revision FROM app_data_revision WHERE id=1"
                ).fetchone()
                revision = int(revision_row[0]) if revision_row else 0

                with connect_database(self.cache_path, timeout=10) as cache:
                    cache.execute("""
                        CREATE TABLE IF NOT EXISTS analytics_cache (
                            source_path TEXT PRIMARY KEY,
                            source_revision INTEGER NOT NULL,
                            payload TEXT NOT NULL,
                            refreshed_at TEXT NOT NULL
                        )
                    """)
                    cached = cache.execute(
                        """SELECT source_revision, payload
                           FROM analytics_cache WHERE source_path=?""",
                        (str(Path(self.database_path).resolve()),),
                    ).fetchone()
                if (
                    not self.force_refresh and cached
                    and int(cached[0]) == revision
                ):
                    cached_payload = json.loads(cached[1])
                    if cached_payload.get("schema_version") == 2:
                        con.rollback()
                        self.result_ready.emit(
                            cached_payload, revision, True
                        )
                        return

                source = pd.read_sql_query("""
                    SELECT h.id AS lesson_id, d.date,
                        COALESCE(g.group_key, c.name) AS class_name,
                        m.name AS subject, lm.name AS learning_mode,
                        h.time AS lesson_time,
                        n.id AS activity_id, n.title AS activity_title,
                        n.time AS activity_time,
                        nd.id AS detail_id, nd.key_name,
                        nd.value_text
                    FROM hessa h
                    JOIN day_data d ON d.id = h.day_data_id
                    JOIN classe c ON c.id = h.classe_id
                    LEFT JOIN class_group g ON g.id=h.class_group_id
                    LEFT JOIN majal m ON m.id = h.majal_id
                    LEFT JOIN learning_mode lm ON lm.id=h.learning_mode_id
                    LEFT JOIN nachat n ON n.hessa_id = h.id
                    LEFT JOIN nachat_detail nd ON nd.nachat_id = n.id
                    ORDER BY d.date, h.id, n.id, nd.id
                """, con)
                plans = pd.read_sql_query("""
                    SELECT p.id, p.title, c.name AS class_name,
                        p.start_date, p.created_at, p.lesson_count,
                        p.methodical_lesson_count,
                        p.integration_lesson_count,
                        p.evaluation_lesson_count,
                        p.support_lesson_count,
                        COUNT(DISTINCT CASE
                            WHEN a.learning_mode='منهجي'
                                AND a.lesson_number BETWEEN 1
                                    AND p.methodical_lesson_count
                            THEN a.lesson_number END)
                        + COUNT(DISTINCT CASE
                            WHEN a.learning_mode='إدماج'
                                AND a.lesson_number BETWEEN 1
                                    AND p.integration_lesson_count
                            THEN a.lesson_number END)
                        + COUNT(DISTINCT CASE
                            WHEN a.learning_mode='تقييم'
                                AND a.lesson_number BETWEEN 1
                                    AND p.evaluation_lesson_count
                            THEN a.lesson_number END)
                        + COUNT(DISTINCT CASE
                            WHEN a.learning_mode='دعم وعلاج'
                                AND a.lesson_number BETWEEN 1
                                    AND p.support_lesson_count
                            THEN a.lesson_number END)
                            AS distributed_slots,
                        COUNT(DISTINCT CASE
                            WHEN a.learning_mode='منهجي'
                                AND a.lesson_number BETWEEN 1
                                    AND p.methodical_lesson_count
                            THEN a.lesson_number END)
                            AS distributed_methodical,
                        COUNT(DISTINCT CASE
                            WHEN a.learning_mode='إدماج'
                                AND a.lesson_number BETWEEN 1
                                    AND p.integration_lesson_count
                            THEN a.lesson_number END)
                            AS distributed_integration,
                        COUNT(DISTINCT CASE
                            WHEN a.learning_mode='تقييم'
                                AND a.lesson_number BETWEEN 1
                                    AND p.evaluation_lesson_count
                            THEN a.lesson_number END)
                            AS distributed_evaluation,
                        COUNT(DISTINCT CASE
                            WHEN a.learning_mode='دعم وعلاج'
                                AND a.lesson_number BETWEEN 1
                                    AND p.support_lesson_count
                            THEN a.lesson_number END)
                            AS distributed_support
                    FROM teaching_plan p
                    JOIN classe c ON c.id=p.classe_id
                    LEFT JOIN teaching_plan_activity a ON a.plan_id=p.id
                    GROUP BY p.id
                    ORDER BY p.start_date, p.id
                """, con)
                con.commit()

            group_labels = {
                group_key: level_firak_label(group_key)
                for group_key in LEVEL_FIRAKS
            }
            source["class_name"] = source["class_name"].map(
                lambda name: (
                    f"{name} — {group_labels[name]}"
                    if name in group_labels else name
                )
            )
            payload = self._build_analytics(source, plans)
            with connect_database(self.cache_path, timeout=10) as cache:
                cache.execute("""
                    INSERT INTO analytics_cache(
                        source_path, source_revision, payload, refreshed_at
                    ) VALUES(?, ?, ?, datetime('now', 'localtime'))
                    ON CONFLICT(source_path) DO UPDATE SET
                        source_revision=excluded.source_revision,
                        payload=excluded.payload,
                        refreshed_at=excluded.refreshed_at
                """, (
                    str(Path(self.database_path).resolve()), revision,
                    json.dumps(payload, ensure_ascii=False),
                ))
            self.result_ready.emit(payload, revision, False)
        except (sqlite3.Error, pd.errors.DatabaseError, ValueError, TypeError) as exc:
            self.failed.emit(f"تعذر تحميل الإحصائيات من قاعدة البيانات: {exc}")
        finally:
            self.finished.emit()

    @staticmethod
    def _build_analytics(source, plans):
        import numpy as np
        import pandas as pd

        mode_properties = {
            "منهجي": ("المحتوى", "هدف الحصة"),
            "إدماج": ("الكفايات المستهدفة",),
            "تقييم": ("الأداء المنتظر",),
            "دعم وعلاج": ("المعايير المستهدفة",),
        }
        if source.empty:
            lessons = pd.DataFrame(columns=[
                "lesson_id", "date", "class_name", "subject",
                "learning_mode", "lesson_time",
            ])
            activities = pd.DataFrame(columns=[
                "activity_id", "lesson_id", "activity_title",
                "activity_time", "learning_mode",
            ])
            details = pd.DataFrame(columns=[
                "detail_id", "activity_id", "activity_title",
                "key_name", "value_text", "learning_mode",
            ])
        else:
            lessons = source.drop_duplicates("lesson_id")[
                ["lesson_id", "date", "class_name", "subject",
                 "learning_mode", "lesson_time"]
            ].copy()
            activities = source.dropna(subset=["activity_id"]).drop_duplicates(
                "activity_id"
            )[
                ["activity_id", "lesson_id", "activity_title",
                 "activity_time", "learning_mode"]
            ].copy()
            details = source.dropna(subset=["detail_id"])[
                ["detail_id", "activity_id", "activity_title", "key_name",
                 "value_text", "learning_mode"]
            ].copy()

        lesson_count = int(len(lessons))
        activity_count = int(len(activities))
        detail_count = int(len(details))
        classes_count = int(lessons["class_name"].nunique())
        dates = pd.to_datetime(lessons["date"], errors="coerce")
        recorded_days = int(dates.nunique())

        activity_counts = (
            activities.groupby("lesson_id").size()
            if not activities.empty else pd.Series(dtype="int64")
        )
        metrics = {
            "lessons": lesson_count,
            "days": recorded_days,
            "classes": classes_count,
            "activities": activity_count,
            "properties": detail_count,
            "average_activities": round(
                activity_count / lesson_count, 1
            ) if lesson_count else 0,
            "average_properties": round(
                detail_count / activity_count, 1
            ) if activity_count else 0,
        }

        lesson_minutes = pd.to_numeric(
            lessons["lesson_time"].astype(str).str.extract(r"(\d+)")[0],
            errors="coerce",
        )
        lesson_minutes.index = lessons["lesson_id"]
        if not activities.empty:
            activities["duration_minutes"] = pd.to_numeric(
                activities["activity_time"].astype(str).str.extract(
                    r"(\d+)"
                )[0],
                errors="coerce",
            )
            activity_minutes = activities.groupby("lesson_id")[
                "duration_minutes"
            ].sum(min_count=1)
            has_valid_activity_times = activities.groupby(
                "lesson_id"
            )["duration_minutes"].count()
            actual_activity_count = activities.groupby("lesson_id").size()
        else:
            activity_minutes = pd.Series(dtype="float64")
            has_valid_activity_times = pd.Series(dtype="int64")
            actual_activity_count = pd.Series(dtype="int64")

        filled_keys = {}
        if not details.empty:
            valid_details = details[
                details["value_text"].fillna("").astype(str).str.strip() != ""
            ]
            filled_keys = (
                valid_details.groupby("activity_id")["key_name"]
                .agg(lambda values: set(str(value).strip() for value in values))
                .to_dict()
            )
        activity_complete = {}
        for activity in activities.itertuples(index=False):
            required = mode_properties.get(
                str(activity.learning_mode or "").strip(), ()
            )
            present = filled_keys.get(activity.activity_id, set())
            activity_complete[activity.activity_id] = all(
                key in present for key in required
            )
        complete_activity_counts = (
            activities.assign(
                is_complete=activities["activity_id"].map(activity_complete)
            ).groupby("lesson_id")["is_complete"].all()
            if not activities.empty else pd.Series(dtype=bool)
        )
        has_activities = activity_counts.reindex(
            lessons["lesson_id"], fill_value=0
        ) > 0
        minutes_match = (
            activity_minutes.reindex(lessons["lesson_id"]).to_numpy()
            == lesson_minutes.reindex(lessons["lesson_id"]).to_numpy()
        )
        valid_times = (
            has_valid_activity_times.reindex(
                lessons["lesson_id"], fill_value=0
            ).to_numpy()
            == actual_activity_count.reindex(
                lessons["lesson_id"], fill_value=0
            ).to_numpy()
        )
        all_activities_complete = complete_activity_counts.reindex(
            lessons["lesson_id"], fill_value=False
        ).to_numpy()
        complete_lessons = int(
            (has_activities.to_numpy() & minutes_match & valid_times
             & all_activities_complete).sum()
        )
        metrics["complete_lessons"] = complete_lessons
        metrics["incomplete_lessons"] = lesson_count - complete_lessons
        metrics["completion_rate"] = round(
            complete_lessons / lesson_count * 100, 1
        ) if lesson_count else 0

        subject_counts = (
            lessons.assign(subject=lessons["subject"].fillna("غير محدد"))
            .groupby("subject").size().sort_values(ascending=False)
        )
        mode_counts = (
            lessons.assign(
                learning_mode=lessons["learning_mode"].fillna("غير محدد")
            ).groupby("learning_mode").size().sort_values(ascending=False)
        )
        activity_title_counts = (
            activities.assign(
                activity_title=activities["activity_title"].fillna("غير محدد")
            ).groupby("activity_title").size().sort_values(ascending=False)
        )
        if details.empty:
            property_usage = []
        else:
            used_details = details[
                details["value_text"].fillna("").astype(str).str.strip() != ""
            ].copy()
            used_details["activity_title"] = (
                used_details["activity_title"].fillna("غير محدد")
            )
            used_details["key_name"] = used_details["key_name"].fillna(
                "غير محدد"
            )
            grouped = used_details.groupby(
                ["activity_title", "key_name"]
            ).agg(
                uses=("detail_id", "count"),
                activities=("activity_id", "nunique"),
            ).sort_values(
                ["uses", "activities"], ascending=False
            )
            property_usage = [
                {
                    "activity": str(activity),
                    "property": str(key),
                    "uses": int(row["uses"]),
                    "activities": int(row["activities"]),
                }
                for (activity, key), row in grouped.iterrows()
            ]

        weekly = []
        forecast = []
        journal_forecast_status = "لا توجد بيانات زمنية صالحة."
        valid_dates = dates.dropna()
        if not valid_dates.empty:
            lesson_dates = lessons.loc[valid_dates.index, ["lesson_id"]].copy()
            lesson_dates["week"] = valid_dates.dt.to_period("W")
            weekly_series = lesson_dates.groupby("week")["lesson_id"].nunique()
            journal_forecast = StatisticsLoadWorker._forecast_weekly_series(
                weekly_series, "lessons"
            )
            weekly = journal_forecast["weekly"]
            forecast = journal_forecast["forecast"]
            journal_forecast_status = journal_forecast["message"]

        plan_mode_definitions = (
            ("منهجي", "methodical_lesson_count", "distributed_methodical"),
            ("إدماج", "integration_lesson_count", "distributed_integration"),
            ("تقييم", "evaluation_lesson_count", "distributed_evaluation"),
            ("دعم وعلاج", "support_lesson_count", "distributed_support"),
        )
        if plans.empty:
            plan_items = []
            plan_metrics = {
                "plans": 0,
                "planned_slots": 0,
                "distributed_slots": 0,
                "pending_slots": 0,
                "progress_rate": 0,
                "complete_plans": 0,
                "average_progress": 0,
                "mode_progress": [
                    {
                        "name": name,
                        "planned": 0,
                        "distributed": 0,
                        "pending": 0,
                        "progress_rate": 0,
                    }
                    for name, _expected_column, _distributed_column
                    in plan_mode_definitions
                ],
            }
            plan_weekly_series = pd.Series(dtype="int64")
        else:
            plans = plans.copy()
            plans["lesson_count"] = pd.to_numeric(
                plans["lesson_count"], errors="coerce"
            ).fillna(0).astype(int)
            plans["distributed_slots"] = pd.to_numeric(
                plans["distributed_slots"], errors="coerce"
            ).fillna(0).astype(int)
            for _name, expected_column, distributed_column in (
                plan_mode_definitions
            ):
                plans[expected_column] = pd.to_numeric(
                    plans[expected_column], errors="coerce"
                ).fillna(0).astype(int)
                plans[distributed_column] = pd.to_numeric(
                    plans[distributed_column], errors="coerce"
                ).fillna(0).astype(int)
            plans["pending_slots"] = (
                plans["lesson_count"] - plans["distributed_slots"]
            ).clip(lower=0)
            plans["progress_rate"] = np.where(
                plans["lesson_count"] > 0,
                plans["distributed_slots"] / plans["lesson_count"] * 100,
                0,
            )
            plan_items = [
                {
                    "title": str(row["title"] or "دون عنوان"),
                    "class_name": str(row["class_name"] or "غير محدد"),
                    "start_date": str(row["start_date"] or ""),
                    "lesson_count": int(row["lesson_count"]),
                    "distributed_slots": int(row["distributed_slots"]),
                    "pending_slots": int(row["pending_slots"]),
                    "progress_rate": round(
                        float(row["progress_rate"]), 1
                    ),
                    "mode_progress": [
                        {
                            "name": mode_name,
                            "planned": int(row[expected_column]),
                            "distributed": int(row[distributed_column]),
                            "pending": max(
                                0,
                                int(row[expected_column])
                                - int(row[distributed_column]),
                            ),
                        }
                        for mode_name, expected_column, distributed_column
                        in plan_mode_definitions
                    ],
                }
                for _, row in plans.iterrows()
            ]
            planned_slots = int(plans["lesson_count"].sum())
            distributed_slots = int(plans["distributed_slots"].sum())
            mode_progress = []
            for name, expected_column, distributed_column in (
                plan_mode_definitions
            ):
                mode_planned = int(plans[expected_column].sum())
                mode_distributed = int(plans[distributed_column].sum())
                mode_progress.append({
                    "name": name,
                    "planned": mode_planned,
                    "distributed": mode_distributed,
                    "pending": max(
                        0, mode_planned - mode_distributed
                    ),
                    "progress_rate": round(
                        mode_distributed / mode_planned * 100, 1
                    ) if mode_planned else 0,
                })
            plan_metrics = {
                "plans": int(len(plans)),
                "planned_slots": planned_slots,
                "distributed_slots": distributed_slots,
                "pending_slots": max(
                    0, planned_slots - distributed_slots
                ),
                "progress_rate": round(
                    distributed_slots / planned_slots * 100, 1
                ) if planned_slots else 0,
                "complete_plans": int(
                    (plans["pending_slots"] == 0).sum()
                ),
                "average_progress": round(
                    float(plans["progress_rate"].mean()), 1
                ),
                "mode_progress": mode_progress,
            }
            created_dates = pd.to_datetime(
                plans["created_at"], errors="coerce"
            ).dropna()
            plan_weekly_series = (
                created_dates.dt.to_period("W").value_counts().sort_index()
                if not created_dates.empty
                else pd.Series(dtype="int64")
            )

        plan_forecast_result = StatisticsLoadWorker._forecast_weekly_series(
            plan_weekly_series, "plans"
        )
        return {
            "schema_version": 2,
            "metrics": metrics,
            "subjects": [
                {"name": str(name), "count": int(count)}
                for name, count in subject_counts.items()
            ],
            "learning_modes": [
                {"name": str(name), "count": int(count)}
                for name, count in mode_counts.items()
            ],
            "activities": [
                {"name": str(name), "count": int(count)}
                for name, count in activity_title_counts.items()
            ],
            "property_usage": property_usage,
            "weekly": weekly,
            "forecast": forecast,
            "forecast_status": journal_forecast_status,
            "plans": {
                "metrics": plan_metrics,
                "items": plan_items,
                "weekly": plan_forecast_result["weekly"],
                "forecast": plan_forecast_result["forecast"],
                "forecast_status": plan_forecast_result["message"],
            },
        }

    @staticmethod
    def _forecast_weekly_series(series, value_key):
        import numpy as np
        import pandas as pd
        from sklearn.linear_model import LinearRegression

        if series.empty:
            return {
                "weekly": [],
                "forecast": [],
                "message": "لا تتوفر بيانات زمنية كافية لبناء توقع.",
            }

        periods = pd.period_range(
            start=series.index.min(), end=series.index.max(), freq="W"
        )
        values = pd.to_numeric(
            series.reindex(periods, fill_value=0), errors="coerce"
        ).fillna(0).to_numpy(dtype=float)
        weekly = [
            {"week": str(period), value_key: int(value)}
            for period, value in zip(periods[-12:], values[-12:])
        ]
        if len(periods) < 4:
            return {
                "weekly": weekly,
                "forecast": [],
                "message": (
                    "لا يتوفر سجل لأربعة أسابيع على الأقل؛ "
                    "لذلك لم يُعرض توقع قد يكون مضللاً."
                ),
            }

        model = LinearRegression()
        positions = np.arange(len(values), dtype=float).reshape(-1, 1)
        model.fit(positions, values)
        future_positions = np.arange(
            len(values), len(values) + 4, dtype=float
        ).reshape(-1, 1)
        predictions = np.maximum(
            0, np.rint(model.predict(future_positions))
        ).astype(int)
        future_periods = pd.period_range(
            start=periods[-1] + 1, periods=4, freq="W"
        )
        return {
            "weekly": weekly,
            "forecast": [
                {"week": str(period), value_key: int(prediction)}
                for period, prediction in zip(future_periods, predictions)
            ],
            "message": (
                "توقع خطي للأربعة أسابيع التالية باستخدام "
                "scikit-learn LinearRegression؛ وهو تقدير استرشادي "
                "مبني على السجل الأسبوعي المتاح."
            ),
        }

class LessonHistoryLoadWorker(QObject):
    result_ready = Signal(object, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self, database_path, weekday_num, existing_count,
        generate_defaults=True,
    ):
        super().__init__()
        self.database_path = database_path
        self.weekday_num = weekday_num
        self.existing_count = existing_count
        self.generate_defaults = generate_defaults

    @Slot()
    def run(self):
        import pandas as pd

        try:
            with connect_database(self.database_path, timeout=10) as con:
                history = pd.read_sql_query("""
                    SELECT COALESCE(g.group_key, c.name) AS classe,
                        m.name AS majal, h.heure, h.time,
                        h.wehda_number, h.hessa_number,
                        lm.name AS namat_taallom, d.date
                    FROM hessa h
                    JOIN day_data d ON h.day_data_id = d.id
                    JOIN classe c ON c.id = h.classe_id
                    LEFT JOIN class_group g ON g.id=h.class_group_id
                    LEFT JOIN majal m ON m.id=h.majal_id
                    LEFT JOIN learning_mode lm ON lm.id=h.learning_mode_id
                """, con)

            defaults = None
            if self.generate_defaults and not history.empty:
                history["date"] = pd.to_datetime(
                    history["date"], errors="coerce"
                )
                same_weekday = history[
                    history["date"].dt.dayofweek == self.weekday_num
                ]
                if self.existing_count < len(same_weekday) and not same_weekday.empty:
                    def most_common(column, fallback):
                        values = same_weekday[column].mode()
                        return values.iloc[0] if not values.empty else fallback

                    defaults = {
                        "classe": most_common("classe", ""),
                        "majal": most_common("majal", ""),
                        "heure": most_common("heure", "08:00-09:00"),
                        "time": most_common("time", "60 دقيقة"),
                        "namat": most_common("namat_taallom", "منهجي"),
                    }
            self.result_ready.emit(history, defaults)
        except (sqlite3.Error, pd.errors.DatabaseError) as exc:
            self.failed.emit(f"تعذر تحميل سجل الحصص السابقة: {exc}")
        finally:
            self.finished.emit()


class TimetableLoadWorker(QObject):
    result_ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, database_path, year_id):
        super().__init__()
        self.database_path = database_path
        self.year_id = year_id

    @Slot()
    def run(self):
        import pandas as pd

        try:
            with connect_database(self.database_path, timeout=10) as con:
                history = pd.read_sql_query("""
                    SELECT COALESCE(g.group_key, c.name) AS classe,
                        m.name AS majal, h.heure, h.time,
                        h.wehda_number, h.hessa_number,
                        lm.name AS namat_taallom, d.date,
                        (
                            SELECT club.name
                            FROM nachat n
                            JOIN cultural_club_section club_section
                                ON club_section.section_name=c.name
                            JOIN cultural_club club
                                ON club.id=club_section.club_id
                                AND club.ann_scolaire_id=d.ann_scolaire_id
                                AND club.club_type=m.name
                                AND club.name=n.title
                            WHERE n.hessa_id=h.id
                                AND n.classe_id=c.id
                            ORDER BY n.id
                            LIMIT 1
                        ) AS cultural_club_name
                    FROM hessa h
                    JOIN day_data d ON h.day_data_id = d.id
                    JOIN classe c ON c.id = h.classe_id
                    LEFT JOIN class_group g ON g.id=h.class_group_id
                    LEFT JOIN majal m ON m.id=h.majal_id
                    LEFT JOIN learning_mode lm ON lm.id=h.learning_mode_id
                    WHERE d.ann_scolaire_id = ?
                """, con, params=(self.year_id,))
            group_labels = {
                group_key: level_firak_label(group_key)
                for group_key in LEVEL_FIRAKS
            }
            history["classe"] = history["classe"].map(
                lambda name: (
                    f"{name} — {group_labels[name]}"
                    if name in group_labels else name
                )
            )
            history["classe"] = history.apply(
                lambda row: (
                    f"ناد: {club_name}"
                    if (club_name := str(
                        row.cultural_club_name
                        if pd.notna(row.cultural_club_name) else ""
                    ).strip())
                    and club_name.casefold() not in {"nan", "none"}
                    else row.classe
                ),
                axis=1,
            )
            first_hour, last_hour = TimetableDialog.schedule_time_bounds(
                history
            )
            schedule = TimetableDialog.build_schedule(
                history, first_hour, last_hour
            )
            self.result_ready.emit(
                (schedule, first_hour, last_hour)
            )
        except (sqlite3.Error, pd.errors.DatabaseError, ValueError, TypeError) as exc:
            self.failed.emit(f"تعذر توليد جدول الأوقات: {exc}")
        finally:
            self.finished.emit()


class MonthlyClubPlanCard(QFrame):
    editRequested = Signal(int)
    deleteRequested = Signal(object)
    exportPdfRequested = Signal(object)
    printRequested = Signal(object)
    previewRequested = Signal(object)
    exportJsonRequested = Signal(object)

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.setObjectName("monthlyClubPlanCard")
        self.setMinimumWidth(480)
        self.setMaximumWidth(760)
        self.setStyleSheet(
            "QFrame#monthlyClubPlanCard { background:#FFFFFF; "
            "border:1px solid #CBD5E1; border-right:4px solid #2563EB; "
            "border-radius:8px; }"
        )
        self.edit_button = QToolButton(self)
        self.edit_button.setObjectName("monthlyClubPlanEditButton")
        self.edit_button.setText("")
        set_card_action_type(self.edit_button, "edit")
        self.edit_button.setToolTip("تعديل المخطط")
        self.edit_button.setAccessibleName("تعديل المخطط")
        self.edit_button.setFixedSize(28, 28)
        self.edit_button.clicked.connect(
            lambda: self.editRequested.emit(int(plan["id"]))
        )
        self.delete_button = QToolButton(self)
        self.delete_button.setObjectName("monthlyClubPlanDeleteButton")
        self.delete_button.setText("")
        set_card_action_type(self.delete_button, "delete")
        self.delete_button.setToolTip("مسح المخطط")
        self.delete_button.setAccessibleName("مسح المخطط")
        self.delete_button.setFixedSize(28, 28)
        self.delete_button.clicked.connect(
            lambda: self.deleteRequested.emit(plan)
        )
        self.export_pdf_button = self._create_action_button(
            "monthlyClubPlanExportPdfButton",
            "تصدير PDF",
            "export",
        )
        self.export_pdf_button.clicked.connect(
            lambda: self.exportPdfRequested.emit(plan)
        )
        self.print_button = self._create_action_button(
            "monthlyClubPlanPrintButton",
            "طباعة المخطط",
            "print",
        )
        self.print_button.clicked.connect(
            lambda: self.printRequested.emit(plan)
        )
        self.preview_button = self._create_action_button(
            "monthlyClubPlanPreviewButton",
            "عرض قبل الطباعة",
            "browse",
        )
        self.preview_button.clicked.connect(
            lambda: self.previewRequested.emit(plan)
        )
        self.export_json_button = self._create_action_button(
            "monthlyClubPlanExportJsonButton",
            "تصدير JSON",
            "export",
        )
        self.export_json_button.clicked.connect(
            lambda: self.exportJsonRequested.emit(plan)
        )
        self.action_buttons = (
            self.delete_button,
            self.edit_button,
            self.export_pdf_button,
            self.print_button,
            self.preview_button,
            self.export_json_button,
        )

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(12, 10, 12, 10)
        self.content_layout.setSpacing(6)
        title = QLabel(str(plan.get("club_name") or "نادي دون اسم"), self)
        title.setStyleSheet(
            "font-size:14px; font-weight:700; color:#1E3A8A;"
        )
        self.content_layout.addWidget(title)

    def _create_action_button(self, object_name, tooltip, action_type):
        button = QToolButton(self)
        button.setObjectName(object_name)
        set_card_action_type(button, action_type)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(28, 28)
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for index, button in enumerate(self.action_buttons):
            button.move(8 + index * 32, 8)
            button.raise_()


class MonthlyClubPlanView(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._clubs_by_key = {}
        self._plans = []
        self._plans_by_key = {}
        self._selected_plan = None
        self.setObjectName("monthlyClubPlanView")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.monthly_activity_button = QPushButton(
            "عرض النشاط الشهري للنادي", self
        )
        self.monthly_activity_button.setObjectName(
            "monthlyClubActivityPreviewButton"
        )
        self.monthly_activity_button.setProperty("actionType", "browse")
        self.monthly_activity_button.setEnabled(False)
        self.monthly_activity_button.clicked.connect(
            self._preview_monthly_activity
        )
        actions.addWidget(self.monthly_activity_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        splitter.setChildrenCollapsible(False)

        content_panel = QWidget()
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_heading = QLabel("جلسات الشهر المحدد", content_panel)
        content_heading.setStyleSheet(
            "font-weight:bold; color:#123B67; padding:4px;"
        )
        content_layout.addWidget(content_heading)

        self.sessions_scroll = QScrollArea(content_panel)
        self.sessions_scroll.setWidgetResizable(True)
        self.sessions_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sessions_container = QWidget(self.sessions_scroll)
        self.sessions_layout = QGridLayout(self.sessions_container)
        self.sessions_layout.setContentsMargins(4, 4, 4, 4)
        self.sessions_layout.setHorizontalSpacing(12)
        self.sessions_layout.setVerticalSpacing(12)
        self.sessions_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self._session_cards = []
        self._session_grid_columns = 1
        self.sessions_scroll.setWidget(self.sessions_container)
        content_layout.addWidget(self.sessions_scroll, 1)

        self.plan_tree = QTreeWidget()
        self.plan_tree.setObjectName("monthlyClubViewPlanTree")
        self.plan_tree.setHeaderHidden(True)
        self.plan_tree.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.plan_tree.setUniformRowHeights(True)
        self.plan_tree.setStyleSheet("""
            QTreeWidget {
                background:#FFFFFF;
                border:1px solid #D9E2EF;
                border-radius:10px;
                color:#1E293B;
                padding:6px;
            }
            QTreeWidget::item { padding:5px 3px; }
            QTreeWidget::item:selected {
                background:#DBEAFE;
                color:#123B67;
                border-radius:5px;
            }
        """)
        self.plan_tree.currentItemChanged.connect(
            self._on_tree_selection_changed
        )
        tree_panel = QFrame()
        tree_panel.setMinimumWidth(190)
        tree_panel.setStyleSheet(
            "QFrame { background:#F8FAFC; border:1px solid #D9E2EF; "
            "border-radius:12px; }"
        )
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(8)
        tree_heading = QLabel(
            "المخططات حسب السنة والنادي والشهر والجلسة", tree_panel
        )
        tree_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tree_heading.setStyleSheet(
            "font-weight:bold; color:#123B67; border:none;"
        )
        tree_layout.addWidget(tree_heading)
        tree_layout.addWidget(self.plan_tree, 1)

        splitter.addWidget(content_panel)
        splitter.addWidget(tree_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([760, 300])
        self.plan_splitter = splitter
        layout.addWidget(splitter, 1)

        self.refresh()

    def refresh(self):
        selected_key = (
            self._selected_plan["tree_key"]
            if self._selected_plan is not None else None
        )
        years = self.db.school_years()
        locale = QLocale(QLocale.Language.Arabic, QLocale.Country.Tunisia)
        self._clubs_by_key = {}
        self._plans = []
        self._plans_by_key = {}
        for year_id, year_name in years:
            clubs = self.db.cultural_clubs(year_id)
            for club in clubs:
                self._clubs_by_key[(year_id, club["id"])] = club
            for plan in self.db.cultural_club_monthly_plans(year_id):
                plan = dict(plan)
                plan["year_id"] = year_id
                plan["school_year_name"] = year_name
                plan["tree_key"] = (year_id, plan["id"])
                self._plans.append(plan)
                self._plans_by_key[plan["tree_key"]] = plan

        self.plan_tree.blockSignals(True)
        self.plan_tree.clear()
        self._selected_plan = None
        folder_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DirIcon
        )
        file_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileIcon
        )
        year_nodes = {}
        club_nodes = {}
        month_items = {}
        year_names = dict(years)
        for plan in self._plans:
            year_id = plan["year_id"]
            year_node = year_nodes.get(year_id)
            if year_node is None:
                year_node = QTreeWidgetItem([
                    str(year_names.get(year_id) or year_id)
                ])
                year_node.setIcon(0, folder_icon)
                year_node.setData(
                    0, Qt.ItemDataRole.UserRole, "year"
                )
                self.plan_tree.addTopLevelItem(year_node)
                year_nodes[year_id] = year_node

            club_key = (year_id, plan["club_id"])
            club_node = club_nodes.get(club_key)
            if club_node is None:
                club = self._clubs_by_key.get(club_key, {})
                club_name = str(
                    club.get("name") or plan.get("club_name") or "نادي"
                )
                club_type = str(club.get("club_type") or plan.get(
                    "club_type"
                ) or "").strip()
                club_label = (
                    f"{club_name} — {club_type}"
                    if club_type else club_name
                )
                club_node = QTreeWidgetItem([club_label])
                club_node.setIcon(0, folder_icon)
                club_node.setData(
                    0, Qt.ItemDataRole.UserRole, "club"
                )
                year_node.addChild(club_node)
                club_nodes[club_key] = club_node

            month_date = QDate.fromString(
                f"{plan.get('month') or ''}-01", "yyyy-MM-dd"
            )
            month_label = (
                locale.toString(month_date, "MMMM yyyy")
                if month_date.isValid()
                else str(plan.get("month") or "شهر غير محدد")
            )
            month_node = QTreeWidgetItem([month_label])
            month_node.setIcon(0, folder_icon)
            month_node.setData(
                0, Qt.ItemDataRole.UserRole, "month"
            )
            month_node.setData(
                0, Qt.ItemDataRole.UserRole + 1, plan["tree_key"]
            )
            club_node.addChild(month_node)
            month_items[plan["tree_key"]] = month_node

            for index, session in enumerate(
                plan.get("sessions", []), start=1
            ):
                session_date = QDate.fromString(
                    str(session.get("session_date") or ""), "yyyy-MM-dd"
                )
                session_label = (
                    locale.toString(
                        session_date, "dddd، dd/MM/yyyy"
                    )
                    if session_date.isValid()
                    else str(session.get("session_date") or "تاريخ غير محدد")
                )
                session_node = QTreeWidgetItem([
                    f"الجلسة {index} · {session_label}"
                ])
                session_node.setIcon(0, file_icon)
                session_node.setData(
                    0, Qt.ItemDataRole.UserRole, "session"
                )
                session_node.setData(
                    0, Qt.ItemDataRole.UserRole + 1, plan["tree_key"]
                )
                month_node.addChild(session_node)

        self.plan_tree.collapseAll()
        selected_item = month_items.get(selected_key)
        if selected_item is not None:
            self.plan_tree.setCurrentItem(selected_item)
            parent = selected_item.parent()
            if parent is not None:
                parent.setExpanded(True)
                if parent.parent() is not None:
                    parent.parent().setExpanded(True)
        self.plan_tree.blockSignals(False)
        if selected_item is not None:
            self._on_tree_selection_changed(selected_item, None)
        else:
            self._render_sessions()

    def _on_tree_selection_changed(self, current, _previous):
        kind = (
            current.data(0, Qt.ItemDataRole.UserRole)
            if current is not None else None
        )
        key = (
            current.data(0, Qt.ItemDataRole.UserRole + 1)
            if kind in {"month", "session"} else None
        )
        self._selected_plan = self._plans_by_key.get(key)
        self._render_sessions()

    def _clear_sessions(self):
        self.monthly_activity_button.setEnabled(False)
        while self.sessions_layout.count():
            item = self.sessions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._session_cards = []

    def _arrange_session_cards(self):
        if not self._session_cards:
            return
        available_width = max(
            self.sessions_scroll.viewport().width(),
            self.sessions_container.width(),
        )
        card_minimum_width = 520
        horizontal_spacing = self.sessions_layout.horizontalSpacing()
        columns = max(
            1,
            min(
                len(self._session_cards),
                (available_width + horizontal_spacing)
                // (card_minimum_width + horizontal_spacing),
            ),
        )
        if columns == self._session_grid_columns and all(
            self.sessions_layout.itemAtPosition(row, column) is not None
            for row, column in (
                (index // columns, index % columns)
                for index in range(len(self._session_cards))
            )
        ):
            return
        while self.sessions_layout.count():
            self.sessions_layout.takeAt(0)
        self._session_grid_columns = columns
        for index, card in enumerate(self._session_cards):
            self.sessions_layout.addWidget(
                card,
                index // columns,
                index % columns,
                Qt.AlignmentFlag.AlignHCenter,
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._arrange_session_cards)

    def _render_sessions(self):
        self._clear_sessions()
        plan = self._selected_plan
        if plan is None:
            message = (
                "اختر السنة الدراسية والنادي والشهر من الشجرة لعرض الجلسات."
                if self._plans else "لا توجد مخططات شهرية محفوظة."
            )
            self._add_empty_message(message)
            return

        session_colors = (
            ("#EFF6FF", "#2563EB", "#BFDBFE", "#1E3A8A"),
            ("#ECFDF5", "#059669", "#A7F3D0", "#065F46"),
            ("#FFF7ED", "#EA580C", "#FED7AA", "#9A3412"),
            ("#FDF2F8", "#DB2777", "#FBCFE8", "#9D174D"),
            ("#ECFEFF", "#0891B2", "#A5F3FC", "#155E75"),
            ("#F7FEE7", "#65A30D", "#D9F99D", "#3F6212"),
        )
        for index, session in enumerate(plan["sessions"], start=1):
            tint, accent, border, foreground = session_colors[
                (index - 1) % len(session_colors)
            ]
            card = QFrame(self.sessions_container)
            card.setObjectName("monthlyClubViewSessionCard")
            card.setMinimumWidth(520)
            card.setMaximumWidth(1100)
            card.setStyleSheet(
                "QFrame#monthlyClubViewSessionCard { "
                f"background:{tint}; border:1px solid {border}; "
                f"border-right:4px solid {accent}; "
                "border-radius:8px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(7)

            header = QHBoxLayout()
            date = QDate.fromString(session["session_date"], "yyyy-MM-dd")
            date_text = (
                QLocale(QLocale.Language.Arabic, QLocale.Country.Tunisia)
                .toString(date, "dddd، dd/MM/yyyy")
                if date.isValid() else session["session_date"]
            )
            date_label = QLabel(f"الجلسة {index} · {date_text}", card)
            date_label.setObjectName("monthlyClubViewSessionDate")
            date_label.setStyleSheet(
                "font-weight:700; "
                f"color:{foreground}; background:transparent;"
            )
            header.addWidget(date_label, 1)
            absent_count = int(session.get("absent_count") or 0)
            absence_count_label = QLabel(
                f"الغيابات: {absent_count}", card
            )
            absence_count_label.setObjectName(
                "monthlyClubSessionAbsenceCount"
            )
            absence_count_label.setStyleSheet(
                f"color:{foreground}; background:{tint}; "
                f"border:1px solid {border}; border-radius:6px; "
                "padding:4px 8px; font-weight:600;"
            )
            header.addWidget(absence_count_label)
            absence_button = QToolButton(card)
            absence_button.setObjectName(
                "monthlyClubSessionAbsencesButton"
            )
            absence_button.setText("")
            absence_button.setAccessibleName("تحديد غيابات الجلسة")
            absence_button.setToolTip(
                "تحديد عدد التلاميذ الغائبين عن هذه الجلسة"
            )
            absence_button.setFixedSize(30, 30)
            absence_button.setStyleSheet(
                "QToolButton { background:transparent; border:none; "
                "padding:0; color:#475569; font-size:17px; }"
                "QToolButton:hover { background:transparent; "
                f"color:{accent}; }}"
            )
            set_action_button_type(absence_button, "edit")
            absence_button.clicked.connect(
                lambda _checked=False, item=session:
                self._edit_absence_count(item)
            )
            header.addWidget(absence_button)
            card_layout.addLayout(header)

            for detail in session.get("properties", []):
                detail_label = QLabel(card)
                detail_label.setObjectName("monthlyClubViewSessionDetail")
                detail_label.setWordWrap(True)
                detail_label.setStyleSheet(
                    "color:#334155; background:transparent;"
                )
                indent_width = max(
                    1,
                    detail_label.fontMetrics().horizontalAdvance("  "),
                )
                detail_lines = str(
                    detail.get("value_text") or ""
                ).splitlines() or [""]
                detail_name = html.escape(
                    str(detail.get("key_name") or ""), quote=True
                )
                detail_blocks = []
                for line_index, line in enumerate(detail_lines):
                    label_text = (
                        f"<span style='color:{accent}; font-weight:700;'>"
                        f"{detail_name}:</span> "
                        if line_index == 0 else ""
                    )
                    line_text = html.escape(line, quote=True) or "&nbsp;"
                    detail_blocks.append(
                        "<div style='margin:0px; "
                        f"margin-right:{indent_width}px;'>"
                        f"{label_text}<span style='color:#334155;'>"
                        f"{line_text}</span></div>"
                    )
                detail_label.setTextFormat(Qt.TextFormat.RichText)
                detail_label.setText("".join(detail_blocks))
                card_layout.addWidget(detail_label)
            self._session_cards.append(card)

        if not plan["sessions"]:
            self._add_empty_message("لا توجد جلسات محفوظة لهذا الشهر.")
        else:
            self._session_grid_columns = 0
            self._arrange_session_cards()
            self.monthly_activity_button.setEnabled(bool(self._session_cards))

    def _monthly_activity_preview_payload(self, plan):
        year_id = plan.get("year_id")
        school_row = self.db.school_info(year_id)
        if not school_row:
            raise ValueError("بيانات السنة الدراسية المحددة غير موجودة.")
        school = dict(zip(SCHOOL_INFO_COLUMNS, school_row))
        club = self._clubs_by_key.get(
            (year_id, plan.get("club_id")), {}
        )
        participant_count = int(club.get("participant_count") or 0)
        locale = QLocale(QLocale.Language.Arabic, QLocale.Country.Tunisia)
        month_date = QDate.fromString(
            f"{plan.get('month') or ''}-01", "yyyy-MM-dd"
        )
        month_name = (
            locale.toString(month_date, "MMMM yyyy")
            if month_date.isValid() else str(plan.get("month") or "—")
        )

        schedule = self.db.teacher_timetable(year_id) or {}
        cards_by_id = {
            str(card.get("id")): card
            for card in schedule.get("cards", [])
            if isinstance(card, dict)
        }
        timetable_entries = []
        for entry in schedule.get("entries", []):
            if not isinstance(entry, dict):
                continue
            card = cards_by_id.get(str(entry.get("card_id")))
            if str((card or {}).get("club_id")) != str(plan.get("club_id")):
                continue
            start_text = str(entry.get("start_time") or "")
            start_time = QTime.fromString(start_text, "HH:mm")
            try:
                duration = float(entry.get("duration_hours") or 1)
            except (TypeError, ValueError):
                duration = 1
            end_time = start_time.addSecs(round(duration * 3600))
            if start_time.isValid() and end_time.isValid():
                weekday_value = entry.get("weekday")
                weekday_name = next((
                    name for name, day_number in WEEKDAYS
                    if weekday_value == name
                    or str(weekday_value) == str(day_number)
                ), "—")
                timetable_entries.append(
                    f"{weekday_name}، من الساعة "
                    f"{start_time.toString('HH:mm')} إلى "
                    f"{end_time.toString('HH:mm')}"
                )

        sessions = []
        for index, session in enumerate(plan.get("sessions", []), start=1):
            properties = session.get("properties", [])
            content = next((
                str(item.get("value_text") or "").strip()
                for item in properties
                if str(item.get("key_name") or "").strip().casefold()
                == "المحتوى"
            ), "")
            absent_count = int(session.get("absent_count") or 0)
            sessions.append({
                "number": index,
                "participant_count": participant_count,
                "absent_count": absent_count,
                "present_count": max(0, participant_count - absent_count),
                "content": content or "—",
                "sections": [
                    {
                        "section_name": section.get("section_name") or "",
                        "female_count": int(
                            section.get("female_count") or 0
                        ),
                        "male_count": int(section.get("male_count") or 0),
                    }
                    for section in club.get("sections", [])
                ],
            })

        title = (
            "جدول الأنشطة الشهرية للنوادي الثقافية والفنية "
            f"للسنة الدراسية {school.get('nom_annee') or '—'}"
        )
        club_schedule = "\n".join(timetable_entries) or "—"
        return {
            "date": QDate.currentDate().toString("yyyy-MM-dd"),
            "preview_title": f"معاينة {title}",
            "monthly_club_document": {
                "title": title,
                "school_year": school.get("nom_annee"),
                "delegation": school.get("delegation_regional_education"),
                "club_name": plan.get("club_name"),
                "club_schedule": club_schedule,
                "school_name": school.get("nom_ecole"),
                "school_address": school.get("school_address"),
                "inspection_district": school.get("inspection_district"),
                "inspector_name": school.get("nom_inspecteur"),
                "school_principal": school.get("school_principal"),
                "school_phone": school.get("school_phone"),
                "principal_email": school.get("email_school_principal"),
                "teacher_name": school.get("nom_enseignant"),
                "teacher_phone": school.get("telephone"),
                "teacher_grade": school.get("grade"),
                "teacher_identifier": school.get("identifiant_unique"),
                "teacher_degree": school.get("diplomes_scientifiques"),
                "teacher_training_certificates": school.get(
                    "training_certificates"
                ),
                "month": month_name,
                "sessions": sessions,
                "signature_date": QDate.currentDate().toString("dd/MM/yyyy"),
            },
        }

    def _preview_monthly_activity(self):
        from day_pdf_preview import DayPdfPreviewDialog

        plan = self._selected_plan
        if plan is None or not self._session_cards:
            self.monthly_activity_button.setEnabled(False)
            return
        try:
            payload = self._monthly_activity_preview_payload(plan)
            DayPdfPreviewDialog(payload, self).exec()
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            QMessageBox.warning(
                self, "تعذرت معاينة النشاط الشهري", str(error)
            )

    def _add_empty_message(self, message):
        label = QLabel(message, self.sessions_container)
        label.setObjectName("monthlyClubViewEmptyMessage")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color:#64748B; padding:24px;")
        self.sessions_layout.addWidget(
            label, 0, 0, 1, 1, Qt.AlignmentFlag.AlignHCenter
        )

    def _edit_absence_count(self, session):
        plan = self._selected_plan
        if plan is None:
            return
        club = self._clubs_by_key.get(
            (plan["year_id"], plan["club_id"]), {}
        )
        participant_count = int(club.get("participant_count") or 0)
        current_count = int(session.get("absent_count") or 0)
        maximum = max(participant_count, current_count)
        if maximum == 0:
            maximum = 999
        count, accepted = QInputDialog.getInt(
            self,
            "غيابات الجلسة",
            "عدد التلاميذ الغائبين:",
            current_count,
            0,
            maximum,
        )
        if not accepted:
            return
        try:
            self.db.set_cultural_club_monthly_session_absences(
                plan["year_id"], session["id"], count
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.warning(
                self, "تعذر حفظ الغيابات", str(error)
            )
            return
        self.refresh()


class SchoolPlanner(QMainWindow):
    def __init__(self, db=None):
        super().__init__()
        self.db = db if db is not None else Database(DB_PATH)
        self.day_id = None
        self.selected_lesson_id = None
        self.selected_activity_id = None
        self.copied_details = []
        self.copied_lessons = []
        self.is_school_year_read_only = False
        
        self.setWindowTitle("المعين للتخطيط اليومي للحصص")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        available_geometry = self.screen().availableGeometry()
        self.setMinimumSize(
            min(900, max(320, available_geometry.width() - 48)),
            min(600, max(240, available_geometry.height() - 80)),
        )
        self.resize(1250, 800)
        self._small_window_profile = is_small_window(self)
        self._small_profile_ui_ready = False
        self.setLayoutDirection(Qt.RightToLeft)
        self.build_ui()
        self._small_profile_ui_ready = True
        self.set_small_window_profile(
            is_small_window(self)
        )
        self.load_school_info()

        self.db.cleanup_empty_days()
        workdays = self.db.recorded_workdays()
        if workdays:
            day_id, latest_date_str = workdays[0]
            qd = QDate.fromString(latest_date_str, "yyyy-MM-dd")
            if qd.isValid():
                self.date_edit.setDate(qd)
        
        self.load_day()
        self.refresh_notification_badge(force=True)
        if workdays:
            self.day_lessons_page.set_day(day_id, latest_date_str)
            self.pages_stack.setCurrentWidget(self.day_lessons_page)
        else:
            self.pages_stack.setCurrentWidget(self.lesson_page)
        self.setStyleSheet("QLineEdit { qproperty-alignment: AlignCenter; }")
        if not workdays:
            QTimer.singleShot(
                0,
                lambda: QMessageBox.information(
                    self,
                    "لا يوجد يوم عمل مسجل",
                    "لا يوجد يوم عمل مسجل بعد. تم فتح صفحة تصفح دفتر إعداد الدروس.",
                ),
            )
        self.setAcceptDrops(True)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_small_window_profile()

    def _sync_small_window_profile(self):
        if not getattr(self, "_small_profile_ui_ready", False):
            return

        should_use_small_profile = is_small_window(self)
        if should_use_small_profile != self._small_window_profile:
            self.set_small_window_profile(should_use_small_profile)


    def build_ui(self):
        self._year_scoped_mutation_widgets = []
        self._year_scoped_mutation_actions = []
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        from PySide6.QtGui import QKeySequence, QShortcut
        self.competence_shortcut = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        self.competence_shortcut.activated.connect(self.open_competence_manager)
        self.concept_shortcut = QShortcut(QKeySequence("Ctrl+Shift+R"), self)
        self.concept_shortcut.activated.connect(self.open_concept_manager)

        self.teacher_info_page = TeacherInfoPage(self)
        self.teacher_info_page.saveRequested.connect(self.save_school_info)

        agenda = QGroupBox("اليوم الدراسي")
        agenda_layout = QVBoxLayout(agenda)
        agenda_row = QHBoxLayout()
        agenda_layout.addLayout(agenda_row)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dddd، dd/MM/yyyy")
        self.date_edit.setLocale(QLocale(QLocale.Arabic, QLocale.Tunisia))
        self.date_edit.setMinimumWidth(130)

        self.custom_calendar = CustomCalendarWidget(self.db, self.date_edit)
        self.date_edit.setCalendarWidget(self.custom_calendar)
        self.set_lesson_date_range()
        self.custom_calendar.set_holiday_date_disabling_enabled(True)
        if self.date_edit.date() in self.custom_calendar._disabled_dates:
            self.date_edit.setDate(self.custom_calendar._last_enabled_date)
        self._last_enabled_agenda_date = self.date_edit.date()
        self.date_edit.dateChanged.connect(self.on_agenda_date_changed)
        agenda_row.addWidget(self.date_edit)
        self.day_status = QLabel()
        self.day_status.setWordWrap(True)
        agenda_layout.addWidget(self.day_status)
        self.prev_btn = QPushButton("اليوم السابق")
        self.prev_btn.setProperty("actionType", "browse")
        _configure_icon_button(
            self.prev_btn,
            QStyle.StandardPixmap.SP_ArrowLeft,
            "اليوم الدراسي السابق",
        )
        self.view_day_btn = QPushButton("عرض اليوم")
        self.view_day_btn.setObjectName("viewDayButton")
        self.view_day_btn.setProperty("actionType", "browse")
        _configure_icon_button(
            self.view_day_btn,
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            "عرض اليوم المسجل",
        )
        self.view_day_btn.setEnabled(False)
        self.view_day_btn.clicked.connect(self.open_day_lessons_view)
        self.next_btn = QPushButton("اليوم التالي")
        self.next_btn.setProperty("actionType", "browse")
        _configure_icon_button(
            self.next_btn,
            QStyle.StandardPixmap.SP_ArrowRight,
            "اليوم الدراسي التالي",
        )
        self.prev_btn.clicked.connect(self.show_previous_recorded_workday)
        self.next_btn.clicked.connect(self.show_next_recorded_workday)
        for button in (self.prev_btn, self.view_day_btn, self.next_btn):
            button.setFixedWidth(42)
            agenda_row.addWidget(button)

        self.lesson_loading_label = QLabel()
        self.lesson_loading_label.setAlignment(Qt.AlignCenter)
        self.lesson_loading_label.setStyleSheet(
            "color: #1E3A8A; background-color: #EFF6FF; "
            "border: 1px solid #BFDBFE; border-radius: 8px; "
            "padding: 6px; font-weight: bold;"
        )
        self.lesson_loading_label.hide()
        self.lesson_table = self.make_table(
            ["المعرّف", " الحصة", "القسم", "المجال ", "التوقيت",
             "المدة", " الوحدة", "نمط التعلم"]
        )
        self.lesson_table.setParent(self)
        self.lesson_table.setColumnHidden(0, True)
        self.lesson_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lesson_table.itemSelectionChanged.connect(self.on_lesson_selected)
        self.lesson_table.hide()

        lower = QSplitter(Qt.Horizontal)

        act_box = QGroupBox("أنشطة الحصة المحددة")
        act_layout = QVBoxLayout(act_box)
        act_layout.setContentsMargins(9, 9, 4, 9)
        act_buttons = QHBoxLayout()

        for label, callback, act_type in [
            ("إضافة نشاط", self.add_activity, "add"),
            ("مسح كل الأنشطة", self.clear_all_activities_for_lesson, "clear")
        ]:
            b = QPushButton(label)
            b.clicked.connect(callback)
            b.setProperty("actionType", act_type)
            act_buttons.addWidget(b)
            if act_type in {"add", "edit", "delete", "copy_paste", "clear"}:
                self._year_scoped_mutation_widgets.append(b)
            if label == "إضافة نشاط":
                self.add_activity_button = b
                b.setEnabled(False)

        act_layout.addLayout(act_buttons)
        self.activity_cards = ActivityCardsWidget()
        self.activity_cards.actionRequested.connect(
            self.on_activity_card_action
        )
        self.activity_cards.itemSelectionChanged.connect(
            self.on_activity_selected
        )
        act_layout.addWidget(self.activity_cards, 1)

        lower.addWidget(act_box)

        detail_box = QGroupBox("خصائص النشاط المحدد (اسم الخاصية / قيمتها)")
        detail_layout = QVBoxLayout(detail_box)
        detail_buttons = QHBoxLayout()

        for label, callback, act_type in [
            ("إضافة خاصية", self.add_detail, "add"),
            ("نسخ الخصائص", self.copy_activity_details, "copy_paste"),
            ("لصق الخصائص", self.paste_activity_details, "copy_paste"),
            ("مسح كل الخصائص", self.clear_all_details_for_activity, "clear")
        ]:
            b = QPushButton(label)
            b.clicked.connect(callback)
            b.setProperty("actionType", act_type)
            detail_buttons.addWidget(b)
            if act_type in {"add", "edit", "delete", "copy_paste", "clear"}:
                self._year_scoped_mutation_widgets.append(b)

        detail_layout.addLayout(detail_buttons)
        self.detail_cards = DetailCardsWidget()
        self.detail_cards.actionRequested.connect(
            self.on_detail_card_action
        )
        detail_layout.addWidget(self.detail_cards, 1)

        lower.addWidget(detail_box)
        lower.setStretchFactor(0, 1)
        lower.setStretchFactor(1, 1)
        lower.setSizes([300, 600])

        self.schedule_group = QGroupBox("حصص اليوم حسب جدول الأوقات")
        schedule_layout = QVBoxLayout(self.schedule_group)
        self.schedule_source_status = QLabel()
        self.schedule_source_status.setWordWrap(True)
        self.schedule_source_status.setStyleSheet("color: #64748B;")
        schedule_layout.addWidget(self.schedule_source_status)
        self.scheduled_lessons_list = ScheduledLessonsListWidget()
        self.scheduled_lessons_list.emptyCardActivated.connect(self.add_lesson)
        self.scheduled_club_lessons_list = ScheduledLessonsListWidget()
        self.scheduled_club_lessons_list.emptyCardActivated.connect(
            self.add_unprogrammed_club_session
        )
        self.scheduled_exam_lessons_list = ScheduledLessonsListWidget()
        self.scheduled_exam_lessons_list.setDragEnabled(True)
        self.scheduled_exam_lessons_list.setDragDropMode(
            QAbstractItemView.DragDropMode.DragOnly
        )
        self.scheduled_exam_lessons_list.setDefaultDropAction(
            Qt.DropAction.CopyAction
        )
        self.scheduled_exam_lessons_list.itemDoubleClicked.connect(
            self._add_scheduled_exam_from_card
        )
        self.scheduled_lessons_tabs = QTabWidget()
        self.scheduled_lessons_tabs.setObjectName("scheduledLessonsTabs")
        self.scheduled_lessons_tabs.addTab(
            self.scheduled_lessons_list, "ح بيداغوجية"
        )
        self.scheduled_lessons_tabs.addTab(
            self.scheduled_club_lessons_list, "ح نوادي"
        )
        self.scheduled_lessons_tabs.addTab(
            self.scheduled_exam_lessons_list,
            "ح تقييم",
        )
        scheduled_tabs_bar = self.scheduled_lessons_tabs.tabBar()
        scheduled_tabs_minimum_width = sum(
            scheduled_tabs_bar.tabSizeHint(index).width()
            for index in range(scheduled_tabs_bar.count())
        )
        scheduled_tabs_bar.setMinimumWidth(scheduled_tabs_minimum_width)
        self.scheduled_lessons_tabs.setMinimumWidth(
            scheduled_tabs_minimum_width
            + self.scheduled_lessons_tabs.contentsMargins().left()
            + self.scheduled_lessons_tabs.contentsMargins().right()
            + 2
        )
        schedule_layout.addWidget(self.scheduled_lessons_tabs, 1)
        schedule_actions = QHBoxLayout()
        self.add_all_lessons_button = QPushButton("إضافة كل الحصص")
        self.add_all_lessons_button.setProperty("actionType", "add")
        self.add_all_lessons_button.clicked.connect(self.add_all_lessons)
        self._year_scoped_mutation_widgets.append(
            self.add_all_lessons_button
        )
        schedule_actions.addWidget(self.add_all_lessons_button)

        self.paste_lessons_button = QPushButton("لصق الحصة")
        self.paste_lessons_button.setToolTip("لصق الحصص المنسوخة في اليوم المحدد.")
        self.paste_lessons_button.setProperty("actionType", "copy_paste")
        self.paste_lessons_button.clicked.connect(self.paste_lessons)
        self.paste_lessons_button.setEnabled(bool(self.copied_lessons))
        self._year_scoped_mutation_widgets.append(
            self.paste_lessons_button
        )
        schedule_actions.addWidget(self.paste_lessons_button)

        self.clear_day_lessons_button = QPushButton("مسح اليوم")
        self.clear_day_lessons_button.setToolTip("مسح حصص اليوم المحدد.")
        self.clear_day_lessons_button.setProperty("actionType", "clear")
        self.clear_day_lessons_button.clicked.connect(
            self.clear_current_day_lessons
        )
        self._year_scoped_mutation_widgets.append(
            self.clear_day_lessons_button
        )
        schedule_actions.addWidget(self.clear_day_lessons_button)
        schedule_layout.addLayout(schedule_actions)

        schedule_column = QWidget()
        schedule_column_layout = QVBoxLayout(schedule_column)
        schedule_column_layout.setContentsMargins(0, 0, 0, 0)
        schedule_column_layout.addWidget(agenda)
        schedule_column_layout.addWidget(self.schedule_group, 1)

        current_section = QGroupBox("أنشطة الحصة وخصائص النشاط")
        current_section_layout = QVBoxLayout(current_section)
        current_section_layout.addWidget(self.lesson_loading_label)
        self.lesson_cards_hint = QLabel(
            "اسحب البطاقة إلى المساحة المناسبة؛ سيتغير لون الخلفية "
            "لتمييز مكان الإفلات."
        )
        self.lesson_cards_hint.setStyleSheet(
            "color: #475569; font-weight: 600; padding: 3px;"
        )
        current_section_layout.addWidget(self.lesson_cards_hint)
        self.recorded_lesson_cards = RecordedLessonCardsWidget()
        self.recorded_lesson_cards.actionRequested.connect(
            self.on_lesson_card_action
        )
        self.recorded_lesson_cards.lessonsDropped.connect(
            self.add_scheduled_lessons
        )
        self.recorded_lesson_cards.itemSelectionChanged.connect(
            self.on_lesson_card_selection_changed
        )
        self.pedagogical_drop_group = QGroupBox(
            "الحصص البيداغوجية العادية"
        )
        self.pedagogical_drop_group.setObjectName(
            "pedagogicalDropGroup"
        )
        drop_hint = self.lesson_cards_hint.text()
        self.pedagogical_drop_group.setToolTip(drop_hint)
        pedagogical_drop_layout = QVBoxLayout(
            self.pedagogical_drop_group
        )
        self.recorded_lesson_cards.setToolTip(drop_hint)
        pedagogical_drop_layout.addWidget(
            self.recorded_lesson_cards, 1
        )
        self.club_drop_group = QGroupBox("حصص النوادي")
        self.club_drop_group.setObjectName("clubDropGroup")
        self.club_drop_group.setToolTip(drop_hint)
        club_drop_layout = QVBoxLayout(self.club_drop_group)
        pedagogical_margins = pedagogical_drop_layout.contentsMargins()
        club_margins = club_drop_layout.contentsMargins()
        self._small_drop_group_layouts = (
            (
                self.pedagogical_drop_group,
                pedagogical_drop_layout,
                (
                    pedagogical_margins.left(),
                    pedagogical_margins.top(),
                    pedagogical_margins.right(),
                    pedagogical_margins.bottom(),
                ),
            ),
            (
                self.club_drop_group,
                club_drop_layout,
                (
                    club_margins.left(),
                    club_margins.top(),
                    club_margins.right(),
                    club_margins.bottom(),
                ),
            ),
        )
        self.cultural_club_session_cards = CulturalClubSessionCardsWidget()
        self.cultural_club_session_cards.setToolTip(drop_hint)
        self.cultural_club_session_cards.lessonsDropped.connect(
            self.add_scheduled_lessons
        )
        self.cultural_club_session_cards.actionRequested.connect(
            self.on_cultural_club_session_action
        )
        club_drop_layout.addWidget(self.cultural_club_session_cards, 1)

        self.lesson_drop_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.lesson_drop_splitter.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )
        self.lesson_drop_splitter.addWidget(self.club_drop_group)
        self.lesson_drop_splitter.addWidget(self.pedagogical_drop_group)
        self.lesson_drop_splitter.setStretchFactor(0, 0)
        self.lesson_drop_splitter.setStretchFactor(1, 1)
        self.lesson_drop_splitter.setSizes([340, 900])
        current_section_layout.addWidget(self.lesson_drop_splitter, 1)
        current_section_layout.addWidget(lower, 2)

        self.club_drop_group.hide()
        self.scheduled_lessons_tabs.currentChanged.connect(
            self._scheduled_lesson_tab_changed
        )

        workspace = QSplitter(Qt.Horizontal)
        workspace.setLayoutDirection(Qt.RightToLeft)
        workspace.addWidget(schedule_column)
        workspace.addWidget(current_section)
        workspace.setStretchFactor(0, 1)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([300, 900])

        self.stats_page = QWidget()
        stats_page_layout = QVBoxLayout(self.stats_page)
        stats_page_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_scroll_area = QScrollArea()
        self.stats_scroll_area.setWidgetResizable(True)
        self.stats_content = QWidget()
        stats_layout = QVBoxLayout(self.stats_content)
        stats_layout.setContentsMargins(24, 20, 24, 24)
        stats_layout.setSpacing(18)
        self.stats_scroll_area.setWidget(self.stats_content)
        stats_page_layout.addWidget(self.stats_scroll_area)

        stats_header_layout = QHBoxLayout()
        stats_title = QLabel("لوحة الإحصائيات والتوقعات")
        stats_title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #0F172A;"
        )
        self.refresh_stats_btn = QPushButton("تحديث التحليلات")
        self.refresh_stats_btn.setProperty("primary", "true")
        self.refresh_stats_btn.clicked.connect(
            lambda: self.load_statistics(force_refresh=True)
        )
        stats_header_layout.addWidget(stats_title)
        stats_header_layout.addStretch()
        stats_header_layout.addWidget(self.refresh_stats_btn)
        stats_layout.addLayout(stats_header_layout)

        self.stats_loading_label = QLabel()
        self.stats_loading_label.setObjectName("statsLoadingLabel")
        self.stats_loading_label.setAlignment(Qt.AlignCenter)
        self.stats_loading_label.hide()
        stats_layout.addWidget(self.stats_loading_label)

        self.stats_stack = QStackedWidget()
        self.stats_sections = {}
        self.stats_section_indices = {}
        self.stats_reports = {}

        def create_stats_section(key, title, description):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(14)
            heading = QLabel(title)
            heading.setStyleSheet(
                "font-size: 16pt; font-weight: 700; color: #0F172A;"
            )
            page_layout.addWidget(heading)
            if description:
                description_label = QLabel(description)
                description_label.setWordWrap(True)
                description_label.setStyleSheet("color: #64748B;")
                page_layout.addWidget(description_label)
            self.stats_sections[key] = page
            self.stats_section_indices[key] = (
                self.stats_stack.addWidget(page)
            )
            return page_layout

        overview_layout = create_stats_section(
            "overview",
            "دفتر إعداد الدروس",
            "مؤشرات الحصص المسجلة واكتمالها، مع توقع استرشادي للأسابيع القادمة.",
        )
        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(12)
        cards_grid.setVerticalSpacing(12)
        self.stats_cards = {}
        card_definitions = [
            ("lessons", "إجمالي الحصص", "0", "#2563EB"),
            ("days", "الأيام المسجلة", "0", "#0F766E"),
            ("classes", "الأقسام", "0", "#7C3AED"),
            ("activities", "الأنشطة", "0", "#D97706"),
            ("properties", "الخصائص المسجلة", "0", "#DB2777"),
            ("completion_rate", "اكتمال الحصص", "0%", "#059669"),
            ("average_activities", "متوسط الأنشطة للحصة", "0", "#0891B2"),
            ("average_properties", "متوسط الخصائص للنشاط", "0", "#9333EA"),
            ("forecast_total", "توقع الحصص للأربعة أسابيع", "0", "#EA580C"),
        ]
        for index, (key, title, value, accent) in enumerate(card_definitions):
            card = QFrame()
            card.setObjectName("statisticsCard")
            card.setStyleSheet(
                "QFrame#statisticsCard { background: #FFFFFF; "
                "border: 1px solid #E2E8F0; border-top: 4px solid "
                f"{accent}; border-radius: 12px; }}"
            )
            card_layout = QVBoxLayout(card)
            card_title = QLabel(title)
            card_title.setStyleSheet(
                "color: #64748B; font-size: 11pt; background: transparent;"
            )
            value_label = QLabel(value)
            value_label.setStyleSheet(
                f"color: {accent}; font-size: 23pt; font-weight: 800; "
                "background: transparent;"
            )
            card_layout.addWidget(card_title)
            card_layout.addWidget(value_label)
            self.stats_cards[key] = value_label
            cards_grid.addWidget(card, index // 3, index % 3)
        overview_layout.addLayout(cards_grid)

        activities_layout = create_stats_section(
            "activities",
            "الحصص والأنشطة",
            "توزيع الحصص حسب المجال ونمط التعلم، وأكثر الأنشطة تسجيلًا.",
        )
        activities_charts_grid = QGridLayout()
        activities_charts_grid.setHorizontalSpacing(14)
        activities_charts_grid.setVerticalSpacing(14)
        properties_layout = create_stats_section(
            "properties",
            "الخصائص المسجلة",
            "تفاصيل استخدام الخصائص والقيم المسجلة ضمن الأنشطة.",
        )
        plans_layout = create_stats_section(
            "plans",
            "المخططات ومدى تقدمها",
            "يقيس التقدم نسبة الحصص التي وُزّع عليها نشاط واحد على الأقل؛ "
            "ولا يعني ذلك أن الحصة نُفذت ميدانياً.",
        )
        self.stats_charts = {}
        chart_definitions = [
            ("subjects", "الحصص حسب المجال"),
            ("modes", "أنماط التعلّم"),
            ("properties", "استخدام الخصائص حسب النشاط"),
            ("weekly", "نشاط الحصص والتوقع للأربعة أسابيع القادمة"),
        ]
        for key, title in chart_definitions:
            chart_box = QGroupBox(title)
            chart_box.setObjectName("statisticsChartCard")
            chart_layout = QVBoxLayout(chart_box)
            figure = Figure(figsize=(7.2, 3.4))
            axis = figure.subplots()
            figure.patch.set_facecolor("#FFFFFF")
            canvas = FigureCanvas(figure)
            canvas.setMinimumHeight(280)
            chart_layout.addWidget(canvas)
            self.stats_charts[key] = (figure, axis, canvas)
            if key == "weekly":
                overview_layout.addWidget(chart_box)
            elif key == "properties":
                properties_layout.addWidget(chart_box)
            else:
                index = 0 if key == "subjects" else 1
                activities_charts_grid.addWidget(chart_box, 0, index)
        activities_layout.addLayout(activities_charts_grid)

        self.stats_table = self.make_table(
            ["المجال", "الحصص", "النسبة"]
        )
        self.stats_activity_table = self.make_table(
            ["النشاط", "عدد مرات التسجيل"]
        )
        self.stats_property_table = self.make_table(
            ["النشاط", "اسم الخاصية", "الاستخدام", "أنشطة مختلفة"]
        )
        for table in (
            self.stats_table, self.stats_activity_table,
            self.stats_property_table,
        ):
            table.setMinimumHeight(240)
        activities_tables_layout = QHBoxLayout()
        activities_tables_layout.addWidget(self._statistics_table_group(
            "توزيع المجالات", self.stats_table
        ))
        activities_tables_layout.addWidget(self._statistics_table_group(
            "الأنشطة الأكثر استخداماً", self.stats_activity_table
        ))
        activities_layout.addLayout(activities_tables_layout)
        properties_layout.addWidget(self._statistics_table_group(
            "استعمال أسماء الخصائص حسب الأنشطة",
            self.stats_property_table,
        ))

        def add_text_report(section_key, section_layout):
            report_group = QGroupBox("التقرير النصي والتحليل")
            report_layout = QVBoxLayout(report_group)
            report = QTextEdit()
            report.setReadOnly(True)
            report.setMinimumHeight(220)
            report.setMaximumHeight(320)
            report.setPlaceholderText(
                "سيظهر هنا تقرير مفصل بعد تحميل البيانات."
            )
            report_layout.addWidget(report)
            section_layout.addWidget(report_group)
            self.stats_reports[section_key] = report

        add_text_report("overview", overview_layout)
        add_text_report("activities", activities_layout)
        add_text_report("properties", properties_layout)

        plan_cards_grid = QGridLayout()
        plan_cards_grid.setHorizontalSpacing(12)
        plan_cards_grid.setVerticalSpacing(12)
        self.plan_stats_cards = {}
        plan_card_definitions = [
            ("plans", "عدد المخططات", "#2563EB"),
            ("planned_slots", "إجمالي الحصص المخططة", "#7C3AED"),
            ("distributed_slots", "الحصص الموزع عليها نشاط", "#0F766E"),
            ("pending_slots", "حصص دون نشاط موزع", "#D97706"),
            ("progress_rate", "نسبة التقدم", "#059669"),
            ("complete_plans", "مخططات مكتملة التوزيع", "#DB2777"),
            ("forecast_total", "توقع المخططات للأربعة أسابيع", "#EA580C"),
        ]
        for index, (key, title, accent) in enumerate(
            plan_card_definitions
        ):
            card = QFrame()
            card.setObjectName("statisticsCard")
            card.setStyleSheet(
                "QFrame#statisticsCard { background: #FFFFFF; "
                "border: 1px solid #E2E8F0; border-top: 4px solid "
                f"{accent}; border-radius: 12px; }}"
            )
            card_layout = QVBoxLayout(card)
            card_title = QLabel(title)
            card_title.setStyleSheet(
                "color: #64748B; font-size: 11pt; background: transparent;"
            )
            value_label = QLabel("0")
            value_label.setStyleSheet(
                f"color: {accent}; font-size: 23pt; font-weight: 800; "
                "background: transparent;"
            )
            card_layout.addWidget(card_title)
            card_layout.addWidget(value_label)
            self.plan_stats_cards[key] = value_label
            plan_cards_grid.addWidget(card, index // 3, index % 3)
        plans_layout.addLayout(plan_cards_grid)

        self.stats_plan_mode_table = self.make_table([
            "نمط التعلم", "الحصص المخططة", "الموزعة",
            "المتبقية", "التقدم",
        ])
        self.stats_plan_mode_table.setMinimumHeight(190)
        plans_layout.addWidget(self._statistics_table_group(
            "تقدم المخططات حسب نمط التعلم",
            self.stats_plan_mode_table,
        ))

        plan_chart_box = QGroupBox(
            "نسبة توزيع الحصص حسب المخطط"
        )
        plan_chart_box.setObjectName("statisticsChartCard")
        plan_chart_layout = QVBoxLayout(plan_chart_box)
        plan_figure = Figure(figsize=(7.2, 3.4))
        plan_axis = plan_figure.subplots()
        plan_figure.patch.set_facecolor("#FFFFFF")
        plan_canvas = FigureCanvas(plan_figure)
        plan_canvas.setMinimumHeight(280)
        plan_chart_layout.addWidget(plan_canvas)
        self.stats_charts["plan_progress"] = (
            plan_figure, plan_axis, plan_canvas
        )
        plans_layout.addWidget(plan_chart_box)

        plan_weekly_box = QGroupBox(
            "إنشاء المخططات والتوقع للأربعة أسابيع القادمة"
        )
        plan_weekly_box.setObjectName("statisticsChartCard")
        plan_weekly_layout = QVBoxLayout(plan_weekly_box)
        plan_weekly_figure = Figure(figsize=(7.2, 3.4))
        plan_weekly_axis = plan_weekly_figure.subplots()
        plan_weekly_figure.patch.set_facecolor("#FFFFFF")
        plan_weekly_canvas = FigureCanvas(plan_weekly_figure)
        plan_weekly_canvas.setMinimumHeight(280)
        plan_weekly_layout.addWidget(plan_weekly_canvas)
        self.stats_charts["plan_weekly"] = (
            plan_weekly_figure, plan_weekly_axis, plan_weekly_canvas
        )
        plans_layout.addWidget(plan_weekly_box)

        self.stats_plan_table = self.make_table([
            "المخطط", "القسم", "تاريخ البدء", "الحصص المخططة",
            "الموزع عليها نشاط", "المتبقية", "التقدم",
        ])
        self.stats_plan_table.setMinimumHeight(240)
        plans_layout.addWidget(self._statistics_table_group(
            "تقدم كل مخطط", self.stats_plan_table
        ))
        add_text_report("plans", plans_layout)

        stats_layout.addWidget(self.stats_stack, 1)
        self.stats_cache_label = QLabel()
        self.stats_cache_label.setStyleSheet("color: #64748B;")
        stats_layout.addWidget(self.stats_cache_label)
        self.stats_revision_timer = QTimer(self)
        self.stats_revision_timer.setInterval(3000)
        self.stats_revision_timer.timeout.connect(
            self._check_statistics_revision
        )
        self.stats_revision_timer.start()

        self.official_programs_page = OfficialProgramsWidget(self.db, self)
        self.official_programs_browse_page = OfficialProgramsBrowsePage(self.db, self)

        self.competences_cba_page = CompetencesCbaBrowsePage(self.db, self)
        self.day_lessons_page = DayLessonsBrowsePage(
            self.db, parent=self, on_back=self.return_to_lesson_book
        )

        self.pages_stack = QStackedWidget()

        self.lesson_page = QWidget()
        lesson_page_layout = QVBoxLayout(self.lesson_page)
        lesson_page_layout.addWidget(workspace, 1)

        self.pages_stack.addWidget(self.lesson_page)
        self.pages_stack.addWidget(self.stats_page)
        self.pages_stack.addWidget(self.teacher_info_page)
        self.pages_stack.addWidget(self.official_programs_page)
        self.pages_stack.addWidget(self.official_programs_browse_page)
        self.pages_stack.addWidget(self.competences_cba_page)
        self.pages_stack.addWidget(self.day_lessons_page)

        self.timetable_page = TeacherTimetablePage(self.db, self)
        self.pages_stack.addWidget(self.timetable_page)

        self.plans_page = TeachingPlansPage(self.db, self)
        self.plans_page.set_compact_mode(
            getattr(self, "_small_window_profile", False)
        )
        self.pages_stack.addWidget(self.plans_page)

        self.plan_view_page = TeachingPlanViewPage(self.db, self)
        self.pages_stack.addWidget(self.plan_view_page)

        self.monthly_club_plans_page = QWidget()
        monthly_club_plans_layout = QVBoxLayout(
            self.monthly_club_plans_page
        )
        self.monthly_club_plans_tabs = QTabWidget(
            self.monthly_club_plans_page
        )
        self.monthly_club_management_tab = QWidget(
            self.monthly_club_plans_tabs
        )
        monthly_club_management_layout = QVBoxLayout(
            self.monthly_club_management_tab
        )
        monthly_club_management_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        monthly_club_management_actions = QHBoxLayout()
        self.add_monthly_club_plan_button = QPushButton(
            "إضافة مخطط شهري",
            self.monthly_club_management_tab,
        )
        self.add_monthly_club_plan_button.setObjectName(
            "addMonthlyClubPlanButton"
        )
        self.add_monthly_club_plan_button.setProperty("actionType", "add")
        self.add_monthly_club_plan_button.clicked.connect(
            self.add_monthly_club_plan
        )
        self.import_monthly_club_plans_button = QPushButton(
            "استيراد JSON",
            self.monthly_club_management_tab,
        )
        self.import_monthly_club_plans_button.setObjectName(
            "importMonthlyClubPlansButton"
        )
        self.import_monthly_club_plans_button.setProperty(
            "actionType", "browse"
        )
        monthly_club_management_actions.addWidget(
            self.add_monthly_club_plan_button
        )
        monthly_club_management_actions.addWidget(
            self.import_monthly_club_plans_button
        )
        monthly_club_management_actions.addStretch(1)
        monthly_club_management_layout.addLayout(
            monthly_club_management_actions
        )
        monthly_club_management_layout.addWidget(
            QLabel("إدارة المخططات الشهرية للنوادي")
        )
        self.monthly_club_cards_scroll = QScrollArea(
            self.monthly_club_management_tab
        )
        self.monthly_club_cards_scroll.setWidgetResizable(True)
        self.monthly_club_cards_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.monthly_club_cards_container = QWidget()
        self.monthly_club_cards_layout = QVBoxLayout(
            self.monthly_club_cards_container
        )
        self.monthly_club_cards_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop
        )
        self.monthly_club_cards_layout.setSpacing(10)
        self.monthly_club_cards_scroll.setWidget(
            self.monthly_club_cards_container
        )
        monthly_club_management_layout.addWidget(
            self.monthly_club_cards_scroll, 1
        )
        self.monthly_club_view = MonthlyClubPlanView(
            self.db, self.monthly_club_plans_tabs
        )
        self.monthly_club_view_tab = self.monthly_club_view
        self.monthly_club_plans_tabs.addTab(
            self.monthly_club_management_tab,
            "إدارة المخططات الشهرية",
        )
        self.monthly_club_plans_tabs.addTab(
            self.monthly_club_view_tab,
            "عرض مخطط شهري",
        )
        self.monthly_club_plans_tabs.currentChanged.connect(
            self._monthly_club_plans_tab_changed
        )
        monthly_club_plans_layout.addWidget(
            self.monthly_club_plans_tabs
        )
        self.pages_stack.addWidget(self.monthly_club_plans_page)

        self.official_holidays_page = OfficialHolidaysPage(self.db, self)
        self.pages_stack.addWidget(self.official_holidays_page)

        self.unofficial_holidays_page = OfficialHolidaysPage(
            self.db, self, holiday_type="unofficial"
        )
        self.pages_stack.addWidget(self.unofficial_holidays_page)

        self.assessment_file_management_page = (
            AssessmentFileManagementPage(self.db, self)
        )
        self.pages_stack.addWidget(
            self.assessment_file_management_page
        )

        self.exam_schedule_page = ExamSchedulePage(self.db, self)
        self.pages_stack.addWidget(self.exam_schedule_page)

        self.lesson_book_settings_page = LessonBookSettingsPage(
            self.db,
            self.open_teacher_timetable_page,
            self.open_teaching_assignments,
            self.toggle_enseig_info,
            parent=self,
        )
        self.pages_stack.addWidget(self.lesson_book_settings_page)

        self._page_descriptions = {
            self.lesson_page: (
                "دفتر إعداد الدروس",
                "اختر يوماً لإضافة الحصص ومتابعة الأنشطة المسجلة.",
            ),
            self.stats_page: (
                "الإحصائيات",
                "ملخص استعمال الحصص والأنشطة والخصائص المسجلة.",
            ),
            self.teacher_info_page: (
                "بيانات المعلم",
                "",
            ),
            self.official_programs_page: (
                "إدارة البرامج الرسمية",
                "إدارة البرامج والكفايات المعتمدة في المؤسسة.",
            ),
            self.official_programs_browse_page: (
                "تصفح البرامج الرسمية",
                "ابحث في البرامج الرسمية حسب المستوى والمجال.",
            ),
            self.competences_cba_page: (
                "الكفايات والمفاهيم",
                "تصفح المفاهيم المرتبطة بالمقاربة بالكفايات.",
            ),
            self.day_lessons_page: (
                "الأيام المسجلة",
                "استعرض دفتر إعداد الدروس حسب اليوم الدراسي.",
            ),
            self.timetable_page: (
                "جدول أوقات المعلم",
                "أنشئ جدولًا آليًا من سجل العمل أو رتّب الحصص يدويًا.",
            ),
            self.plans_page: (
                "المخططات",
                "أنشئ المخططات التعليمية وتابع تقدم إنجازها.",
            ),
            self.plan_view_page: (
                "عرض المخطط",
                "تصفح محتوى المخطط بالتنسيق نفسه المستخدم في ملف PDF.",
            ),
            self.monthly_club_plans_page: (
                "المخططات الشهرية للنوادي",
                "إدارة المخططات الشهرية للنوادي وعرضها.",
            ),
            self.official_holidays_page: (
                "العطل الرسمية",
                "أدر فترات العطل المعتمدة في السنة الدراسية.",
            ),
            self.unofficial_holidays_page: (
                "إدارة العطل غير الرسمية",
                "سجّل غياب المعلم الطارئ بسبب لقاء تكويني أو عطلة مرضية أو استثنائية.",
            ),
            self.assessment_file_management_page: (
                "إدارة ملف التقييم والمتابعة",
                "إعداد وإدارة ملف التقييم والمتابعة.",
            ),
            self.exam_schedule_page: (
                "مواعيد الامتحانات",
                "سجّل مواعيد الامتحانات ومددها حسب اليوم والقسم والمعلم.",
            ),
            self.lesson_book_settings_page: (
                "إعداد دفتر إعداد الدروس",
                "اضبط صفحات إعداد الدفتر والخصائص التي تظهر عند طباعة كل نمط تعلم.",
            ),
        }
        page_header = QFrame()
        page_header.setObjectName("pageHeader")
        page_header_layout = QVBoxLayout(page_header)
        page_header_layout.setContentsMargins(16, 10, 16, 10)
        page_header_layout.setSpacing(2)
        self.page_title_label = QLabel()
        self.page_title_label.setObjectName("pageTitle")
        self.page_description_label = QLabel()
        self.page_description_label.setObjectName("pageDescription")
        page_header_layout.addWidget(self.page_title_label)
        page_header_layout.addWidget(self.page_description_label)
        root.addWidget(page_header)
        root.addWidget(self.pages_stack, 1)

        footer = QHBoxLayout()
        self.export_hint = QLabel("تُحفظ التغييرات مباشرة في قاعدة البيانات.")
        self.export_hint.setObjectName("saveHint")
        footer.addWidget(self.export_hint, 1)
        root.addLayout(footer)

        self.statusBar().showMessage("تم الاتصال بقاعدة البيانات بنجاح.")
        toolbar = self.addToolBar("التنقل")
        toolbar.setObjectName("mainNavigationBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        toolbar.setLayoutDirection(Qt.RightToLeft)
        toolbar.setToolTip("التنقل بين صفحات التطبيق")
        toolbar.setAccessibleName("التنقل بين صفحات التطبيق")
        self._page_navigation_actions = []
        self.pages_stack.currentChanged.connect(self.update_page_navigation_actions)
        self.pages_stack.currentChanged.connect(self.update_page_header)
        self.pages_stack.currentChanged.connect(
            lambda index: (
                self.exam_schedule_page.refresh()
                if self.pages_stack.widget(index)
                is self.exam_schedule_page
                else None
            )
        )
        self.pages_stack.currentChanged.connect(
            self._sync_club_drop_group_visibility
        )

        self.navigation_menu_group = QFrame(toolbar)
        self.navigation_menu_group.setObjectName("navigationMenuGroup")
        self.navigation_menu_group.setFixedHeight(60)
        navigation_menu_layout = QHBoxLayout(self.navigation_menu_group)
        navigation_menu_layout.setContentsMargins(0, 0, 0, 0)
        _configure_navigation_menu_layout(navigation_menu_layout)

        self.navigation_search = QLineEdit()
        self.navigation_search.setObjectName("navigationPageSearch")
        self.navigation_search.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )
        self.navigation_search.setPlaceholderText(
            "ابحث في صفحات التطبيق..."
        )
        self.navigation_search.setMinimumWidth(140)
        self.navigation_search.setMaximumWidth(220)
        self.navigation_search.setFixedHeight(32)
        self.navigation_search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.navigation_search.setStyleSheet(
            "QLineEdit#navigationPageSearch {"
            "color: #0F172A; background: #FFFFFF;"
            "border: 1px solid #CBD5E1; border-radius: 8px;"
            "padding: 3px 10px;}"
            "QLineEdit#navigationPageSearch:focus {"
            "border: 2px solid #2563EB; padding: 2px 9px;}"
        )
        self.navigation_search.setAccessibleName(
            "البحث والتنقل بين صفحات التطبيق"
        )
        self.navigation_search.setToolTip(
            "ابحث في الصفحات المتاحة عبر أزرار التطبيق"
        )
        self.navigation_search.setClearButtonEnabled(True)
        self.navigation_search_popup = NavigationSearchPopup(
            self
        )
        self.navigation_search_history = NavigationSearchHistory(self.db.path)
        self._navigation_search_history_suppressed = False
        self._navigation_search_revision = 0
        self._navigation_search_tasks = {}
        self._navigation_search_timer = QTimer(self)
        self._navigation_search_timer.setSingleShot(True)
        self._navigation_search_timer.setInterval(80)
        self._navigation_search_timer.timeout.connect(
            self._start_navigation_search
        )
        self._navigation_search_focus_filter = (
            _ClearSearchFocusOnOutsideClick(
                self.navigation_search,
                self.navigation_search_popup,
                self._show_navigation_search_history,
                self._remember_navigation_search_phrase,
            )
        )
        QApplication.instance().installEventFilter(
            self._navigation_search_focus_filter
        )
        self.navigation_search_popup.historySelected.connect(
            self._select_navigation_search_history
        )

        def add_navigation_menu_separator():
            separator = QFrame(self.navigation_menu_group)
            separator.setObjectName("navigationMenuSeparator")
            separator.setFixedSize(1, 36)
            separator.setStyleSheet("background: #CBD5E1; border: none;")
            navigation_menu_layout.addWidget(
                separator, 0, Qt.AlignmentFlag.AlignVCenter
            )

        lesson_book_menu = QMenu("دفتر إعداد الدروس", self)
        lesson_book_menu.setObjectName("appNavigationMenu")
        open_lesson_action = QAction("التصرف في الدفتر", self)
        open_lesson_action.setProperty("actionType", "browse")
        open_lesson_action.triggered.connect(lambda: self.pages_stack.setCurrentWidget(self.lesson_page))
        self.register_page_navigation_action(open_lesson_action, self.lesson_page)
        lesson_book_menu.addAction(open_lesson_action)
        view_day_action = QAction("عرض الأيام المسجلة بالدفتر", self)
        view_day_action.setProperty("actionType", "browse")
        view_day_action.triggered.connect(self.open_day_lessons_from_menu)
        self.register_page_navigation_action(view_day_action, self.day_lessons_page)
        lesson_book_menu.addAction(view_day_action)
        lesson_book_menu.addSeparator()

        toggle_action = QAction("بيانات المعلم", self)
        toggle_action.triggered.connect(self.toggle_enseig_info)
        self.register_page_navigation_action(
            toggle_action, self.teacher_info_page
        )

        export_pdf_action = QAction("تصدير إلى ملف PDF", self)
        export_pdf_action.triggered.connect(self.export_pdf)

        export_json_action = QAction("تصدير يوم بصيغة JSON", self)
        export_json_action.triggered.connect(self.export_day_to_json)

        import_json_action = QAction("استيراد يوم من JSON", self)
        import_json_action.triggered.connect(self.import_day_from_json)
        self._year_scoped_mutation_actions.append(import_json_action)

        export_year_action = QAction("تصدير سنة دراسية كاملة (JSON)", self)
        export_year_action.triggered.connect(self.export_all_days_for_year)

        import_year_action = QAction("استيراد سنة دراسية كاملة (JSON)", self)
        import_year_action.triggered.connect(self.import_all_years_from_json)
        self._year_scoped_mutation_actions.append(import_year_action)

        self.timetable_action = QAction("جدول أوقات المعلم", self)
        self.timetable_action.triggered.connect(
            self.open_teacher_timetable_page
        )
        self.register_page_navigation_action(
            self.timetable_action, self.timetable_page
        )

        lesson_book_menu.addAction(export_pdf_action)
        lesson_book_menu.addSeparator()
        lesson_book_menu.addAction(export_json_action)
        lesson_book_menu.addAction(import_json_action)
        lesson_book_menu.addSeparator()
        lesson_book_menu.addAction(export_year_action)
        lesson_book_menu.addAction(import_year_action)
        lesson_book_menu.addSeparator()
        clear_all_lessons_action = QAction(
            "مسح كل الحصص والأنشطة والخصائص", self
        )
        clear_all_lessons_action.setToolTip(
            "يتطلب إدخال رمز تحقق قبل مسح جميع البيانات."
        )
        clear_all_lessons_action.setProperty("actionType", "clear")
        clear_all_lessons_action.triggered.connect(
            self.clear_all_lessons_in_db
        )
        self.clear_all_lessons_action = clear_all_lessons_action
        self._year_scoped_mutation_actions.append(clear_all_lessons_action)
        lesson_book_menu.addAction(clear_all_lessons_action)

        center_menu_items(lesson_book_menu)
        lesson_book_button = QToolButton(self)
        lesson_book_button.setText("دفتر إعداد الدروس")
        _configure_navigation_icon(
            lesson_book_button,
            "دفتر إعداد الدروس",
            NAVIGATION_ICON_FILES["lesson_book"],
        )
        lesson_book_button.setMenu(lesson_book_menu)
        lesson_book_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        navigation_menu_layout.addWidget(lesson_book_button)

        school_year_menu = QMenu("السنة الدراسية", self)
        school_year_menu.setObjectName("appNavigationMenu")
        school_year_menu.addAction(toggle_action)
        school_year_menu.addAction(self.timetable_action)
        teaching_assignments_action = QAction(
            "تعيين الأقسام وأنشطة التدريس", self
        )
        teaching_assignments_action.triggered.connect(
            self.open_teaching_assignments
        )
        self._year_scoped_mutation_actions.append(
            teaching_assignments_action
        )
        school_year_menu.addAction(teaching_assignments_action)
        official_holidays_action = QAction("إدارة العطل الرسمية", self)
        official_holidays_action.setProperty("actionType", "browse")
        official_holidays_action.triggered.connect(
            lambda: self.pages_stack.setCurrentWidget(
                self.official_holidays_page
            )
        )
        self.register_page_navigation_action(
            official_holidays_action, self.official_holidays_page
        )
        school_year_menu.addAction(official_holidays_action)
        unofficial_holidays_action = QAction(
            "إدارة العطل غير الرسمية", self
        )
        unofficial_holidays_action.setProperty("actionType", "browse")
        unofficial_holidays_action.triggered.connect(
            lambda: self.pages_stack.setCurrentWidget(
                self.unofficial_holidays_page
            )
        )
        self.register_page_navigation_action(
            unofficial_holidays_action, self.unofficial_holidays_page
        )
        school_year_menu.addAction(unofficial_holidays_action)
        exam_schedule_action = QAction("مواعيد الامتحانات", self)
        exam_schedule_action.setProperty("actionType", "browse")
        exam_schedule_action.triggered.connect(
            lambda: self.pages_stack.setCurrentWidget(
                self.exam_schedule_page
            )
        )
        self.register_page_navigation_action(
            exam_schedule_action, self.exam_schedule_page
        )
        school_year_menu.addAction(exam_schedule_action)
        self.add_school_year_action = QAction("إضافة سنة دراسية جديدة", self)
        self.add_school_year_action.triggered.connect(self.add_school_year)
        self._year_scoped_mutation_actions.append(self.add_school_year_action)
        school_year_menu.addAction(self.add_school_year_action)
        school_year_menu.aboutToShow.connect(
            self.update_add_school_year_action_state
        )
        center_menu_items(school_year_menu)
        school_year_button = QToolButton(self)
        school_year_button.setText("السنة الدراسية")
        _configure_navigation_icon(
            school_year_button,
            "السنة الدراسية",
            NAVIGATION_ICON_FILES["school_year"],
        )
        school_year_button.setMenu(school_year_menu)
        school_year_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        navigation_menu_layout.addWidget(school_year_button)
        self.update_add_school_year_action_state()

        prog_menu = QMenu("البرامج الرسمية", self)
        prog_menu.setObjectName("appNavigationMenu")
        browse_prog_action = QAction("تصفح البرامج الرسمية", self)
        browse_prog_action.setProperty("actionType", "browse")
        browse_prog_action.triggered.connect(self.open_official_programs_browser)
        self.register_page_navigation_action(
            browse_prog_action, self.official_programs_browse_page
        )
        prog_menu.addAction(browse_prog_action)
        open_prog_action = QAction("فتح إدارة البرامج الرسمية", self)
        open_prog_action.triggered.connect(lambda: self.pages_stack.setCurrentWidget(self.official_programs_page))
        self.register_page_navigation_action(open_prog_action, self.official_programs_page)
        prog_menu.addAction(open_prog_action)
        prog_menu.addSeparator()

        browse_cba_action = QAction("تصفح مفاهيم متصلة بالمقاربة بالكفايات", self)
        browse_cba_action.setProperty("actionType", "browse")
        browse_cba_action.triggered.connect(self.open_competences_cba_browser)
        self.register_page_navigation_action(browse_cba_action, self.competences_cba_page)
        prog_menu.addAction(browse_cba_action)

        prog_menu.addSeparator()

        self.export_prog_action = QAction("تصدير البرامج الرسمية كاملة (JSON)", self)
        self.export_prog_action.triggered.connect(self.export_programs_json)
        prog_menu.addAction(self.export_prog_action)

        self.import_prog_action = QAction("استيراد البرامج الرسمية من JSON", self)
        self.import_prog_action.triggered.connect(self.import_programs_json)
        prog_menu.addAction(self.import_prog_action)

        prog_menu.aboutToShow.connect(self.update_prog_actions_state)

        center_menu_items(prog_menu)
        prog_button = QToolButton(self)
        prog_button.setText("البرامج الرسمية")
        _configure_navigation_icon(
            prog_button,
            "البرامج الرسمية",
            NAVIGATION_ICON_FILES["official_programs"],
        )
        prog_button.setMenu(prog_menu)
        prog_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        navigation_menu_layout.addWidget(prog_button)

        add_navigation_menu_separator()
        stats_menu = QMenu("الإحصائيات", self)
        stats_menu.setObjectName("appNavigationMenu")
        stats_menu_actions = (
            ("دفتر إعداد الدروس", "overview", "fa5s.book"),
            ("الحصص والأنشطة", "activities", "fa5s.book-open"),
            ("الخصائص المسجلة", "properties", "fa5s.list-alt"),
            ("المخططات والتقدم", "plans", "fa5s.project-diagram"),
        )
        for title, section, icon_name in stats_menu_actions:
            action = QAction(title, self)
            action.setProperty("actionType", "browse")
            action.setIcon(qta.icon(icon_name, color="#475569"))
            action.triggered.connect(
                lambda _checked=False, selected_section=section:
                self.open_statistics_page(selected_section)
            )
            stats_menu.addAction(action)
        center_menu_items(stats_menu)
        stats_button = QToolButton(self)
        stats_button.setObjectName("statisticsNavigationButton")
        stats_button.setText("الإحصائيات")
        stats_button.setMenu(stats_menu)
        stats_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        _configure_navigation_icon(
            stats_button,
            "الإحصائيات",
            NAVIGATION_ICON_FILES["statistics"],
        )
        navigation_menu_layout.addWidget(stats_button)

        plans_action = QAction("فتح المخططات", self)
        plans_action.setText("إدارة المخططات")
        plans_action.setStatusTip("عرض المخططات التعليمية")
        plans_action.triggered.connect(lambda: self.pages_stack.setCurrentWidget(self.plans_page))
        self.register_page_navigation_action(plans_action, self.plans_page)
        plans_button = QToolButton(self)
        plans_button.setObjectName("plansNavigationButton")
        plans_button.setText("المخططات")
        _configure_navigation_icon(
            plans_button,
            "المخططات",
            NAVIGATION_ICON_FILES["plans"],
        )
        plans_menu = QMenu("المخططات", self)
        plans_menu.setObjectName("appNavigationMenu")
        plans_menu.addAction(plans_action)
        view_plan_action = QAction("عرض المخطط", self)
        view_plan_action.setProperty("actionType", "browse")
        view_plan_action.setStatusTip("عرض المخطط بتنسيق PDF داخل التطبيق")
        view_plan_action.triggered.connect(
            lambda: self.pages_stack.setCurrentWidget(self.plan_view_page)
        )
        self.register_page_navigation_action(
            view_plan_action, self.plan_view_page
        )
        plans_menu.addAction(view_plan_action)

        monthly_club_plans_action = QAction(
            "المخططات الشهرية للنوادي", self
        )
        monthly_club_plans_action.setProperty("actionType", "browse")
        monthly_club_plans_action.triggered.connect(
            lambda: self.open_monthly_club_plans_tab(0)
        )
        self.register_page_navigation_action(
            monthly_club_plans_action, self.monthly_club_plans_page
        )
        plans_menu.addAction(monthly_club_plans_action)
        center_menu_items(plans_menu)
        plans_button.setMenu(plans_menu)
        plans_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        navigation_menu_layout.addWidget(plans_button)

        assessment_management_action = QAction(
            "إدارة ملف التقييم والمتابعة", self
        )
        assessment_management_action.setProperty("actionType", "browse")
        assessment_management_action.setStatusTip(
            "فتح صفحة إدارة ملف التقييم والمتابعة"
        )
        assessment_management_action.triggered.connect(
            lambda: self.pages_stack.setCurrentWidget(
                self.assessment_file_management_page
            )
        )
        self.register_page_navigation_action(
            assessment_management_action,
            self.assessment_file_management_page,
        )
        assessment_button = QToolButton(self)
        assessment_button.setObjectName("assessmentNavigationButton")
        assessment_button.setText("التقييم والمتابعة")
        _configure_navigation_icon(
            assessment_button,
            "التقييم والمتابعة",
            NAVIGATION_ICON_FILES["assessment"],
        )
        assessment_menu = QMenu("التقييم والمتابعة", self)
        assessment_menu.setObjectName("appNavigationMenu")
        assessment_menu.addAction(assessment_management_action)
        exam_schedule_action = QAction("مواعيد الامتحانات", self)
        exam_schedule_action.setProperty("actionType", "browse")
        exam_schedule_action.setStatusTip(
            "إدارة مواعيد الامتحانات ومددها بالدقائق"
        )
        exam_schedule_action.triggered.connect(
            lambda: self.pages_stack.setCurrentWidget(
                self.exam_schedule_page
            )
        )
        self.register_page_navigation_action(
            exam_schedule_action, self.exam_schedule_page
        )
        assessment_menu.addAction(exam_schedule_action)
        center_menu_items(assessment_menu)
        assessment_button.setMenu(assessment_menu)
        assessment_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        navigation_menu_layout.addWidget(assessment_button)

        settings_menu = QMenu("الإعدادات", self)
        settings_menu.setObjectName("appNavigationMenu")
        lesson_book_settings_action = QAction(
            "إعداد دفتر إعداد الدروس", self
        )
        lesson_book_settings_action.setProperty("actionType", "browse")
        lesson_book_settings_action.triggered.connect(
            lambda: self.pages_stack.setCurrentWidget(
                self.lesson_book_settings_page
            )
        )
        self.register_page_navigation_action(
            lesson_book_settings_action, self.lesson_book_settings_page
        )
        settings_menu.addAction(lesson_book_settings_action)
        center_menu_items(settings_menu)
        settings_button = QToolButton(self)
        settings_button.setText("الإعدادات")
        _configure_navigation_icon(
            settings_button,
            "الإعدادات",
            NAVIGATION_ICON_FILES["settings"],
        )
        settings_button.setMenu(settings_menu)
        settings_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        navigation_menu_layout.addWidget(settings_button)

        add_navigation_menu_separator()
        about_menu = QMenu("حول التطبيق", self)
        about_menu.setObjectName("appNavigationMenu")
        about_action = QAction("معلومات التطبيق", self)
        about_action.setProperty("actionType", "browse")
        about_action.triggered.connect(self.show_about_dialog)
        about_menu.addAction(about_action)
        center_menu_items(about_menu)
        about_button = QToolButton(self)
        about_button.setText("حول التطبيق")
        _configure_navigation_icon(
            about_button,
            "حول التطبيق",
            NAVIGATION_ICON_FILES["about"],
        )
        about_button.setMenu(about_menu)
        about_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        navigation_menu_layout.addWidget(about_button)

        self.teacher_year_identity_card = ClickableFrame(toolbar)
        self.teacher_year_identity_card.setObjectName(
            "teacherYearIdentityCard"
        )
        self.teacher_year_identity_card.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )
        self.teacher_year_identity_card.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.teacher_year_identity_card.setMinimumWidth(0)
        self.teacher_year_identity_card.setFixedHeight(48)
        self.teacher_year_identity_card.setStyleSheet(
            "QFrame#teacherYearIdentityCard {"
            "background: #FFFFFF; border: 1px solid #E2E8F0;"
            "border-radius: 12px;}"
        )
        self.teacher_year_identity_card.clicked.connect(
            self.open_teacher_identity
        )
        identity_layout = QHBoxLayout(self.teacher_year_identity_card)
        identity_layout.setContentsMargins(10, 4, 10, 4)
        identity_layout.setSpacing(10)

        self.teacher_year_photo_placeholder = QFrame(
            self.teacher_year_identity_card
        )
        self.teacher_year_photo_placeholder.setObjectName(
            "teacherYearPhotoPlaceholder"
        )
        self.teacher_year_photo_placeholder.setFixedSize(38, 38)
        self.teacher_year_photo_placeholder.setStyleSheet(
            "QFrame#teacherYearPhotoPlaceholder {"
            "background: #F8FAFC; border: 1px solid #CBD5E1;"
            "border-radius: 19px;}"
        )
        self.teacher_year_photo_placeholder.setAccessibleName(
            "موضع صورة المعلم"
        )
        self.teacher_year_avatar_label = QLabel(
            self.teacher_year_photo_placeholder
        )
        self.teacher_year_avatar_label.setObjectName(
            "teacherYearAvatarIcon"
        )
        self.teacher_year_avatar_label.setFixedSize(36, 36)
        self.teacher_year_avatar_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.teacher_year_avatar_label.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        avatar_layout = QVBoxLayout(self.teacher_year_photo_placeholder)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        avatar_layout.addWidget(self.teacher_year_avatar_label)
        identity_layout.addWidget(self.teacher_year_photo_placeholder)

        identity_text = QHBoxLayout()
        identity_text.setContentsMargins(0, 0, 0, 0)
        identity_text.setSpacing(8)
        self.teacher_name_label = QLabel("اسم المعلم غير محدد")
        self.teacher_name_label.setObjectName("teacherYearTeacherName")
        self.teacher_name_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.teacher_name_label.setStyleSheet(
            "font-weight: 700; color: #1E293B; background: transparent;"
        )
        self.current_school_year_label = QLabel(
            "السنة الدراسية الحالية: —"
        )
        self.current_school_year_label.setObjectName(
            "teacherYearCurrentSchoolYear"
        )
        self.current_school_year_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.current_school_year_label.setStyleSheet(
            "font-size: 9pt; color: #64748B; background: transparent;"
        )
        identity_text.addWidget(self.teacher_name_label)
        identity_text.addWidget(self.current_school_year_label)
        self.teacher_identity_text_layout = identity_text
        identity_layout.addLayout(identity_text, 1)

        self.notification_button = QToolButton(toolbar)
        self.notification_button.setObjectName("notificationButton")
        self.notification_button.setAccessibleName("الإشعارات")
        self.notification_button.setToolTip("الإشعارات")
        self.notification_button.setIcon(
            qta.icon("fa5s.bell", color="#334155")
        )
        self.notification_button.setIconSize(QSize(18, 18))
        self.notification_button.setFixedSize(40, 48)
        self.notification_button.setStyleSheet(
            "QToolButton#notificationButton {"
            "min-width: 40px; max-width: 40px;"
            "min-height: 48px; max-height: 48px;"
            "padding: 0; border: 1px solid #CBD5E1;"
            "border-radius: 12px; background: #FFFFFF;}"
            "QToolButton#notificationButton:hover {"
            "background: #EFF6FF; border-color: #93C5FD;}"
            "QToolButton#notificationButton:pressed {"
            "background: #DBEAFE;}"
        )
        self.notification_badge = QLabel(
            "0", self.notification_button
        )
        self.notification_badge.setObjectName("notificationBadge")
        self.notification_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_badge.setStyleSheet(
            "QLabel#notificationBadge {"
            "color: #FFFFFF; background: #DC2626;"
            "border: 1px solid #FFFFFF; border-radius: 9px;"
            "font-size: 8pt; font-weight: 700; padding: 0 3px;}"
        )
        self.notification_badge.hide()
        self.notification_button.clicked.connect(self.show_notifications)
        self._notification_items = []
        self._notification_revision = None
        self._notification_year_id = None
        self._notification_refresh_timer = QTimer(self)
        self._notification_refresh_timer.setSingleShot(True)
        self._notification_refresh_timer.setInterval(250)
        self._notification_refresh_timer.timeout.connect(
            self.refresh_notification_badge
        )
        self._calendar_event_notification_timer = QTimer(self)
        self._calendar_event_notification_timer.setInterval(
            6 * 60 * 60 * 1000
        )
        self._calendar_event_notification_timer.timeout.connect(
            lambda: self.refresh_notification_badge(force=True)
        )
        self._calendar_event_notification_timer.start()

        self.teacher_notification_group = QFrame(toolbar)
        self.teacher_notification_group.setObjectName(
            "teacherNotificationGroup"
        )
        self.teacher_notification_group.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )
        self.teacher_notification_group.setFixedHeight(48)
        notification_group_layout = QHBoxLayout(
            self.teacher_notification_group
        )
        notification_group_layout.setContentsMargins(0, 0, 0, 0)
        notification_group_layout.setSpacing(6)
        notification_group_layout.addWidget(
            self.teacher_year_identity_card, 0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        notification_group_layout.addWidget(
            self.notification_button, 0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        self.teacher_notification_group.setFixedWidth(
            self.teacher_year_identity_card.width()
            + self.notification_button.width()
            + notification_group_layout.spacing()
        )

        left_toolbar_section = QWidget()
        left_toolbar_section.setObjectName("navigationLeftSection")
        left_toolbar_section.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        left_toolbar_layout = QHBoxLayout(left_toolbar_section)
        left_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        left_toolbar_layout.setSpacing(8)
        left_toolbar_layout.addWidget(self.teacher_notification_group)
        left_toolbar_layout.addWidget(self.navigation_search)
        toolbar_content = _build_navigation_toolbar_content(
            toolbar, left_toolbar_section, self.navigation_menu_group
        )
        self.navigation_toolbar_layout = toolbar_content.layout()
        self.navigation_toolbar_left_section = left_toolbar_section
        self.navigation_toolbar_menu_section = self.navigation_menu_group
        self.navigation_toolbar_right_section = toolbar_content.findChild(
            QWidget, "navigationRightSection"
        )
        toolbar.addWidget(toolbar_content)

        linked_menu_actions = set()

        def collect_menu_actions(menu):
            for menu_action in menu.actions():
                linked_menu_actions.add(menu_action)
                submenu = menu_action.menu()
                if submenu is not None:
                    collect_menu_actions(submenu)

        for button in self.navigation_menu_group.findChildren(QToolButton):
            menu = button.menu()
            if menu is not None:
                collect_menu_actions(menu)
        self.navigation_search_actions = _build_navigation_search_actions(
            self._page_navigation_actions,
            self._page_descriptions,
            linked_menu_actions,
        )
        page_actions = {
            page: action
            for action, page in self._page_navigation_actions
        }
        self.navigation_search_targets = {}
        extra_search_entries = []
        for page, (page_title, description) in self._page_descriptions.items():
            action = page_actions.get(page)
            target = {"action": action, "page": page}
            self.navigation_search_targets[page_title] = target
            page_terms = [page_title, description, "صفحة تطبيق تنقل"]
            for widget_type in (QLabel, QPushButton, QToolButton, QGroupBox):
                page_terms.extend(
                    _navigation_widget_text(widget).replace("&", "")
                    for widget in page.findChildren(widget_type)
                    if _navigation_widget_text(widget).strip()
                )
            extra_search_entries.append(
                {
                    "title": page_title,
                    "description": description,
                    "keywords": " ".join(page_terms),
                    "key": page_title,
                }
            )

        for label, action in self.navigation_search_actions.items():
            target_page = next(
                (
                    page for page, page_action in page_actions.items()
                    if page_action is action
                ),
                None,
            )
            if target_page is not None:
                self.navigation_search_targets[label] = {
                    "action": action,
                    "page": target_page,
                }

        for tab_widget in self.pages_stack.findChildren(QTabWidget):
            owner_page = tab_widget.parentWidget()
            while (
                owner_page is not None
                and self.pages_stack.indexOf(owner_page) < 0
            ):
                owner_page = owner_page.parentWidget()
            if owner_page is None:
                continue
            page_action = page_actions.get(owner_page)
            page_title = self._page_descriptions.get(
                owner_page, ("صفحة التطبيق", "")
            )[0]
            for tab_index in range(tab_widget.count()):
                tab_title = tab_widget.tabText(tab_index).replace("&", "")
                if not tab_title:
                    continue
                tab_key = (
                    f"tab:{id(tab_widget)}:{tab_index}"
                )
                extra_search_entries.append(
                    {
                        "title": tab_title,
                        "description": f"تبويب ضمن {page_title}",
                        "keywords": page_title,
                        "key": tab_key,
                    }
                )
                self.navigation_search_targets[tab_key] = {
                    "action": page_action,
                    "page": owner_page,
                    "tab_widget": tab_widget,
                    "tab_index": tab_index,
                }

        database_page_titles = {
            "ann_scolaire": "بيانات المعلم",
            "day_data": "الأيام المسجلة",
            "hessa": "الأيام المسجلة",
            "nachat": "الأيام المسجلة",
            "nachat_detail": "الأيام المسجلة",
            "level": "دفتر إعداد الدروس",
            "classe": "دفتر إعداد الدروس",
            "class_group": "دفتر إعداد الدروس",
            "class_group_member": "دفتر إعداد الدروس",
            "hessa_class_member": "الأيام المسجلة",
            "lesson_repeat_request": "الأيام المسجلة",
            "lesson_repeat_activity": "الأيام المسجلة",
            "majal": "تصفح البرامج الرسمية",
            "learning_mode": "دفتر إعداد الدروس",
            "value": "دفتر إعداد الدروس",
            "competence_majal": "تصفح البرامج الرسمية",
            "competence_matiere": "تصفح البرامج الرسمية",
            "moukawan_kifaya": "تصفح البرامج الرسمية",
            "objectif_specifique": "تصفح البرامج الرسمية",
            "content": "تصفح البرامج الرسمية",
            "concept": "الكفايات والمفاهيم",
            "official_holiday": "العطل الرسمية",
            "teacher_timetable": "جدول أوقات المعلم",
            "teacher_teaching_assignments": "جدول أوقات المعلم",
            "assessment_file": "إدارة ملف التقييم والمتابعة",
            "assessment_file_class": "إدارة ملف التقييم والمتابعة",
            "assessment_file_activity": "إدارة ملف التقييم والمتابعة",
            "cultural_club": "المخططات الشهرية للنوادي",
            "cultural_club_section": "المخططات الشهرية للنوادي",
            "cultural_club_monthly_plan": "المخططات الشهرية للنوادي",
            "cultural_club_monthly_session": "المخططات الشهرية للنوادي",
            "cultural_club_monthly_property": "المخططات الشهرية للنوادي",
            "cultural_club_daily_session": "دفتر إعداد الدروس",
            "cultural_club_daily_property": "دفتر إعداد الدروس",
            "cultural_club_daily_repeat_request": "دفتر إعداد الدروس",
            "teaching_plan": "المخططات",
            "teaching_plan_property": "المخططات",
            "teaching_plan_weekday": "المخططات",
            "teaching_plan_item": "المخططات",
            "teaching_plan_item_detail": "المخططات",
            "teaching_plan_activity": "المخططات",
            "teaching_plan_activity_property": "المخططات",
            "teaching_plan_personal_content": "المخططات",
            "teaching_plan_mode_setting": "المخططات",
            "teaching_plan_mode_selection": "المخططات",
            "teaching_plan_mode_activity_selection": "المخططات",
            "teaching_plan_integration_activity": "المخططات",
            "teaching_plan_integration_content": "المخططات",
            "teaching_plan_evaluation_activity": "المخططات",
            "teaching_plan_evaluation_content": "المخططات",
            "teaching_plan_support_activity": "المخططات",
        }
        for table_name, page_title in database_page_titles.items():
            if page_title in self.navigation_search_targets:
                self.navigation_search_targets[table_name] = (
                    self.navigation_search_targets[page_title]
                )

        self.navigation_search_index = SmartNavigationSearchIndex(
            self.navigation_search_actions,
            self._page_descriptions,
            extra_entries=extra_search_entries,
            database_path=self.db.path,
            database_targets=database_page_titles,
            year_id=self.db.year_id,
        )
        self.navigation_search.textChanged.connect(
            self._queue_navigation_search
        )
        self.navigation_search_popup.resultActivated.connect(
            self.open_navigation_search_result
        )

        self.update_page_header(self.pages_stack.currentIndex())

    @staticmethod
    def _statistics_table_group(title, table):
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.addWidget(table)
        return group

    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("حول التطبيق")
        dialog.setObjectName("aboutApplicationDialog")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.setMinimumWidth(460)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(14)

        header = QFrame()
        header.setStyleSheet(
            "QFrame { background-color: #EFF6FF; border: 1px solid #BFDBFE; "
            "border-radius: 14px; }"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 18, 18, 18)
        title = QLabel("المعين للتخطيط اليومي للحصص")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 19pt; font-weight: 800; color: #1E3A8A; "
            "background: transparent; border: none;"
        )
        description = QLabel("البرنامج المساعد التربوي للمعلم")
        description.setAlignment(Qt.AlignCenter)
        description.setStyleSheet(
            "font-size: 11pt; color: #475569; background: transparent; "
            "border: none;"
        )
        version = QLabel("الإصدار v 1.2")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet(
            "font-size: 10pt; font-weight: 700; color: #2563EB; "
            "background: transparent; border: none;"
        )
        header_layout.addWidget(title)
        header_layout.addWidget(description)
        header_layout.addWidget(version)
        layout.addWidget(header)

        developer = QLabel(
            "<b>المطور</b><br>بلال المزوغي"
        )
        phone = QLabel(
            '<b>الهاتف</b><br><a href="tel:20971271">20971271</a>'
        )
        email = QLabel(
            '<b>البريد الإلكتروني</b><br>'
            '<a href="mailto:mzbi9620@gmail.com">mzbi9620@gmail.com</a>'
        )
        for label in (developer, phone, email):
            label.setTextFormat(Qt.RichText)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            label.setOpenExternalLinks(True)
            label.setStyleSheet(
                "padding: 8px 12px; color: #334155; background: #FFFFFF; "
                "border: 1px solid #E2E8F0; border-radius: 8px;"
            )
            layout.addWidget(label)

        close_button = QPushButton("إغلاق")
        close_button.setProperty("actionType", "close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        if self.styleSheet():
            dialog.setStyleSheet(self.styleSheet())
        dialog.exec()

    def open_timetable_dialog(self):
        if getattr(self, "_timetable_thread", None) is not None:
            return
        self.timetable_action.setEnabled(False)
        self.statusBar().showMessage("في انتظار توليد البيانات ...")
        self._timetable_loading_year_id = self.db.year_id
        self._timetable_thread = QThread(self)
        self._timetable_worker = TimetableLoadWorker(
            self.db.path, self._timetable_loading_year_id
        )
        self._timetable_worker.moveToThread(self._timetable_thread)
        self._timetable_thread.started.connect(
            self._timetable_worker.run, Qt.QueuedConnection
        )
        self._timetable_worker.result_ready.connect(
            self._open_timetable_with_schedule
        )
        self._timetable_worker.failed.connect(self._timetable_load_failed)
        self._timetable_worker.finished.connect(self._timetable_thread.quit)
        self._timetable_worker.finished.connect(
            self._timetable_worker.deleteLater
        )
        self._timetable_thread.finished.connect(
            self._timetable_thread_finished
        )
        self._timetable_thread.start()

    @Slot(object)
    def _open_timetable_with_schedule(self, result):
        self.statusBar().clearMessage()
        if self._timetable_loading_year_id != self.db.year_id:
            return
        if getattr(self, "_timetable_refresh_pending", False):
            return
        schedule, first_hour, last_hour = result
        self.timetable_page.set_automatic_schedule(
            schedule, first_hour, last_hour
        )

    def open_teacher_timetable_page(self):
        self.timetable_page.set_school_year(self.db.year_id)
        self.timetable_page.set_read_only(self.is_school_year_read_only)
        self.pages_stack.setCurrentWidget(self.timetable_page)
        if getattr(self, "_timetable_thread", None) is None:
            self.open_timetable_dialog()

    def open_teaching_assignments(self):
        if not self.ensure_school_year_writable():
            return
        try:
            dialog = TeachingAssignmentsDialog(
                self.db, self.db.year_id, self
            )
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.critical(
                self,
                "تعذر تحميل تعيينات التدريس",
                str(error),
            )
            return
        dialog.assignmentsChanged.connect(
            self.timetable_page.refresh_lesson_palette_from_database
        )
        dialog.exec()

    @Slot(str)
    def _timetable_load_failed(self, message):
        if getattr(self, "_timetable_refresh_pending", False):
            return
        if self._timetable_loading_year_id != self.db.year_id:
            return
        self.timetable_page.set_automatic_generation_failed(message)
        self.statusBar().showMessage(message)
        QMessageBox.critical(self, "تعذر توليد جدول الأوقات", message)

    @Slot()
    def _timetable_thread_finished(self):
        thread = self._timetable_thread
        loaded_year_id = self._timetable_loading_year_id
        self._timetable_loading_year_id = None
        self._timetable_worker = None
        self._timetable_thread = None
        if thread is not None:
            thread.deleteLater()
        self.timetable_action.setEnabled(True)
        if getattr(self, "_timetable_refresh_pending", False):
            self._timetable_refresh_pending = False
            self.open_timetable_dialog()
            return
        if (
            loaded_year_id != self.db.year_id
            and self.pages_stack.currentWidget() is self.timetable_page
        ):
            self.open_timetable_dialog()

    def open_official_programs_browser(self):
        self.pages_stack.setCurrentWidget(self.official_programs_browse_page)
        self.official_programs_browse_page.load_levels()

    def open_competences_cba_browser(self):
        self.pages_stack.setCurrentWidget(self.competences_cba_page)

    def register_page_navigation_action(self, action, page):
        self._page_navigation_actions.append((action, page))
        action.setEnabled(self.pages_stack.currentWidget() is not page)

    def open_navigation_search_result(self, page_name):
        key = str(page_name).strip()
        database_result = decode_database_result_key(key)
        query = (
            str(database_result.get("query") or "").strip()
            if database_result is not None
            else str(getattr(self.navigation_search, "text", lambda: "")()).strip()
        )
        if database_result is not None:
            key = database_result["target"]
        target = getattr(self, "navigation_search_targets", {}).get(key)
        action = (
            target.get("action")
            if target is not None
            else self.navigation_search_actions.get(key)
        )
        if hasattr(self, "navigation_search_popup"):
            self.navigation_search_popup.hide()
        history = getattr(self, "navigation_search_history", None)
        if history is not None and query:
            history.record(query)
        self._navigation_search_history_suppressed = True
        try:
            self.navigation_search.clear()
        finally:
            self._navigation_search_history_suppressed = False
        if action is not None and action.isEnabled():
            action.trigger()
        elif target is not None and target.get("page") is not None:
            self.pages_stack.setCurrentWidget(target["page"])
        if target is not None and target.get("tab_widget") is not None:
            target["tab_widget"].setCurrentIndex(target["tab_index"])
        if database_result is not None:
            day_text = database_result.get("day")
            page = target.get("page") if target is not None else None
            if day_text:
                day_id = self.db.recorded_day_id(day_text)
                self.day_lessons_page.set_day(day_id, day_text)
                page = self.day_lessons_page
                self.pages_stack.setCurrentWidget(page)
            context = database_result.get("context") or {}
            if context.get("type") == "teaching_plan_activity":
                open_distribution = getattr(
                    page, "open_distribution_for_plan", None
                )
                if callable(open_distribution):
                    distribution_page = open_distribution(
                        context.get("plan_id"),
                        learning_mode=context.get("learning_mode"),
                        lesson_number=context.get("lesson_number"),
                        activity_id=context.get("activity_id"),
                        show_errors=False,
                    )
                    if distribution_page is not None:
                        page = distribution_page
        else:
            page = target.get("page") if target is not None else None
        if page is None:
            pages_stack = getattr(self, "pages_stack", None)
            if pages_stack is not None:
                page = pages_stack.currentWidget()
        if page is not None and query:
            self._show_navigation_search_matches(
                page,
                query,
                database_result.get("result", "")
                if database_result is not None
                else "",
            )

    def _show_navigation_search_matches(self, page, query, result_title=""):
        previous_controller = getattr(
            self, "_navigation_search_match_controller", None
        )
        if previous_controller is not None:
            previous_controller.clear()
        controller = _NavigationSearchMatchController(
            page, query, result_title
        )
        self._navigation_search_match_controller = (
            controller if controller.matches else None
        )

    def _queue_navigation_search(self, query):
        self._navigation_search_revision += 1
        if not query.strip():
            self._navigation_search_timer.stop()
            self.navigation_search_popup.hide()
            if not getattr(
                self, "_navigation_search_history_suppressed", False
            ):
                QTimer.singleShot(0, self._show_navigation_search_history)
            return
        if self.navigation_search_popup._showing_history:
            self.navigation_search_popup.hide()
        self._navigation_search_timer.start()

    def _show_navigation_search_history(self):
        if (
            getattr(self, "_navigation_search_history_suppressed", False)
            or not self.navigation_search.hasFocus()
            or self.navigation_search.text().strip()
        ):
            return
        history = self.navigation_search_history.recent()
        if not history:
            self.navigation_search_popup.hide()
            return
        self.navigation_search_popup.set_history(history)
        self.navigation_search_popup.show_below(self.navigation_search)

    def _remember_navigation_search_phrase(self):
        phrase = self.navigation_search.text().strip()
        if phrase:
            self.navigation_search_history.record(phrase)

    def _select_navigation_search_history(self, phrase):
        phrase = str(phrase or "").strip()
        if not phrase:
            return
        self.navigation_search_history.record(phrase)
        self.navigation_search.setText(phrase)
        self.navigation_search.setFocus()
        self.navigation_search.selectAll()

    def _start_navigation_search(self):
        query = self.navigation_search.text()
        if not query.strip():
            return
        revision = self._navigation_search_revision
        task = NavigationSearchTask(
            self.navigation_search_index,
            revision,
            query,
        )
        task.signals.completed.connect(
            self._show_navigation_search_results
        )
        task.signals.failed.connect(self._navigation_search_failed)
        self._navigation_search_tasks[revision] = task
        QThreadPool.globalInstance().start(task)

    def _show_navigation_search_results(self, revision, query, results):
        self._navigation_search_tasks.pop(revision, None)
        if (
            revision != self._navigation_search_revision
            or query != self.navigation_search.text()
            or not self.navigation_search.hasFocus()
        ):
            return
        visible_results = [
            (title, description, key)
            for title, description, key in results
            if (
                (
                    database_result := decode_database_result_key(key)
                ) is not None
                and database_result["target"] in self.navigation_search_targets
            )
            or key in self.navigation_search_targets
        ]
        self.navigation_search_popup.set_results(visible_results)
        self.navigation_search_popup.show_below(self.navigation_search)

    def _navigation_search_failed(self, revision, query, error_message):
        self._navigation_search_tasks.pop(revision, None)
        if (
            revision != self._navigation_search_revision
            or query != self.navigation_search.text()
        ):
            return
        self.navigation_search_popup.hide()
        self.statusBar().showMessage(
            f"تعذر إكمال البحث: {error_message}", 5000
        )

    def open_statistics_page(self, section="overview"):
        section_index = self.stats_section_indices.get(section)
        if section_index is None:
            raise ValueError(f"قسم الإحصائيات غير معروف: {section}")
        self.stats_stack.setCurrentIndex(section_index)
        self.pages_stack.setCurrentWidget(self.stats_page)
        self.load_statistics()

    def open_monthly_club_plans_tab(self, tab_index):
        previous_index = self.monthly_club_plans_tabs.currentIndex()
        self.monthly_club_plans_tabs.setCurrentIndex(tab_index)
        if (
            previous_index == tab_index
        ):
            if tab_index == 0 and hasattr(
                self, "_load_monthly_club_plans"
            ):
                self._load_monthly_club_plans()
            elif tab_index == 1 and hasattr(
                self, "monthly_club_view"
            ):
                self.monthly_club_view.refresh()
        self.pages_stack.setCurrentWidget(self.monthly_club_plans_page)

    def _monthly_club_plans_tab_changed(self, tab_index):
        if tab_index == 0:
            self._load_monthly_club_plans()
        elif tab_index == 1:
            self.monthly_club_view.refresh()

    def _load_monthly_club_plans(self):
        try:
            plans = self.db.cultural_club_monthly_plans(self.db.year_id)
        except sqlite3.Error as error:
            QMessageBox.warning(
                self, "تعذر تحميل المخططات الشهرية", str(error)
            )
            return
        self._render_monthly_club_plans(plans)

    def _render_monthly_club_plans(self, plans):
        while self.monthly_club_cards_layout.count():
            item = self.monthly_club_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not plans:
            empty_label = QLabel("لا توجد مخططات شهرية مضافة لهذه السنة.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.monthly_club_cards_layout.addWidget(empty_label)
            return

        month_locale = QLocale(QLocale.Language.Arabic, QLocale.Country.Tunisia)
        for plan in plans:
            card = MonthlyClubPlanCard(
                plan, self.monthly_club_cards_container
            )
            card.editRequested.connect(self.edit_monthly_club_plan)
            card.deleteRequested.connect(self.delete_monthly_club_plan)
            card.exportPdfRequested.connect(
                self.export_monthly_club_plan_pdf
            )
            card.printRequested.connect(self.print_monthly_club_plan)
            card.previewRequested.connect(
                self.preview_monthly_club_plan
            )
            card.exportJsonRequested.connect(
                self.export_monthly_club_plan_json
            )

            month_date = QDate.fromString(
                f"{plan.get('month', '')}-01", "yyyy-MM-dd"
            )
            month_name = (
                month_locale.toString(month_date, "MMMM yyyy")
                if month_date.isValid() else str(plan.get("month") or "")
            )
            sessions = plan.get("sessions", [])
            card.content_layout.addWidget(QLabel(f"الشهر: {month_name}"))
            card.content_layout.addWidget(
                QLabel(f"عدد الجلسات: {len(sessions)}")
            )
            session_dates = []
            for session in sessions:
                session_date = QDate.fromString(
                    str(session.get("session_date") or ""), "yyyy-MM-dd"
                )
                session_dates.append(
                    session_date.toString("dd/MM/yyyy")
                    if session_date.isValid()
                    else str(session.get("session_date") or "")
                )
            dates_label = QLabel(
                "تواريخ الجلسات: " + ("، ".join(session_dates) or "—")
            )
            dates_label.setWordWrap(True)
            card.content_layout.addWidget(dates_label)
            self.monthly_club_cards_layout.addWidget(card)

    @staticmethod
    def _monthly_club_plan_preview_payload(plan):
        sessions = plan.get("sessions", [])
        if not sessions:
            raise ValueError("لا توجد جلسات في المخطط المحدد.")
        lessons = []
        for index, session in enumerate(sessions, start=1):
            session_date = str(session.get("session_date") or "")
            if not QDate.fromString(session_date, "yyyy-MM-dd").isValid():
                raise ValueError("تاريخ إحدى جلسات المخطط غير صالح.")
            lessons.append({
                "display_classe": (
                    f"{plan.get('club_name') or 'نادي'} — الجلسة {index}"
                ),
                "classe": plan.get("club_name") or "",
                "majal": plan.get("club_type") or "",
                "heure": "",
                "time": "",
                "display_unit_label": "الشهر",
                "display_unit_value": plan.get("month") or "",
                "wehda_number": "",
                "hessa_number": index,
                "namat_taallom": "",
                "activities": [{
                    "display_title": f"تاريخ الجلسة: {session_date}",
                    "details": list(session.get("properties", [])),
                }],
            })
        month_date = QDate.fromString(
            f"{plan.get('month') or ''}-01", "yyyy-MM-dd"
        )
        month_name = (
            QLocale(
                QLocale.Language.Arabic, QLocale.Country.Tunisia
            ).toString(month_date, "MMMM yyyy")
            if month_date.isValid() else str(plan.get("month") or "")
        )
        title = (
            f"مخطط نادي {plan.get('club_name') or 'دون اسم'} "
            f"لشهر {month_name}"
        )
        return {
            "date": sessions[0]["session_date"],
            "header_title": title,
            "preview_title": f"معاينة {title}",
            "hide_lesson_headers": True,
            "split_monthly_activity_details": True,
            "club_statistics": {
                "participant_count": int(
                    plan.get("participant_count") or 0
                ),
                "sections": list(plan.get("sections", [])),
            },
            "lessons": lessons,
        }

    def _monthly_club_plan_export_path(self, plan, extension, file_filter):
        from PySide6.QtWidgets import QFileDialog

        documents_dir = Path.home() / "Documents"
        start_dir = documents_dir if documents_dir.exists() else Path.home()
        club_name = str(plan.get("club_name") or "نادي")
        safe_name = club_name.replace("/", "_").replace("\\", "_")
        default_path = start_dir / (
            f"مخطط_{safe_name}_{plan.get('month') or ''}.{extension}"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"تصدير المخطط بصيغة {extension.upper()}",
            str(default_path),
            file_filter,
        )
        if not file_path:
            return None
        if Path(file_path).suffix.lower() != f".{extension}":
            file_path += f".{extension}"
        return Path(file_path)

    def export_monthly_club_plan_json(self, plan):
        file_path = self._monthly_club_plan_export_path(
            plan, "json", "ملفات JSON (*.json);;كل الملفات (*)"
        )
        if file_path is None:
            return
        try:
            with file_path.open("w", encoding="utf-8") as output:
                json.dump(plan, output, ensure_ascii=False, indent=2)
        except OSError as error:
            QMessageBox.critical(
                self, "تعذر تصدير JSON", str(error)
            )
            return
        self.statusBar().showMessage(
            f"تم تصدير المخطط إلى {file_path}", 5000
        )

    def export_monthly_club_plan_pdf(self, plan):
        from day_pdf_preview import export_day_preview_to_pdf

        file_path = self._monthly_club_plan_export_path(
            plan, "pdf", "ملفات PDF (*.pdf);;كل الملفات (*)"
        )
        if file_path is None:
            return
        try:
            payload = self._monthly_club_plan_preview_payload(plan)
            output_path = export_day_preview_to_pdf(payload, file_path)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر تصدير PDF", str(error)
            )
            return
        self.statusBar().showMessage(
            f"تم تصدير المخطط إلى {output_path}", 5000
        )

    def print_monthly_club_plan(self, plan):
        from day_pdf_preview import DayPdfPreviewDialog

        try:
            payload = self._monthly_club_plan_preview_payload(plan)
            DayPdfPreviewDialog(payload, self).print_pages()
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(
                self, "تعذرت طباعة المخطط", str(error)
            )

    def preview_monthly_club_plan(self, plan):
        from day_pdf_preview import DayPdfPreviewDialog

        try:
            payload = self._monthly_club_plan_preview_payload(plan)
            DayPdfPreviewDialog(payload, self).exec()
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(
                self, "تعذرت معاينة المخطط", str(error)
            )

    def edit_monthly_club_plan(self, plan_id):
        if not self.ensure_school_year_writable():
            return
        try:
            plan = next((
                item for item in self.db.cultural_club_monthly_plans(
                    self.db.year_id
                )
                if item["id"] == plan_id
            ), None)
        except sqlite3.Error as error:
            QMessageBox.warning(
                self, "تعذر تحميل المخطط", str(error)
            )
            return
        if plan is None:
            QMessageBox.warning(
                self, "المخطط غير موجود", "لم يعد المخطط المحدد موجودًا."
            )
            self._load_monthly_club_plans()
            return
        self.add_monthly_club_plan(plan)

    def delete_monthly_club_plan(self, plan):
        if not self.ensure_school_year_writable():
            return
        answer = QMessageBox.question(
            self,
            "تأكيد مسح المخطط",
            f"هل تريد مسح مخطط «{plan['club_name']}» لشهر {plan['month']}؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.delete_cultural_club_monthly_plan(
                self.db.year_id, plan["id"]
            )
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(
                self, "تعذر مسح المخطط", str(error)
            )
            return
        self._load_monthly_club_plans()

    def add_monthly_club_plan(self, plan=None):
        if not self.ensure_school_year_writable():
            return
        if plan is None:
            dialog = MonthlyClubPlanDialog(
                self.db, self.db.year_id, parent=self
            )
        else:
            dialog = MonthlyClubPlanDialog(
                self.db, self.db.year_id, parent=self, plan=plan
            )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            save_values = (
                self.db.year_id,
                values["club_id"],
                values["month"],
                values["sessions"],
            )
            if plan is None:
                self.db.save_cultural_club_monthly_plan(*save_values)
            else:
                self.db.save_cultural_club_monthly_plan(
                    *save_values, plan_id=plan["id"]
                )
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(
                self, "تعذر حفظ المخطط الشهري", str(error)
            )
            return
        self.statusBar().showMessage(
            "تم حفظ المخطط الشهري للنادي بنجاح.", 5000
        )
        if hasattr(self, "_load_monthly_club_plans"):
            self._load_monthly_club_plans()

    def update_page_navigation_actions(self, current_index):
        current_page = self.pages_stack.widget(current_index)
        for action, page in self._page_navigation_actions:
            action.setEnabled(current_page is not page)

    def update_page_header(self, current_index):
        page = self.pages_stack.widget(current_index)
        title, description = self._page_descriptions.get(
            page, ("المعين للتخطيط اليومي للحصص", "")
        )
        self.page_title_label.setText(title)
        self.page_description_label.setText(description)
        self.page_description_label.setVisible(bool(description))

    def open_competence_manager(self):
        dlg = CompetenceManagerDialog(db=self.db, parent=self)
        dlg.setLayoutDirection(self.layoutDirection())
        if self.styleSheet():
            dlg.setStyleSheet(self.styleSheet())
        dlg.exec()

    def open_concept_manager(self):
        dlg = ConceptManagerDialog(db=self.db, parent=self)
        dlg.setLayoutDirection(self.layoutDirection())
        if self.styleSheet():
            dlg.setStyleSheet(self.styleSheet())
        dlg.exec()

    def load_statistics(self, force_refresh=False):
        if getattr(self, "_statistics_thread", None) is not None:
            if force_refresh:
                self._statistics_refresh_pending = True
            return

        waiting_text = (
            "جارٍ تحديث التحليلات..."
            if force_refresh else "جارٍ تحميل التحليلات..."
        )
        self.stats_loading_label.setText(waiting_text)
        self.stats_loading_label.show()
        self.refresh_stats_btn.setEnabled(False)
        self.stats_cache_label.setText(waiting_text)

        self._statistics_thread = QThread(self)
        self._statistics_worker = StatisticsLoadWorker(
            self.db.path, force_refresh=force_refresh
        )
        self._statistics_worker.moveToThread(self._statistics_thread)
        self._statistics_thread.started.connect(
            self._statistics_worker.run, Qt.QueuedConnection
        )
        self._statistics_worker.result_ready.connect(self._display_statistics)
        self._statistics_worker.failed.connect(self._statistics_load_failed)
        self._statistics_worker.finished.connect(self._statistics_thread.quit)
        self._statistics_worker.finished.connect(
            self._statistics_worker.deleteLater
        )
        self._statistics_thread.finished.connect(
            self._statistics_thread_finished
        )
        self._statistics_thread.start()

    @Slot(object, int, bool)
    def _display_statistics(self, payload, revision, from_cache):
        self.stats_loading_label.hide()
        self._statistics_source_revision = revision
        metrics = payload["metrics"]
        self.stats_cards["lessons"].setText(
            f"{metrics['lessons']:,}"
        )
        self.stats_cards["days"].setText(f"{metrics['days']:,}")
        self.stats_cards["classes"].setText(f"{metrics['classes']:,}")
        self.stats_cards["activities"].setText(
            f"{metrics['activities']:,}"
        )
        self.stats_cards["properties"].setText(
            f"{metrics['properties']:,}"
        )
        self.stats_cards["completion_rate"].setText(
            f"{metrics['completion_rate']:.1f}%"
        )
        self.stats_cards["average_activities"].setText(
            str(metrics["average_activities"])
        )
        self.stats_cards["average_properties"].setText(
            str(metrics["average_properties"])
        )
        forecast_total = sum(
            item["lessons"] for item in payload["forecast"]
        )
        self.stats_cards["forecast_total"].setText(
            str(forecast_total) if payload["forecast"] else "—"
        )
        plan_payload = payload["plans"]
        plan_metrics = plan_payload["metrics"]
        for key in (
            "plans", "planned_slots", "distributed_slots",
            "pending_slots", "complete_plans",
        ):
            self.plan_stats_cards[key].setText(
                f"{plan_metrics[key]:,}"
            )
        self.plan_stats_cards["progress_rate"].setText(
            f"{plan_metrics['progress_rate']:.1f}%"
        )
        self.plan_stats_cards["forecast_total"].setText(
            str(sum(
                item["plans"] for item in plan_payload["forecast"]
            )) if plan_payload["forecast"] else "—"
        )
        cache_state = "من قاعدة التحليلات المحلية" if from_cache else "تم تحديثها الآن"
        self.stats_cache_label.setText(
            f"{cache_state} — نسخة البيانات {revision} — "
            f"نسبة اكتمال الحصص {metrics['completion_rate']:.1f}%"
        )

        self._fill_statistics_table(
            self.stats_table,
            ["المجال", "الحصص", "النسبة"],
            [
                (
                    item["name"], item["count"],
                    f"{item['count'] / metrics['lessons'] * 100:.1f}%"
                    if metrics["lessons"] else "0%",
                )
                for item in payload["subjects"]
            ],
        )
        self._fill_statistics_table(
            self.stats_activity_table,
            ["النشاط", "عدد مرات التسجيل"],
            [(item["name"], item["count"]) for item in payload["activities"]],
        )
        self._fill_statistics_table(
            self.stats_property_table,
            ["النشاط", "اسم الخاصية", "الاستخدام", "أنشطة مختلفة"],
            [
                (
                    item["activity"], item["property"], item["uses"],
                    item["activities"],
                )
                for item in payload["property_usage"]
            ],
        )
        self._fill_statistics_table(
            self.stats_plan_table,
            [
                "المخطط", "القسم", "تاريخ البدء", "الحصص المخططة",
                "الموزع عليها نشاط", "المتبقية", "التقدم",
            ],
            [
                (
                    item["title"], item["class_name"], item["start_date"],
                    item["lesson_count"], item["distributed_slots"],
                    item["pending_slots"], f"{item['progress_rate']:.1f}%",
                )
                for item in plan_payload["items"]
            ],
        )
        self._fill_statistics_table(
            self.stats_plan_mode_table,
            [
                "نمط التعلم", "الحصص المخططة", "الموزعة",
                "المتبقية", "التقدم",
            ],
            [
                (
                    item["name"], item["planned"], item["distributed"],
                    item["pending"], f"{item['progress_rate']:.1f}%",
                )
                for item in plan_metrics["mode_progress"]
            ],
        )
        for section_key, report in self.stats_reports.items():
            report.setPlainText(
                self._format_statistics_report(section_key, payload)
            )
        self._draw_statistics_charts(payload)

    @staticmethod
    def _format_statistics_report(section_key, payload):
        if section_key == "plans":
            data = payload["plans"]
            metrics = data["metrics"]
            lines = [
                "تقرير إحصائيات المخططات التعليمية",
                "",
                f"عدد المخططات: {metrics['plans']}",
                f"الحصص المخططة: {metrics['planned_slots']}",
                f"الحصص التي وُزّع عليها نشاط: "
                f"{metrics['distributed_slots']}",
                f"الحصص التي لم يُوزّع عليها نشاط: "
                f"{metrics['pending_slots']}",
                f"نسبة التقدم الإجمالية: {metrics['progress_rate']:.1f}%",
                f"متوسط التقدم للمخطط: "
                f"{metrics['average_progress']:.1f}%",
                f"مخططات اكتمل توزيع حصصها: {metrics['complete_plans']}",
                "",
                "التقدم حسب نمط التعلم:",
            ]
            lines.extend(
                f"- {item['name']}: {item['distributed']}/"
                f"{item['planned']} حصة موزعة، "
                f"{item['pending']} متبقية "
                f"({item['progress_rate']:.1f}%)"
                for item in metrics["mode_progress"]
            )
            lines.extend((
                "",
                "تفاصيل المخططات:",
            ))
            if data["items"]:
                for item in data["items"]:
                    lines.append(
                        f"- {item['title']} | القسم: {item['class_name']} | "
                        f"البدء: {item['start_date']} | "
                        f"الموزع: {item['distributed_slots']}/"
                        f"{item['lesson_count']} "
                        f"({item['progress_rate']:.1f}%) | "
                        f"المتبقي: {item['pending_slots']}"
                    )
                    lines.extend(
                        f"  - {mode['name']}: {mode['distributed']}/"
                        f"{mode['planned']} موزع، "
                        f"{mode['pending']} متبقية"
                        for mode in item["mode_progress"]
                    )
            else:
                lines.append("- لا توجد مخططات مسجلة.")
            lines.extend(("", "السجل الأسبوعي لإنشاء المخططات:"))
            lines.extend(
                f"- {item['week']}: {item['plans']} مخطط"
                for item in data["weekly"]
            )
            lines.extend(("", "التوقع للأربعة أسابيع التالية:"))
            if data["forecast"]:
                lines.extend(
                    f"- {item['week']}: {item['plans']} مخطط متوقع"
                    for item in data["forecast"]
                )
            else:
                lines.append("- لا يتوفر توقع موثوق من السجل الحالي.")
            lines.extend((
                "",
                data["forecast_status"],
                "تنبيه: التقدم هنا يقيس تغطية الحصص بتوزيع نشاط واحد "
                "على الأقل لكل حصة، ولا يقيس تنفيذها ميدانياً. "
                "توقع إنشاء المخططات مبني على تواريخ إنشائها، وليس "
                "توقعاً لإنجاز التوزيع.",
            ))
            return "\n".join(lines)

        metrics = payload["metrics"]
        section_titles = {
            "overview": "دفتر إعداد الدروس",
            "activities": "الحصص والأنشطة",
            "properties": "الخصائص المسجلة",
        }
        lesson_total = metrics["lessons"]
        lines = [
            f"تقرير {section_titles.get(section_key, 'إعداد الدروس')}",
            "",
            f"إجمالي الحصص: {lesson_total}",
            f"الأيام المسجلة: {metrics['days']}",
            f"الأقسام المسجلة: {metrics['classes']}",
            f"الأنشطة المسجلة: {metrics['activities']}",
            f"الخصائص المسجلة: {metrics['properties']}",
            f"الحصص المكتملة: {metrics['complete_lessons']}",
            f"الحصص غير المكتملة: {metrics['incomplete_lessons']}",
            f"نسبة اكتمال الحصص: {metrics['completion_rate']:.1f}%",
            f"متوسط الأنشطة لكل حصة: {metrics['average_activities']}",
            f"متوسط الخصائص لكل نشاط: {metrics['average_properties']}",
            "",
            "توزيع الحصص حسب المجال:",
        ]
        if lesson_total:
            lines.extend(
                f"- {item['name']}: {item['count']} "
                f"({item['count'] / lesson_total * 100:.1f}%)"
                for item in payload["subjects"]
            )
        else:
            lines.append("- لا توجد حصص مسجلة.")
        lines.append("")
        lines.append("توزيع الحصص حسب نمط التعلم:")
        lines.extend(
            f"- {item['name']}: {item['count']}"
            for item in payload["learning_modes"]
        )
        lines.extend(("", "الأنشطة المسجلة:"))
        lines.extend(
            f"- {item['name']}: {item['count']}"
            for item in payload["activities"]
        )
        lines.extend(("", "استخدام الخصائص حسب النشاط:"))
        lines.extend(
            f"- {item['activity']} / {item['property']}: "
            f"{item['uses']} استخدام ضمن {item['activities']} نشاط"
            for item in payload["property_usage"]
        )
        lines.extend(("", "السجل الأسبوعي للحصص:"))
        lines.extend(
            f"- {item['week']}: {item['lessons']} حصة"
            for item in payload["weekly"]
        )
        lines.extend(("", "توقع الحصص للأربعة أسابيع التالية:"))
        if payload["forecast"]:
            lines.extend(
                f"- {item['week']}: {item['lessons']} حصة متوقعة"
                for item in payload["forecast"]
            )
        else:
            lines.append("- لا يتوفر توقع موثوق من السجل الحالي.")
        lines.extend((
            "",
            payload["forecast_status"],
            "التوقع استرشادي مبني على تواريخ الحصص المسجلة، ولا يمثل "
            "جدولاً مؤكداً للحصص القادمة.",
        ))
        return "\n".join(lines)

    @staticmethod
    def _fill_statistics_table(table, headers, rows):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row_index, column, item)
        table.resizeRowsToContents()

    def _draw_statistics_charts(self, payload):
        font = load_custom_font()
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [
            font, "Noto Naskh Arabic", "Arial", "DejaVu Sans"
        ]
        palette = [
            "#2563EB", "#0F766E", "#7C3AED", "#D97706",
            "#DB2777", "#0891B2", "#65A30D", "#EA580C",
        ]

        figure, axis, canvas = self.stats_charts["subjects"]
        axis.clear()
        subjects = payload["subjects"][:10]
        if subjects:
            names = [item["name"] for item in reversed(subjects)]
            counts = [item["count"] for item in reversed(subjects)]
            axis.barh(names, counts, color=palette[:len(names)])
            axis.set_xlabel("عدد الحصص")
            axis.grid(axis="x", alpha=0.2)
        else:
            axis.text(0.5, 0.5, "لا توجد بيانات بعد", ha="center", va="center")
        axis.spines[["top", "right", "left"]].set_visible(False)
        figure.tight_layout()
        canvas.draw_idle()

        figure, axis, canvas = self.stats_charts["modes"]
        axis.clear()
        modes = payload["learning_modes"]
        if modes and sum(item["count"] for item in modes):
            axis.pie(
                [item["count"] for item in modes],
                labels=[item["name"] for item in modes],
                autopct="%1.0f%%", startangle=90,
                colors=palette[:len(modes)],
                wedgeprops={"width": 0.42, "edgecolor": "#FFFFFF"},
            )
            axis.axis("equal")
        else:
            axis.text(0.5, 0.5, "لا توجد بيانات بعد", ha="center", va="center")
        figure.tight_layout()
        canvas.draw_idle()

        figure, axis, canvas = self.stats_charts["properties"]
        axis.clear()
        property_usage = payload["property_usage"][:10]
        if property_usage:
            labels = [
                f"{item['activity']} — {item['property']}"
                for item in reversed(property_usage)
            ]
            counts = [
                item["uses"] for item in reversed(property_usage)
            ]
            axis.barh(labels, counts, color="#DB2777")
            axis.set_xlabel("عدد القيم المسجلة")
            axis.grid(axis="x", alpha=0.2)
            axis.tick_params(axis="y", labelsize=8)
        else:
            axis.text(0.5, 0.5, "لا توجد خصائص مسجلة", ha="center", va="center")
        axis.spines[["top", "right", "left"]].set_visible(False)
        figure.tight_layout()
        canvas.draw_idle()

        figure, axis, canvas = self.stats_charts["weekly"]
        axis.clear()
        weekly = payload["weekly"]
        forecast = payload["forecast"]
        if weekly:
            historical_labels = [item["week"] for item in weekly]
            historical_counts = [item["lessons"] for item in weekly]
            axis.plot(
                historical_labels, historical_counts,
                color="#2563EB", marker="o", linewidth=2,
                label="الحصص المسجلة",
            )
            if forecast:
                forecast_labels = [item["week"] for item in forecast]
                forecast_counts = [item["lessons"] for item in forecast]
                axis.plot(
                    [historical_labels[-1], *forecast_labels],
                    [historical_counts[-1], *forecast_counts],
                    color="#EA580C", marker="o", linestyle="--",
                    linewidth=2, label="التوقع",
                )
            axis.tick_params(axis="x", labelrotation=35, labelsize=8)
            axis.grid(axis="y", alpha=0.2)
            axis.legend(frameon=False)
        else:
            axis.text(0.5, 0.5, "لا توجد بيانات زمنية", ha="center", va="center")
        axis.spines[["top", "right"]].set_visible(False)
        figure.tight_layout()
        canvas.draw_idle()

        figure, axis, canvas = self.stats_charts["plan_progress"]
        axis.clear()
        plan_items = payload["plans"]["items"]
        if plan_items:
            displayed_plans = sorted(
                plan_items, key=lambda item: item["progress_rate"]
            )[:12]
            axis.barh(
                [item["title"] for item in reversed(displayed_plans)],
                [item["progress_rate"] for item in reversed(displayed_plans)],
                color="#0F766E",
            )
            axis.set_xlim(0, 100)
            axis.set_xlabel("نسبة الحصص الموزع عليها نشاط")
            axis.grid(axis="x", alpha=0.2)
            axis.tick_params(axis="y", labelsize=8)
        else:
            axis.text(0.5, 0.5, "لا توجد مخططات بعد", ha="center", va="center")
        axis.spines[["top", "right", "left"]].set_visible(False)
        figure.tight_layout()
        canvas.draw_idle()

        figure, axis, canvas = self.stats_charts["plan_weekly"]
        axis.clear()
        plan_data = payload["plans"]
        plan_weekly = plan_data["weekly"]
        plan_forecast = plan_data["forecast"]
        if plan_weekly:
            historical_labels = [item["week"] for item in plan_weekly]
            historical_counts = [item["plans"] for item in plan_weekly]
            axis.plot(
                historical_labels, historical_counts,
                color="#2563EB", marker="o", linewidth=2,
                label="المخططات المنشأة",
            )
            if plan_forecast:
                forecast_labels = [
                    item["week"] for item in plan_forecast
                ]
                forecast_counts = [
                    item["plans"] for item in plan_forecast
                ]
                axis.plot(
                    [historical_labels[-1], *forecast_labels],
                    [historical_counts[-1], *forecast_counts],
                    color="#EA580C", marker="o", linestyle="--",
                    linewidth=2, label="التوقع",
                )
            axis.tick_params(axis="x", labelrotation=35, labelsize=8)
            axis.grid(axis="y", alpha=0.2)
            axis.legend(frameon=False)
        else:
            axis.text(
                0.5, 0.5, "لا توجد تواريخ إنشاء صالحة",
                ha="center", va="center",
            )
        axis.spines[["top", "right"]].set_visible(False)
        figure.tight_layout()
        canvas.draw_idle()

    @Slot(str)
    def _statistics_load_failed(self, message):
        self.stats_loading_label.setText(message)
        self.stats_loading_label.show()
        self.stats_cache_label.setText("فشل تحديث التحليلات")
        QMessageBox.critical(self, "تعذر تحميل الإحصائيات", message)

    @Slot()
    def _statistics_thread_finished(self):
        thread = self._statistics_thread
        self._statistics_worker = None
        self._statistics_thread = None
        if thread is not None:
            thread.deleteLater()
        self.refresh_stats_btn.setEnabled(True)
        if getattr(self, "_statistics_refresh_pending", False):
            self._statistics_refresh_pending = False
            self.load_statistics(force_refresh=True)

    def _check_statistics_revision(self):
        if self.pages_stack.currentWidget() is not self.stats_page:
            return
        if getattr(self, "_statistics_thread", None) is not None:
            return
        try:
            revision = self.db.analytics_revision()
        except sqlite3.Error as exc:
            self.statusBar().showMessage(
                f"تعذر فحص تحديثات الإحصائيات: {exc}", 5000
            )
            return
        if revision != getattr(self, "_statistics_source_revision", None):
            self.load_statistics()

    def open_teacher_identity(self):
        if self._small_window_profile:
            self.day_lessons_page.show_teacher_info_popup(
                self.teacher_year_photo_placeholder
            )
            return
        self.toggle_enseig_info()

    def toggle_enseig_info(self):
        self.load_school_info()
        self.pages_stack.setCurrentWidget(self.teacher_info_page)

    def update_add_school_year_action_state(self):
        if not hasattr(self, "add_school_year_action"):
            return
        self.add_school_year_action.setEnabled(
            not self.is_school_year_read_only
            and self.db.year_id != self.db.current_school_year_id()
        )

    def ensure_school_year_writable(self):
        if not self.is_school_year_read_only:
            return True
        QMessageBox.information(
            self, "السنة الدراسية للعرض فقط",
            "السنة الدراسية المحددة سابقة؛ يمكنك تصفحها وتصدير بياناتها فقط."
        )
        return False

    def set_lesson_date_range(self, school_year_name=None):
        if school_year_name is None:
            school_info = self.db.school_info()
            if not school_info:
                raise ValueError("بيانات السنة الدراسية المحددة غير موجودة.")
            school_year_name = school_info[0]
        try:
            start_year_text, end_year_text = str(school_year_name).split("-", 1)
            start_year = int(start_year_text)
            end_year = int(end_year_text)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"اسم السنة الدراسية غير صالح: {school_year_name}"
            ) from error
        if end_year != start_year + 1:
            raise ValueError(
                f"اسم السنة الدراسية غير صالح: {school_year_name}"
            )
        first_day = QDate(start_year, 9, 1)
        last_day = QDate(end_year, 6, 30)
        self.date_edit.setDateRange(first_day, last_day)
        self.custom_calendar.setDateRange(first_day, last_day)
        if getattr(
            self.custom_calendar, "_holiday_date_disabling_enabled", False
        ):
            self.custom_calendar.refresh_holiday_dates()

    def on_agenda_date_changed(self, *_args):
        selected_date = self.date_edit.date()
        if selected_date in self.custom_calendar._disabled_dates:
            self.custom_calendar.refresh_holiday_dates()
            if (
                self._last_enabled_agenda_date
                in self.custom_calendar._disabled_dates
            ):
                self._last_enabled_agenda_date = (
                    self.custom_calendar._nearest_enabled_date(selected_date)
                )
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(self._last_enabled_agenda_date)
            self.date_edit.blockSignals(False)
            self.custom_calendar.setSelectedDate(
                self._last_enabled_agenda_date
            )
            self.statusBar().showMessage(
                "لا يمكن اختيار يوم عطلة رسمية.", 3000
            )
            return
        self._last_enabled_agenda_date = selected_date
        self.load_day()

    def set_school_year_read_only(self, read_only):
        self.is_school_year_read_only = bool(read_only)
        for widget in self._year_scoped_mutation_widgets:
            widget.setEnabled(not self.is_school_year_read_only)
        self.update_paste_lessons_button_state()
        for action in self._year_scoped_mutation_actions:
            action.setEnabled(not self.is_school_year_read_only)
        if hasattr(self, "teacher_info_page"):
            self.teacher_info_page.set_read_only(
                self.is_school_year_read_only
            )
        if hasattr(self, "detail_cards"):
            self.detail_cards.set_read_only(self.is_school_year_read_only)
        if hasattr(self, "activity_cards"):
            self.activity_cards.set_read_only(self.is_school_year_read_only)
        if hasattr(self, "cultural_club_session_cards"):
            self.cultural_club_session_cards.set_read_only(
                self.is_school_year_read_only
            )
            self._sync_club_drop_group_visibility()
        self.update_add_school_year_action_state()
        self._update_add_activity_button()
        if hasattr(self, "timetable_page"):
            self.timetable_page.set_read_only(
                self.is_school_year_read_only
            )
        if hasattr(self, "exam_schedule_page"):
            self.exam_schedule_page.set_read_only(
                self.is_school_year_read_only
            )

    def add_school_year(self):
        if not self.ensure_school_year_writable():
            return
        new_year_name = self.db.school_year_name_for_date()
        school_info = self.db.school_info()
        if not school_info:
            QMessageBox.warning(
                self, "تعذر إضافة السنة الدراسية",
                "لم يتم العثور على بيانات السنة الدراسية الحالية."
            )
            return
        if str(school_info[0] or "").strip() == new_year_name:
            self.update_add_school_year_action_state()
            return

        dialog_values = _school_info_to_dialog_values(list(school_info))
        dialog_values[0] = new_year_name
        dlg = EntryDialog(
            "إضافة سنة دراسية جديدة", SCHOOL_INFO_DIALOG_FIELDS,
            values=dialog_values, parent=self
        )
        dlg.widgets[0].setReadOnly(True)
        if not dlg.exec():
            return

        values = _school_info_from_dialog_values(dlg.values())
        values[0] = new_year_name
        try:
            new_year_id = self.db.create_school_year(values)
        except ValueError as exc:
            QMessageBox.warning(self, "تعذر إضافة السنة الدراسية", str(exc))
            self.update_add_school_year_action_state()
            return
        except sqlite3.Error as exc:
            QMessageBox.critical(
                self, "تعذر إضافة السنة الدراسية",
                f"حدث خطأ أثناء حفظ بيانات السنة الجديدة:\n{exc}"
            )
            return

        self.db.year_id = new_year_id
        self.timetable_page.set_school_year(new_year_id)
        self.set_lesson_date_range(new_year_name)
        self.load_school_info()

        start_year = int(new_year_name.split("-", 1)[0])
        first_school_day = QDate(start_year, 9, 1)
        self.date_edit.setDate(first_school_day)
        self.load_day()
        self.day_lessons_page.set_day(
            None, first_school_day.toString("yyyy-MM-dd")
        )
        self.pages_stack.setCurrentWidget(self.lesson_page)
        self.update_add_school_year_action_state()
        self.statusBar().showMessage(
            f"تمت إضافة السنة الدراسية {new_year_name} مع الإبقاء على بيانات السنة السابقة.",
            5000,
        )
        QMessageBox.information(
            self, "تمت إضافة السنة الدراسية",
            f"أُضيفت السنة الدراسية {new_year_name}، "
            "ونُسخت إليها بيانات المعلم دون تغيير بيانات السنة السابقة."
        )

    def make_table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setMinimumHeight(120)
        return table

    def load_school_info(self):
        row = self.db.school_info()
        if row:
            values = list(row)
        else:
            default_values = [
                default for _label, _kind, default
                in SCHOOL_INFO_DIALOG_FIELDS
            ]
            default_values[0] = self.db.school_year_name_for_date()
            values = _school_info_from_dialog_values(default_values)
        self.update_teacher_year_identity(values)
        self.teacher_info_page.set_values(
            _school_info_to_dialog_values(values)
        )

    def update_teacher_year_identity(self, school_info):
        teacher_name = str(school_info[2] or "").strip()
        school_year = str(school_info[0] or "").strip()
        gender = (
            str(school_info[SCHOOL_INFO_COLUMNS.index("teacher_gender")] or "")
            .strip()
            if len(school_info) > SCHOOL_INFO_COLUMNS.index("teacher_gender")
            else ""
        )
        avatar_gender = "أنثى" if gender == "أنثى" else "ذكر"
        self.teacher_year_avatar_label.setPixmap(
            QIcon(str(TEACHER_AVATAR_ICONS[avatar_gender])).pixmap(
                self.teacher_year_avatar_label.size()
            )
        )
        self.teacher_year_photo_placeholder.setAccessibleName(
            "صورة المعلمة" if avatar_gender == "أنثى" else "صورة المعلم"
        )
        self.teacher_name_label.setText(
            teacher_name or "اسم المعلم غير محدد"
        )
        self.teacher_name_label.setToolTip(teacher_name)
        self.teacher_name_label.setAccessibleName("بيانات المعلم")
        self.teacher_year_identity_card.setToolTip(
            f"بيانات المعلم: {teacher_name or 'غير محدد'}"
        )
        self.teacher_year_identity_card.setAccessibleName("بيانات المعلم")
        self.current_school_year_label.setText(
            school_year or "—"
        )
        self.current_school_year_label.setAccessibleName("السنة الدراسية")
        self.set_small_window_profile(
            getattr(self, "_small_window_profile", False)
        )

    def set_small_window_profile(self, enabled):
        self._small_window_profile = bool(enabled)
        set_application_button_scale(
            QApplication.instance(),
            0.8 if self._small_window_profile else 1.0,
        )
        day_lessons_page = getattr(self, "day_lessons_page", None)
        if day_lessons_page is not None:
            day_lessons_page.set_compact_mode(self._small_window_profile)
        plans_page = getattr(self, "plans_page", None)
        if plans_page is not None:
            plans_page.set_compact_mode(self._small_window_profile)
        timetable_page = getattr(self, "timetable_page", None)
        if timetable_page is not None:
            timetable_page.set_compact_mode(self._small_window_profile)
        recorded_lesson_cards = getattr(
            self, "recorded_lesson_cards", None
        )
        if recorded_lesson_cards is not None:
            recorded_lesson_cards.set_compact_mode(
                self._small_window_profile
            )
        activity_cards = getattr(self, "activity_cards", None)
        if activity_cards is not None:
            activity_cards.set_compact_mode(
                self._small_window_profile
            )
        club_session_cards = getattr(
            self, "cultural_club_session_cards", None
        )
        if club_session_cards is not None:
            club_session_cards.set_compact_mode(
                self._small_window_profile
            )
        for list_name in (
            "scheduled_lessons_list",
            "scheduled_club_lessons_list",
            "scheduled_exam_lessons_list",
        ):
            scheduled_list = getattr(self, list_name, None)
            if scheduled_list is not None:
                scheduled_list.set_compact_mode(
                    self._small_window_profile
                )
        self._sync_lesson_drop_splitter_size()
        self._sync_day_status_display()
        for group, layout, normal_margins in getattr(
            self, "_small_drop_group_layouts", ()
        ):
            if group.property("smallProfile") == self._small_window_profile:
                continue
            margins = (
                (3, 3, 3, 3)
                if self._small_window_profile
                else normal_margins
            )
            layout.setContentsMargins(*margins)
            group.setProperty(
                "smallProfile", self._small_window_profile
            )
            group.style().unpolish(group)
            group.style().polish(group)
            group.update()
        for button in (
            getattr(self, "prev_btn", None),
            getattr(self, "next_btn", None),
        ):
            if button is not None:
                button.setVisible(not self._small_window_profile)
        lesson_cards_hint = getattr(self, "lesson_cards_hint", None)
        if lesson_cards_hint is not None:
            lesson_cards_hint.setVisible(not self._small_window_profile)
        self.current_school_year_label.setVisible(
            not self._small_window_profile
        )

        identity_layout = self.teacher_year_identity_card.layout()
        if self._small_window_profile:
            identity_layout.setContentsMargins(5, 4, 5, 4)
            identity_layout.setSpacing(5)
            self.teacher_identity_text_layout.setSpacing(0)
            margins = identity_layout.contentsMargins()
            width = (
                margins.left()
                + self.teacher_year_photo_placeholder.width()
                + identity_layout.spacing()
                + self.teacher_name_label.sizeHint().width()
                + margins.right()
            )
        else:
            identity_layout.setContentsMargins(10, 4, 10, 4)
            identity_layout.setSpacing(10)
            self.teacher_identity_text_layout.setSpacing(8)
            width = identity_layout.sizeHint().width()

        self.teacher_year_identity_card.setFixedWidth(width)
        self.teacher_notification_group.setFixedWidth(
            width
            + self.notification_button.width()
            + self.teacher_notification_group.layout().spacing()
        )
        if hasattr(self, "navigation_toolbar_layout"):
            self._set_small_navigation_alignment(
                self._small_window_profile
            )

    def _sync_lesson_drop_splitter_size(self):
        splitter = getattr(self, "lesson_drop_splitter", None)
        if splitter is None:
            return
        splitter.setSizes(
            [220, 1000]
            if self._small_window_profile else [340, 900]
        )

    def _set_day_status_text(self, text):
        self.day_status.setText(text)
        self._sync_day_status_display()

    def _sync_day_status_display(self):
        day_status = getattr(self, "day_status", None)
        date_edit = getattr(self, "date_edit", None)
        if day_status is None or date_edit is None:
            return

        small = getattr(self, "_small_window_profile", False)
        day_status.setVisible(not small)
        tooltip = day_status.text() if small else ""
        date_edit.setToolTip(tooltip)
        line_edit = date_edit.lineEdit()
        if line_edit is not None:
            line_edit.setToolTip(tooltip)

    def _set_small_navigation_alignment(self, enabled):
        layout = self.navigation_toolbar_layout
        left_section = self.navigation_toolbar_left_section
        menu_section = self.navigation_toolbar_menu_section
        right_section = self.navigation_toolbar_right_section
        for section in (left_section, menu_section, right_section):
            layout.removeWidget(section)

        if enabled:
            layout.setColumnStretch(0, 0)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 0)
            layout.addWidget(
                left_section, 0, 0,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            layout.addWidget(right_section, 0, 1)
            layout.addWidget(
                menu_section, 0, 2,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            return

        for column in range(3):
            layout.setColumnStretch(column, 1)
        layout.addWidget(
            left_section, 0, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(
            menu_section, 0, 1, 1, 1,
            Qt.AlignmentFlag.AlignCenter,
        )
        layout.addWidget(right_section, 0, 2)

    def refresh_notification_badge(self, force=False):
        year_id = self.db.year_id
        try:
            revision = self.db.analytics_revision()
            if (
                not force
                and year_id == self._notification_year_id
                and revision == self._notification_revision
            ):
                return True
            notifications = (
                self.db.lesson_completion_notifications(year_id)
                + self.db.teaching_plan_lesson_notifications(year_id)
                + self.db.cultural_club_session_notifications(year_id)
                + self.db.calendar_event_notifications(year_id)
            )
            self._notification_items = notifications
            self._notification_year_id = year_id
            self._notification_revision = self.db.analytics_revision()
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر تحميل الإشعارات", str(error)
            )
            return False

        unread_count = sum(
            not notification["is_read"]
            for notification in self._notification_items
        )
        if unread_count:
            self.notification_badge.setText(
                str(unread_count) if unread_count < 100 else "99+"
            )
            self.notification_badge.adjustSize()
            self.notification_badge.setFixedHeight(18)
            self.notification_badge.setFixedWidth(
                max(18, self.notification_badge.sizeHint().width())
            )
            self.notification_badge.move(
                self.notification_button.width()
                - self.notification_badge.width() + 2,
                -2,
            )
            self.notification_badge.raise_()
            self.notification_badge.show()
        else:
            self.notification_badge.hide()
        self.notification_button.setToolTip(
            f"الإشعارات غير المقروءة: {unread_count}"
            if unread_count else "الإشعارات"
        )
        return True

    def schedule_notification_refresh(self):
        timer = getattr(self, "_notification_refresh_timer", None)
        if timer is not None:
            timer.start()

    def show_notifications(self):
        if not self.refresh_notification_badge(force=True):
            return
        unread_lesson_ids = [
            notification["lesson_id"]
            for notification in self._notification_items
            if (
                notification["notification_type"] == "lesson_completion"
                and not notification["is_read"]
            )
        ]
        unread_club_session_ids = [
            notification["club_session_id"]
            for notification in self._notification_items
            if (
                notification["notification_type"] == "club_session"
                and not notification["is_read"]
            )
        ]
        unread_planned_lesson_keys = [
            (
                notification["plan_id"],
                notification["lesson_number"],
                notification["learning_mode"],
            )
            for notification in self._notification_items
            if (
                notification["notification_type"] == "planned_lesson"
                and not notification["is_read"]
            )
        ]
        unread_calendar_event_keys = [
            (
                notification["event_type"],
                notification["event_id"],
                notification["reminder_date"],
            )
            for notification in self._notification_items
            if (
                notification["notification_type"] == "calendar_event"
                and not notification["is_read"]
            )
        ]
        if (
            unread_lesson_ids or unread_club_session_ids
            or unread_planned_lesson_keys or unread_calendar_event_keys
        ):
            try:
                if unread_lesson_ids:
                    self.db.mark_lesson_completion_notifications_read(
                        self.db.year_id, unread_lesson_ids
                    )
                if unread_planned_lesson_keys:
                    self.db.mark_teaching_plan_lesson_notifications_read(
                        self.db.year_id, unread_planned_lesson_keys
                    )
                if unread_club_session_ids:
                    self.db.mark_cultural_club_session_notifications_read(
                        self.db.year_id, unread_club_session_ids
                    )
                if unread_calendar_event_keys:
                    self.db.mark_calendar_event_notifications_read(
                        self.db.year_id, unread_calendar_event_keys
                    )
                self._notification_revision = self.db.analytics_revision()
            except (sqlite3.Error, ValueError) as error:
                QMessageBox.critical(
                    self, "تعذر تحديث حالة الإشعارات", str(error)
                )
                return
            for notification in self._notification_items:
                notification["is_read"] = True
            self.notification_badge.hide()
            self.notification_button.setToolTip("الإشعارات")

        menu = QMenu(self.notification_button)
        menu.setObjectName("notificationsMenu")
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu_content = QWidget(menu)
        menu_content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu_layout = QVBoxLayout(menu_content)
        menu_layout.setContentsMargins(8, 8, 8, 8)
        menu_layout.setSpacing(6)
        header = QLabel(
            f"الإشعارات ({len(self._notification_items)})",
            menu_content,
        )
        header.setStyleSheet(
            "font-weight: 700; color: #1E293B; padding: 4px;"
        )
        menu_layout.addWidget(header)

        if self._notification_items:
            notification_list = QListWidget(menu_content)
            notification_list.setObjectName("notificationList")
            notification_list.setMinimumWidth(380)
            notification_list.setMaximumWidth(440)
            notification_list.setMaximumHeight(360)
            notification_list.setWordWrap(True)
            notification_list.setStyleSheet(
                "QListWidget#notificationList {"
                "background: #FFFFFF; border: 0;}"
                "QListWidget#notificationList::item {"
                "padding: 7px; border-bottom: 1px solid #E2E8F0;}"
                "QListWidget#notificationList::item:selected {"
                "background: #EFF6FF; color: #1E293B;}"
            )
            for notification in self._notification_items:
                if notification["notification_type"] == "calendar_event":
                    if notification["event_type"] == "exam":
                        title_parts = [
                            "امتحان",
                            str(notification["title"]),
                            str(notification["class_name"]),
                            str(notification["date"]),
                            f"الساعة {notification['start_time']}",
                        ]
                        if notification["activities"]:
                            title_parts.append(
                                "الأنشطة: "
                                + "، ".join(notification["activities"])
                            )
                    else:
                        holiday_label = (
                            "عطلة رسمية"
                            if notification["holiday_type"] == "official"
                            else "عطلة غير رسمية"
                        )
                        title_parts = [
                            holiday_label,
                            str(notification["title"]),
                            str(notification["date"]),
                        ]
                        if notification["end_date"] != notification["date"]:
                            title_parts.append(
                                f"إلى {notification['end_date']}"
                            )
                    text = " — ".join(
                        part for part in title_parts if part
                    )
                    text += "\nتذكير قبل الموعد بيومين."
                    tooltip = text
                    visible_issues = text.splitlines()
                else:
                    if notification["notification_type"] == "club_session":
                        title_parts = [
                            "حصة نادي غير مسجلة",
                            str(notification["club_name"]),
                            str(notification["date"]),
                        ]
                    elif notification["notification_type"] == "planned_lesson":
                        title_parts = [
                            f"مخطط {notification['plan_title']}",
                            str(notification["class_name"]),
                            str(notification["domain"]),
                        ]
                        if notification["plan_number"] is not None:
                            title_parts.append(
                                f"المخطط {notification['plan_number']}"
                            )
                        title_parts.append(
                            f"الحصة {notification['lesson_number']} "
                            f"({notification['learning_mode']})"
                        )
                    else:
                        title_parts = [
                            str(notification["date"]),
                            str(notification["class_name"]),
                            str(notification["domain"]),
                        ]
                        if notification["lesson_number"] is not None:
                            title_parts.append(
                                f"الحصة {notification['lesson_number']}"
                            )
                    issues = notification["issues"]
                    visible_issues = issues[:3]
                    if len(issues) > 3:
                        visible_issues.append(
                            f"ومشكلات أخرى ({len(issues) - 3})"
                        )
                    text = " — ".join(
                        part for part in title_parts if part
                    )
                    text += "\n" + "\n".join(
                        f"• {issue}" for issue in visible_issues
                    )
                    tooltip = "\n".join(notification["issues"])
                item = QListWidgetItem(text)
                item.setToolTip(tooltip)
                item.setData(Qt.ItemDataRole.UserRole, notification)
                item.setSizeHint(QSize(
                    360, min(132, 48 + 20 * len(visible_issues))
                ))
                notification_list.addItem(item)
            menu_layout.addWidget(notification_list)
        else:
            empty_label = QLabel(
                "لا توجد إشعارات حالياً.", menu_content
            )
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setMinimumWidth(380)
            empty_label.setStyleSheet(
                "color: #64748B; padding: 18px;"
            )
            menu_layout.addWidget(empty_label)

        menu_action = QWidgetAction(menu)
        menu_action.setDefaultWidget(menu_content)
        menu.addAction(menu_action)
        menu.popup(self.notification_button.mapToGlobal(
            QPoint(0, self.notification_button.height())
        ))

    def save_school_info(self):
        if not self.ensure_school_year_writable():
            return
        values = _school_info_from_dialog_values(
            self.teacher_info_page.values()
        )
        if not values[0]:
            self.statusBar().showMessage(
                "أدخل السنة الدراسية ليتم حفظ بيانات المعلم.", 3000
            )
            return
        try:
            self.db.update_school_info(values)
        except (sqlite3.Error, ValueError, TypeError) as exc:
            QMessageBox.critical(
                self,
                "تعذر حفظ بيانات المعلم",
                f"حدث خطأ أثناء حفظ البيانات:\n{exc}",
            )
            return
        self.update_teacher_year_identity(values)
        self.statusBar().showMessage(
            "تم حفظ بيانات المعلم والمؤسسة تلقائيا.", 3000
        )

    def load_day(self, *_):
        qd = self.date_edit.date()
        day = qd.toString("yyyy-MM-dd")
        if self.is_school_year_read_only:
            self.day_id = self.db.recorded_day_id(day)
        else:
            self.day_id = self.db.get_day_id(day)
        self.selected_lesson_id = None
        self.selected_activity_id = None

        if hasattr(self, 'custom_calendar'):
            self.custom_calendar.refresh_recorded_dates()
            self.custom_calendar.update()
        
        self.activity_cards.clear()
        self.detail_cards.clear()
        self.refresh_lessons()
        self._set_day_status_text(
            f"التاريخ: {day} — عدد الحصص: "
            f"{self.lesson_table.rowCount()}"
        )

    def fill_table(self, table, rows):
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                for column, value in enumerate(row):
                    item = QTableWidgetItem(
                        "" if value is None else str(value)
                    )
                    if column == 0:
                        item.setData(Qt.UserRole, value)
                    table.setItem(row_index, column, item)
            table.resizeRowsToContents()
        finally:
            table.setUpdatesEnabled(True)
            table.viewport().update()

    def current_id(self, table):
        if isinstance(table, QListWidget):
            item = table.currentItem()
            value = item.data(Qt.UserRole) if item is not None else None
            return int(value) if value is not None else None
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        return int(item.text()) if item else None

    def refresh_lessons(self, select_id=None, select_first=False):
        rows = self.db.lessons(self.day_id)
        group_labels = {
            group_key: group["level_label"]
            for group_key, group in self.db.class_groups().items()
        }
        display_rows = [
            (
                *row[:2],
                (
                    f"{row[2]} — {group_labels[row[2]]}"
                    if row[2] in group_labels else row[2]
                ),
                *row[3:],
            )
            for row in rows
        ]
        self.fill_table(self.lesson_table, display_rows)
        manual_heading_names = self.refresh_scheduled_lessons(rows)
        plan_progress = {
            int(row[0]): progress
            for row in rows
            if (
                progress := self.db.lesson_plan_progress(row[0])
            ) is not None
        }
        repeat_lesson_statuses = self.db.repeat_request_statuses_for_day(
            self.day_id
        )
        self.recorded_lesson_cards.set_lessons(
            rows,
            heading_names=manual_heading_names,
            plan_progress=plan_progress,
            repeat_lesson_statuses=repeat_lesson_statuses,
            cultural_club_details=(
                _manual_lesson_cultural_club_details(
                    rows,
                    manual_heading_names,
                    self.db.cultural_clubs(self.db.year_id),
                )
                if manual_heading_names
                and callable(getattr(self.db, "cultural_clubs", None))
                else {}
            ),
        )
        self._update_workday_navigation_buttons()
        club_sessions = self.db.cultural_club_daily_sessions(
            self.date_edit.date().toString("yyyy-MM-dd")
        )
        club_cards = getattr(self, "cultural_club_session_cards", None)
        if club_cards is not None:
            club_cards.set_sessions(club_sessions)
            club_cards.set_read_only(self.is_school_year_read_only)
            self._sync_club_drop_group_visibility()
        self.view_day_btn.setEnabled(bool(rows or club_sessions))
        self._set_day_status_text(
            f"التاريخ: {self.date_edit.date().toString('yyyy-MM-dd')} — "
            f"عدد الحصص: {len(rows)} — جلسات النوادي: "
            f"{len(club_sessions)}"
        )
        
        selected_row = -1
        if select_id:
            for r in range(self.lesson_table.rowCount()):
                if int(self.lesson_table.item(r, 0).text()) == select_id:
                    selected_row = r
                    break
        elif select_first and self.lesson_table.rowCount() > 0:
            selected_row = 0

        self.lesson_table.blockSignals(True)
        self.lesson_table.clearSelection()
        if selected_row >= 0:
            self.lesson_table.setCurrentCell(selected_row, 0)
            self.lesson_table.selectRow(selected_row)
        else:
            self.lesson_table.setCurrentCell(-1, -1)
        self.lesson_table.blockSignals(False)
        self.recorded_lesson_cards.blockSignals(True)
        self.recorded_lesson_cards.select_lesson(
            rows[selected_row][0] if selected_row >= 0 else None
        )
        self.recorded_lesson_cards.blockSignals(False)
        self.on_lesson_selected()
        self._refresh_lesson_completion_colors()
        self.schedule_notification_refresh()

    def _scheduled_lesson_tab_changed(self, tab_index):
        self._sync_club_drop_group_visibility()

    def _refresh_scheduled_lesson_tab_indicators(self):
        if not hasattr(self, "scheduled_lessons_tabs"):
            return
        warning_icon = QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_MessageBoxWarning
        )
        for index, cards in enumerate((
            self.scheduled_lessons_list,
            self.scheduled_club_lessons_list,
            self.scheduled_exam_lessons_list,
        )):
            has_warnings = cards.has_missing_lesson_warnings()
            self.scheduled_lessons_tabs.setTabIcon(
                index, warning_icon if has_warnings else QIcon()
            )
            self.scheduled_lessons_tabs.setTabToolTip(
                index,
                (
                    "توجد حصص مجدولة لم تُضف إلى دفتر اليوم."
                    if has_warnings else ""
                ),
            )

    def _sync_club_drop_group_visibility(self, *_args):
        if not hasattr(self, "club_drop_group"):
            return
        has_scheduled_club_lessons = any(
            self.scheduled_club_lessons_list.item(row).data(
                Qt.ItemDataRole.UserRole
            ) is not None
            for row in range(self.scheduled_club_lessons_list.count())
        )
        should_be_visible = (
            has_scheduled_club_lessons
            or self.cultural_club_session_cards.has_sessions()
        )
        self.club_drop_group.setVisible(should_be_visible)

    def on_cultural_club_session_action(self, action, session_id):
        if action == "browse":
            self.show_cultural_club_session_details(session_id)
        elif action == "edit":
            self.edit_cultural_club_daily_session(session_id)
        elif action == "delete":
            self.delete_cultural_club_daily_session(session_id)

    def show_cultural_club_session_details(self, session_id):
        session_date = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            session = next(
                (
                    item
                    for item in self.db.cultural_club_daily_sessions(
                        session_date
                    )
                    if int(item["id"]) == int(session_id)
                ),
                None,
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر عرض حصة النادي", str(error)
            )
            return
        if session is None:
            QMessageBox.warning(
                self, "حصة غير موجودة",
                "لم تعد حصة النادي المحددة موجودة لهذا اليوم.",
            )
            self.refresh_lessons()
            return
        CulturalClubDailySessionDetailsDialog(session, self).exec()

    def edit_cultural_club_daily_session(self, session_id):
        if not self.ensure_school_year_writable():
            return
        session_date = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            session_id = int(session_id)
            session = next(
                (
                    item
                    for item in self.db.cultural_club_daily_sessions(
                        session_date
                    )
                    if int(item["id"]) == int(session_id)
                ),
                None,
            )
            repeat_request = (
                self.db.cultural_club_daily_repeat_request(session_id)
                if session is not None else None
            )
            next_monthly_session = (
                self.db.next_cultural_club_monthly_session(
                    self.db.year_id, session_id
                )
                if session is not None else None
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر تحميل جلسة النادي", str(error)
            )
            return
        if session is None:
            QMessageBox.warning(
                self, "جلسة غير موجودة",
                "لم تعد جلسة النادي المحددة موجودة لهذا اليوم.",
            )
            self.refresh_lessons()
            return

        repeat_requested = bool(
            repeat_request
            and repeat_request["repeat_for_next_session"]
            and repeat_request["confirmed_by_user"]
            and not repeat_request["is_applied"]
        )
        dialog = CulturalClubDailySessionEditDialog(
            session,
            self,
            allow_repeat=(
                next_monthly_session is not None or repeat_requested
            ),
            repeat_requested=repeat_requested,
            repeat_reason=(
                repeat_request["reason"] if repeat_requested else ""
            ),
        )
        if not dialog.exec():
            return
        interval, duration, properties = dialog.values()
        repeat_requested, repeat_reason = dialog.repeat_values()
        try:
            self.db.update_cultural_club_daily_session(
                self.db.year_id, session_id, interval, duration, properties,
                repeat_for_next_session=repeat_requested,
                repeat_reason=repeat_reason,
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر تعديل جلسة النادي", str(error)
            )
            return
        self.refresh_lessons()

    def add_unprogrammed_club_session(self):
        if not self.ensure_school_year_writable():
            return

        session_date = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            clubs = self.db.cultural_clubs(self.db.year_id)
            if not clubs:
                QMessageBox.information(
                    self, "لا توجد نوادٍ",
                    "أضف ناديًا إلى السنة الدراسية أولًا.",
                )
                return

            sessions = self.db.cultural_club_daily_sessions(session_date)
            day_lessons = (
                self.db.lessons(self.day_id) if self.day_id else []
            )
            occupied_lessons = SchoolPlanner._include_cultural_club_sessions(
                self, day_lessons, sessions
            )
            work_bounds = self._teacher_work_bounds()
            free_intervals = _unoccupied_work_intervals(
                occupied_lessons, *work_bounds
            )
            duration = clubs[0].get("session_duration_minutes")
            if duration not in (60, 120):
                duration = 60
            available_interval = next(
                (
                    (start, start + duration)
                    for start, end in free_intervals
                    if end - start >= duration
                ),
                None,
            )
            if available_interval is None:
                QMessageBox.information(
                    self, "لا توجد فترة شاغرة",
                    "لا توجد فترة عمل شاغرة تكفي لحصة نادي مدتها ساعة على الأقل.",
                )
                return
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر إضافة حصة النادي", str(error)
            )
            return

        start, end = available_interval
        interval = (
            f"{start // 60:02d}:{start % 60:02d} - "
            f"{end // 60:02d}:{end % 60:02d}"
        )
        dialog = CulturalClubDailySessionEditDialog(
            {"hour_interval": interval, "properties": []},
            self,
            clubs=clubs,
        )
        if not dialog.exec():
            return

        interval, duration, properties = dialog.values()
        club_id = dialog.selected_club_id()
        try:
            if not _hour_interval_is_available(
                interval, occupied_lessons, work_bounds
            ):
                QMessageBox.warning(
                    self, "توقيت مشغول",
                    "الفترة المحددة تتعارض مع حصة أخرى أو تقع خارج ساعات العمل.",
                )
                return
            self.db.save_cultural_club_daily_session(
                self.db.year_id,
                club_id,
                session_date,
                interval,
                duration,
                properties=properties,
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر إضافة حصة النادي", str(error)
            )
            return
        self.refresh_lessons()

    def delete_cultural_club_daily_session(self, session_id):
        if not self.ensure_school_year_writable():
            return
        answer = QMessageBox.question(
            self,
            "مسح جلسة النادي",
            "هل تريد مسح جلسة النادي وتوابعها من هذا اليوم؟",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.delete_cultural_club_daily_session(
                self.db.year_id, session_id
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر مسح جلسة النادي", str(error)
            )
            return
        self.refresh_lessons()

    def refresh_scheduled_lessons(self, day_lessons=None):
        weekday_num = self.date_edit.date().dayOfWeek() - 1
        target_day = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            if day_lessons is None:
                day_lessons = (
                    self.db.lessons(self.day_id) if self.day_id else []
                )
            work_bounds = self._teacher_work_bounds()
            cultural_club_sessions = (
                self.db.cultural_club_daily_sessions(target_day)
            )
            scheduled_exams = self.db.exam_schedules(target_day)
            recorded_exam_ids = set(
                self.db.exam_schedule_diary_lesson_ids(target_day)
            )
            occupied_lessons = SchoolPlanner._include_cultural_club_sessions(
                self, day_lessons, cultural_club_sessions
            )
            has_free_time = (
                True if work_bounds is None
                else _has_unoccupied_work_time(
                    occupied_lessons, *work_bounds
                )
            )
            manual_lessons = (
                self.db.manual_timetable_lessons_for_weekday(weekday_num)
            )
            if manual_lessons:
                lessons = manual_lessons
                source_label = "الجدول اليدوي"
                manual_heading_names = _manual_lesson_activity_names(
                    day_lessons, lessons
                )
            else:
                lessons = self.db.lessons_for_weekday(
                    weekday_num, target_day
                )
                source_label = "الجدول الآلي من سجل الحصص"
                manual_heading_names = {}
            lessons = self.db.adjust_scheduled_lessons_for_exams(
                target_day, lessons
            )
            occupied_intervals = set()
            disabled_candidate_intervals = set()
            for lesson in day_lessons:
                occupied_intervals.add(_parse_hour_interval(lesson[4]))
            for lesson in occupied_lessons[len(day_lessons):]:
                occupied_intervals.add(_parse_hour_interval(lesson[4]))
            for lesson in lessons:
                interval = _parse_hour_interval(lesson[2])
                if (
                    interval in occupied_intervals
                    or not _hour_interval_is_available(
                        lesson[2], occupied_lessons, work_bounds
                    )
                ):
                    disabled_candidate_intervals.add(interval)
            pedagogical_lessons, club_lessons = (
                _split_scheduled_lessons(lessons)
            )
            recorded_club_lessons = [
                (
                    None,
                    None,
                    section["section_name"],
                    session["club_type"],
                    session["hour_interval"],
                )
                for session in cultural_club_sessions
                for section in session["sections"]
            ]
            club_recorded_lessons = [
                *day_lessons,
                *recorded_club_lessons,
            ]
            exam_lessons = []
            for exam in scheduled_exams:
                (
                    exam_id, _exam_date, start_time, _teacher, _class_id,
                    class_name, subject, exam_duration, activities, _during,
                ) = exam
                start = datetime.strptime(start_time, "%H:%M")
                end = start + timedelta(minutes=exam_duration)
                plan = PLANS_NAMES.get(subject, {})
                domain = str(plan.get("المجال") or "").strip()
                if not domain:
                    raise ValueError(
                        f"لا يوجد مجال مسجل لمادة التقييم «{subject}»."
                    )
                exam_lessons.append((
                    class_name,
                    domain,
                    f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}",
                    f"{exam_duration} دقيقة",
                    None,
                    subject,
                    "scheduled_exam",
                    int(exam_id),
                    activities,
                ))
            has_recorded_lessons_today = bool(
                day_lessons or cultural_club_sessions
            )
            self.scheduled_lessons_list.set_lessons(
                pedagogical_lessons,
                disabled_intervals=disabled_candidate_intervals,
                allow_manual_add=(
                    has_free_time and not self.is_school_year_read_only
                ),
                recorded_lessons=day_lessons,
                warn_unrecorded=has_recorded_lessons_today,
            )
            self.scheduled_club_lessons_list.set_lessons(
                club_lessons,
                disabled_intervals=disabled_candidate_intervals,
                allow_manual_add=(
                    has_free_time and not self.is_school_year_read_only
                ),
                recorded_lessons=club_recorded_lessons,
                include_manual_card=True,
                warn_unrecorded=has_recorded_lessons_today,
                manual_card_text=(
                    "＋ حصة نادٍ غير مبرمجة\n"
                    "انقر مرتين لإضافتها يدويًا"
                ),
            )
            self.scheduled_exam_lessons_list.set_lessons(
                exam_lessons,
                include_manual_card=False,
                warn_unrecorded=has_recorded_lessons_today,
                recorded_exam_ids=recorded_exam_ids,
            )
            SchoolPlanner._sync_club_drop_group_visibility(self)
            SchoolPlanner._refresh_scheduled_lesson_tab_indicators(self)
            available_scheduled_lessons = any(
                _hour_interval_is_available(
                    lesson[2], occupied_lessons, work_bounds
                )
                for lesson in lessons
            )
            has_unrecorded_exams = any(
                int(lesson[7]) not in recorded_exam_ids
                for lesson in exam_lessons
            )
            self.add_all_lessons_button.setEnabled(
                (available_scheduled_lessons or has_unrecorded_exams)
                and not self.is_school_year_read_only
            )
            self.schedule_source_status.setText(
                (
                    f"المصدر: {source_label}"
                    if has_free_time else
                    "امتلأت ساعات العمل المحددة في جدول المعلم."
                ) if lessons
                else (
                    "لا توجد حصص في الجدول لهذا اليوم؛ " +
                    (
                        "يمكنك إضافة حصة يدويًا من البطاقة الأخيرة."
                        if has_free_time else
                        "لا توجد فترة عمل شاغرة لإضافة حصة."
                    )
                )
            )
            return manual_heading_names
        except (sqlite3.Error, ValueError) as exc:
            self.scheduled_lessons_list.set_lessons([])
            self.scheduled_club_lessons_list.set_lessons(
                [], include_manual_card=False
            )
            self.scheduled_exam_lessons_list.set_lessons(
                [], include_manual_card=False
            )
            SchoolPlanner._sync_club_drop_group_visibility(self)
            SchoolPlanner._refresh_scheduled_lesson_tab_indicators(self)
            self.add_all_lessons_button.setEnabled(False)
            self.schedule_source_status.setText(
                "تعذر تحميل حصص جدول الأوقات."
            )
            QMessageBox.critical(
                self,
                "تعذر تحميل جدول الأوقات",
                f"حدث خطأ أثناء تحميل حصص اليوم:\n{exc}",
            )
            return {}

    def _teacher_work_bounds(self):
        schedule = self.db.teacher_timetable()
        if schedule is None:
            return 7 * 60, 17 * 60

        try:
            start, end = _parse_hour_interval(
                f"{schedule.get('start_time', '')}-"
                f"{schedule.get('end_time', '')}"
            )
        except ValueError as exc:
            raise ValueError(
                "نطاق ساعات العمل في جدول المعلم غير صالح."
            ) from exc
        return start, end


    def _has_free_timetable_time(self):
        work_bounds = self._teacher_work_bounds()
        if work_bounds is None:
            return True
        lessons = self.db.lessons(self.day_id) if self.day_id else []
        lessons = SchoolPlanner._include_cultural_club_sessions(
            self, lessons
        )
        return _has_unoccupied_work_time(lessons, *work_bounds)

    def _include_cultural_club_sessions(self, lessons, sessions=None):
        database = getattr(self, "db", None)
        date_edit = getattr(self, "date_edit", None)
        loader = getattr(database, "cultural_club_daily_sessions", None)
        if not callable(loader) or date_edit is None:
            return list(lessons)
        if sessions is None:
            day_text = date_edit.date().toString("yyyy-MM-dd")
            sessions = loader(day_text)
        return [
            *lessons,
            *(
                (None, None, None, None, session["hour_interval"])
                for session in sessions
            ),
        ]

    def _validate_new_lesson_intervals(self, lessons, existing_lessons):
        work_bounds = self._teacher_work_bounds()
        existing_lessons = SchoolPlanner._include_cultural_club_sessions(
            self, existing_lessons
        )
        occupied_new = []
        for lesson in lessons:
            start, end = _parse_hour_interval(lesson[2])
            lesson_duration = duration_minutes(lesson[3])
            if (
                lesson_duration is not None
                and end - start != lesson_duration
            ):
                return False
            if not _hour_interval_is_available(
                lesson[2], existing_lessons, work_bounds
            ):
                return False
            interval_group = (
                (
                    "cultural_club",
                    str(lesson[8] or "").strip().casefold(),
                    str(lesson[1] or "").strip().casefold(),
                    str(lesson[2] or "").strip(),
                )
                if len(lesson) > 9
                and isinstance(lesson[9], list)
                and str(lesson[8] or "").strip()
                else None
            )
            if (
                len(lesson) > 7
                and lesson[6] == "cultural_club"
                and isinstance(lesson[7], list)
            ):
                interval_group = (
                    "cultural_club",
                    str(lesson[5] or "").strip().casefold(),
                    str(lesson[1] or "").strip().casefold(),
                    str(lesson[2] or "").strip(),
                )
            for occupied_start, occupied_end, occupied_group in occupied_new:
                if (
                    start < occupied_end
                    and occupied_start < end
                    and (
                        interval_group is None
                        or interval_group != occupied_group
                    )
                ):
                    return False
            occupied_new.append((start, end, interval_group))
        return True

    def _update_workday_navigation_buttons(self):
        selected_day = self.date_edit.date().toString("yyyy-MM-dd")
        recorded_days = [
            day for _, day in self.db.recorded_workdays()
            if day
        ]
        self.prev_btn.setEnabled(any(day < selected_day for day in recorded_days))
        self.next_btn.setEnabled(any(day > selected_day for day in recorded_days))

    def _navigate_recorded_workday(self, direction):
        selected_day = self.date_edit.date().toString("yyyy-MM-dd")
        recorded_days = sorted(
            day for _, day in self.db.recorded_workdays() if day
        )
        if direction < 0:
            candidates = [day for day in recorded_days if day < selected_day]
            target_day = candidates[-1] if candidates else None
        else:
            candidates = [day for day in recorded_days if day > selected_day]
            target_day = candidates[0] if candidates else None

        if target_day is not None:
            self.date_edit.setDate(QDate.fromString(target_day, "yyyy-MM-dd"))
        self._update_workday_navigation_buttons()

    def show_previous_recorded_workday(self):
        self._navigate_recorded_workday(-1)

    def show_next_recorded_workday(self):
        self._navigate_recorded_workday(1)

    def open_day_lessons_view(self):
        try:
            day_text = self.date_edit.date().toString("yyyy-MM-dd")
            club_sessions = self.db.cultural_club_daily_sessions(day_text)
            if not self.day_id or not (
                self.db.lessons(self.day_id) or club_sessions
            ):
                self.view_day_btn.setEnabled(False)
                return

            self.day_lessons_page.set_day(self.day_id, day_text)
            self.pages_stack.setCurrentWidget(self.day_lessons_page)
        except (sqlite3.Error, RuntimeError) as exc:
            QMessageBox.critical(
                self, "تعذر عرض حصص اليوم",
                f"حدث خطأ أثناء تحميل بيانات اليوم:\n{exc}"
            )

    def return_to_lesson_book(self):
        selected_date = QDate.fromString(
            self.day_lessons_page.day_text, "yyyy-MM-dd"
        )
        if not selected_date.isValid():
            QMessageBox.warning(
                self,
                "تاريخ غير صالح",
                "تعذر الرجوع إلى دفتر الدروس لأن تاريخ اليوم المعروض غير صالح.",
            )
            return
        self.date_edit.setDate(selected_date)
        self.load_day()
        self.pages_stack.setCurrentWidget(self.lesson_page)

    def open_day_lessons_from_menu(self):
        day_text = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            day_id = self.db.recorded_day_id(day_text)
            self.day_lessons_page.set_day(day_id, day_text)
            self.pages_stack.setCurrentWidget(self.day_lessons_page)
        except (sqlite3.Error, RuntimeError) as exc:
            QMessageBox.critical(
                self, "تعذر عرض حصص اليوم",
                f"حدث خطأ أثناء تحميل بيانات اليوم:\n{exc}"
            )

    def refresh_activities(self, select_id=None):
        if not self.selected_lesson_id:
            self.activity_cards.clear()
            self.selected_activity_id = None
            self.detail_cards.clear()
            self._update_add_activity_button()
            self._refresh_lesson_completion_colors()
            self.schedule_notification_refresh()
            return
        self.db.ensure_lesson_activities(self.selected_lesson_id)
        activities = self.db.activities(self.selected_lesson_id)
        class_names = {
            class_id: class_name
            for class_id, class_name, _level_name
            in self.db.lesson_classes(self.selected_lesson_id)
        }
        activity_scopes = self.db.activity_scopes(self.selected_lesson_id)
        club_loader = getattr(self.db, "cultural_clubs", None)
        cultural_clubs = (
            club_loader(self.db.year_id)
            if activities and callable(club_loader) else []
        )
        displayed_activities = []
        for activity_id, title, duration in activities:
            class_id = activity_scopes.get(activity_id)
            class_name = class_names.get(class_id, "")
            club_title = _cultural_club_activity_title(
                title, class_name, cultural_clubs
            )
            display_title = club_title or (
                f"{title} — {class_name}" if class_name else title
            )
            displayed_activities.append(
                (activity_id, display_title, duration)
            )
        completion_data = self.db.activity_completion_data(
            (self.selected_lesson_id,)
        ).get(self.selected_lesson_id, {})
        learning_mode = completion_data.get("learning_mode", "")
        details_by_id = completion_data.get("activities", {})
        issues_by_id = {
            activity[0]: self._activity_completion_issues(
                details_by_id.get(activity[0], {}).get("details", []),
                learning_mode,
            )
            for activity in activities
        }
        self.activity_cards.blockSignals(True)
        self.activity_cards.set_activities(
            displayed_activities, issues_by_id, select_id
        )
        self.activity_cards.blockSignals(False)
        self.selected_activity_id = self.current_id(self.activity_cards)
        self._refresh_lesson_completion_colors()
        self._update_add_activity_button()
        self.refresh_details()
        self.schedule_notification_refresh()

    @staticmethod
    def _duration_minutes(value):
        return duration_minutes(value)

    @staticmethod
    def _required_activity_properties(learning_mode):
        return required_activity_properties(learning_mode)

    def _activity_completion_issues(self, details, learning_mode):
        return activity_completion_issues(details, learning_mode)

    @staticmethod
    def _set_completion_row_style(table, row, issues, item_type):
        if issues:
            background = QColor("#FEE2E2")
            foreground = QColor("#991B1B")
            state_text = "غير مكتملة"
            tooltip = f"{state_text}: " + "؛ ".join(issues)
        else:
            background = QColor("#DCFCE7")
            foreground = QColor("#166534")
            state_text = "مكتملة"
            tooltip = f"{item_type} {state_text} وفق الشروط المطلوبة."

        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is not None:
                item.setBackground(background)
                item.setForeground(foreground)
                item.setToolTip(tooltip)

    def _refresh_activity_completion_colors(self, activities=None):
        if not self.selected_lesson_id:
            return
        if activities is None:
            activities = self.db.activities(self.selected_lesson_id)
        completion_data = self.db.activity_completion_data(
            (self.selected_lesson_id,)
        ).get(self.selected_lesson_id, {})
        learning_mode = completion_data.get("learning_mode", "")
        details_by_id = completion_data.get("activities", {})
        issues_by_id = {
            activity[0]: self._activity_completion_issues(
                details_by_id.get(activity[0], {}).get("details", []),
                learning_mode,
            )
            for activity in activities
        }
        for row in range(self.activity_cards.count()):
            item = self.activity_cards.item(row)
            card = self.activity_cards.itemWidget(item)
            if card is None:
                continue
            indicator = card.findChild(
                LessonStatusIndicator, "lessonStatusIndicator"
            )
            if indicator is not None:
                indicator.set_issues(
                    issues_by_id.get(int(item.data(Qt.UserRole)), [])
                )

    def _refresh_lesson_completion_colors(self):
        lesson_ids = [
            int(self.lesson_table.item(row, 0).text())
            for row in range(self.lesson_table.rowCount())
            if self.lesson_table.item(row, 0) is not None
        ]
        completion_data = self.db.activity_completion_data(lesson_ids)
        self._refresh_lesson_card_completion_indicators(completion_data)
        for row in range(self.lesson_table.rowCount()):
            id_item = self.lesson_table.item(row, 0)
            if id_item is None:
                continue
            lesson_id = int(id_item.text())
            lesson = completion_data.get(lesson_id, {})
            self._set_completion_row_style(
                self.lesson_table, row, lesson_completion_issues(lesson),
                "الحصة"
            )

    def _refresh_lesson_card_completion_indicators(
        self, completion_data=None
    ):
        lesson_ids = [
            int(self.recorded_lesson_cards.item(row).data(Qt.UserRole))
            for row in range(self.recorded_lesson_cards.count())
            if self.recorded_lesson_cards.item(row).data(Qt.UserRole) is not None
        ]
        if completion_data is None:
            completion_data = self.db.activity_completion_data(lesson_ids)
        for row, lesson_id in enumerate(lesson_ids):
            item = self.recorded_lesson_cards.item(row)
            card = self.recorded_lesson_cards.itemWidget(item)
            if card is None:
                continue
            indicator = card.findChild(
                LessonStatusIndicator, "lessonStatusIndicator"
            )
            if indicator is not None:
                indicator.set_issues(
                    lesson_completion_issues(
                        completion_data.get(lesson_id, {})
                    )
                )

    def _activity_time_totals(self, exclude_activity_id=None):
        if not self.selected_lesson_id:
            return None, None, {}

        lesson = self.db.lesson(self.selected_lesson_id)
        lesson_minutes = self._duration_minutes(lesson[4]) if lesson else None
        if lesson_minutes is None:
            return None, None, {}

        members = self.db.lesson_classes(self.selected_lesson_id)
        class_ids = [row[0] for row in members]
        if not class_ids:
            class_ids = [None]
        class_names = {
            row[0]: row[1] for row in members
        }
        minutes_by_class = {member_id: 0 for member_id in class_ids}
        activity_scopes = self.db.activity_scopes(
            self.selected_lesson_id
        )
        for activity in self.db.activities(self.selected_lesson_id):
            if activity[0] == exclude_activity_id:
                continue
            minutes = self._duration_minutes(activity[2])
            if minutes is None:
                return lesson_minutes, None, class_names
            scope_id = activity_scopes.get(activity[0])
            affected_classes = (
                class_ids if scope_id is None else [scope_id]
            )
            for affected_class in affected_classes:
                if affected_class in minutes_by_class:
                    minutes_by_class[affected_class] += minutes
        return lesson_minutes, minutes_by_class, class_names

    def _activity_time_budget(
        self, exclude_activity_id=None, class_id=None
    ):
        lesson_minutes, minutes_by_class, _class_names = (
            self._activity_time_totals(exclude_activity_id)
        )
        if minutes_by_class is None or lesson_minutes is None:
            return lesson_minutes, None
        if class_id is not None:
            activity_minutes = minutes_by_class.get(class_id, 0)
        else:
            activity_minutes = max(minutes_by_class.values(), default=0)
        return lesson_minutes, activity_minutes

    def _show_shared_activity_time_status(self):
        lesson_minutes, minutes_by_class, class_names = (
            self._activity_time_totals()
        )
        if (
            lesson_minutes is None or minutes_by_class is None
            or len(minutes_by_class) < 2
        ):
            return

        summaries = []
        all_complete = True
        for class_id, minutes in minutes_by_class.items():
            name = class_names.get(class_id, str(class_id))
            if minutes == lesson_minutes:
                state = "مكتمل"
            elif minutes < lesson_minutes:
                remaining = lesson_minutes - minutes
                state = f"متبقي {remaining} دقيقة"
                all_complete = False
            else:
                excess = minutes - lesson_minutes
                state = f"تجاوز {excess} دقيقة"
                all_complete = False
            summaries.append(f"«{name}»: {minutes}/{lesson_minutes} دقيقة ({state})")

        message = (
            "اكتملت مدة الأنشطة لكل قسم: "
            if all_complete else "توزيع مدد الأنشطة لكل قسم: "
        ) + "؛ ".join(summaries)
        self.statusBar().showMessage(message, 10000)

    def _update_add_activity_button(self):
        if self.is_school_year_read_only:
            self.add_activity_button.setEnabled(False)
            self.add_activity_button.setToolTip(
                "السنة الدراسية السابقة متاحة للتصفح والتصدير فقط."
            )
            return
        if not self.selected_lesson_id:
            self.add_activity_button.setEnabled(False)
            self.add_activity_button.setToolTip("اختر حصة لإضافة نشاط.")
            return

        lesson_minutes, minutes_by_class, class_names = (
            self._activity_time_totals()
        )
        if lesson_minutes is None:
            self.add_activity_button.setEnabled(False)
            self.add_activity_button.setToolTip(
                "حدد مدة الحصة بالدقائق قبل إضافة الأنشطة."
            )
        elif minutes_by_class is None:
            self.add_activity_button.setEnabled(False)
            self.add_activity_button.setToolTip(
                "تعذر حساب المدد؛ صحح مدد الأنشطة لتكون بالدقائق."
            )
        elif all(
            minutes >= lesson_minutes
            for minutes in minutes_by_class.values()
        ):
            self.add_activity_button.setEnabled(False)
            self.add_activity_button.setToolTip(
                "اكتملت مدة الأنشطة لكل قسم؛ عدّل الأنشطة أو مدة الحصة."
            )
        else:
            self.add_activity_button.setEnabled(True)
            remaining_by_class = [
                f"«{class_names.get(class_id, str(class_id))}»: "
                f"{max(lesson_minutes - minutes, 0)} دقيقة"
                for class_id, minutes in minutes_by_class.items()
                if minutes < lesson_minutes
            ]
            self.add_activity_button.setToolTip(
                "الوقت المتبقي لإكمال مدة الحصة لكل قسم: "
                + "؛ ".join(remaining_by_class)
            )

    def on_lesson_selected(self):
        self.selected_lesson_id = self.current_id(self.lesson_table)
        self.selected_activity_id = None
        self.detail_cards.clear()
        self.refresh_activities(select_id=False)

    def on_lesson_card_selection_changed(self):
        selected_ids = self.recorded_lesson_cards.selected_lesson_ids()
        current_item = self.recorded_lesson_cards.currentItem()
        candidate_id = (
            int(current_item.data(Qt.UserRole))
            if current_item is not None
            and current_item.data(Qt.UserRole) is not None
            else None
        )
        current_id = (
            candidate_id if candidate_id in selected_ids
            else (selected_ids[-1] if selected_ids else None)
        )
        row_by_id = {
            int(self.lesson_table.item(row, 0).text()): row
            for row in range(self.lesson_table.rowCount())
            if self.lesson_table.item(row, 0) is not None
        }
        self.lesson_table.blockSignals(True)
        self.lesson_table.clearSelection()
        for lesson_id in selected_ids:
            row = row_by_id.get(lesson_id)
            if row is not None:
                self.lesson_table.selectRow(row)
        current_row = row_by_id.get(current_id)
        if current_row is not None:
            self.lesson_table.setCurrentCell(current_row, 0)
        else:
            self.lesson_table.setCurrentCell(-1, -1)
        self.lesson_table.blockSignals(False)
        self.on_lesson_selected()

    def on_lesson_card_action(self, action, lesson_id):
        lesson_row = next(
            (
                row for row in range(self.lesson_table.rowCount())
                if self.lesson_table.item(row, 0) is not None
                and int(self.lesson_table.item(row, 0).text()) == lesson_id
            ),
            None,
        )
        if lesson_row is None:
            QMessageBox.warning(
                self, "الحصة غير موجودة",
                "تعذر العثور على الحصة لتنفيذ الإجراء المطلوب.",
            )
            return

        self.lesson_table.blockSignals(True)
        self.lesson_table.clearSelection()
        self.lesson_table.setCurrentCell(lesson_row, 0)
        self.lesson_table.selectRow(lesson_row)
        self.lesson_table.blockSignals(False)
        self.recorded_lesson_cards.blockSignals(True)
        self.recorded_lesson_cards.select_lesson(lesson_id)
        self.recorded_lesson_cards.blockSignals(False)
        self.on_lesson_selected()

        if action == "edit":
            self.edit_lesson(lesson_id)
        elif action == "delete":
            self.delete_lesson(lesson_id)
        elif action == "copy":
            self.copy_selected_lessons([lesson_id])

    def on_activity_selected(self):
        self.selected_activity_id = self.current_id(self.activity_cards)
        self.refresh_details()

    def on_activity_card_action(self, action, activity_id):
        for row in range(self.activity_cards.count()):
            item = self.activity_cards.item(row)
            if int(item.data(Qt.UserRole)) != activity_id:
                continue
            self.activity_cards.setCurrentItem(item)
            break
        if action == "edit":
            self.edit_activity(activity_id)
        elif action == "delete":
            self.delete_activity(activity_id)

    def on_detail_card_action(self, action, detail_id):
        for row in range(self.detail_cards.count()):
            item = self.detail_cards.item(row)
            if int(item.data(Qt.UserRole)) != detail_id:
                continue
            self.detail_cards.setCurrentItem(item)
            break
        if action == "edit":
            self.edit_detail(detail_id)
        elif action == "delete":
            self.delete_detail(detail_id)

    def refresh_details(self, select_id=None):
        if not self.selected_activity_id:
            self.detail_cards.clear()
            self._refresh_completion_colors()
            return
        self.detail_cards.set_details(
            self.db.details(self.selected_activity_id), select_id
        )
        self._refresh_completion_colors()

    def _refresh_completion_colors(self):
        self._refresh_activity_completion_colors()
        self._refresh_lesson_completion_colors()

    def _prepare_repeat_selection(self, lesson, used_request_ids):
        lesson_data = {
            "classe": lesson[0],
            "majal": lesson[1],
            "heure": lesson[2],
            "time": lesson[3],
        }
        requests = self.db.lesson_repeat_requests_for_match(
            lesson_data, self.day_id
        )
        request = next(
            (
                candidate for candidate in requests
                if candidate["id"] not in used_request_ids
            ),
            None,
        )
        if request is None:
            return None
        used_request_ids.add(request["id"])

        target_minutes = duration_minutes(lesson[3])
        source_minutes = request["duration_minutes"]
        activities = request["activities"]
        if target_minutes is None or source_minutes is None or not activities:
            QMessageBox.warning(
                self,
                "تعذر إعداد إعادة الحصة",
                "تعذر تحديد مدة الحصة أو أنشطتها؛ أضيفت الحصة دون نسخ "
                "أنشطة الإعادة.",
            )
            return None

        activity_minutes = [
            duration_minutes(activity[2]) for activity in activities
        ]
        if target_minutes == source_minutes and all(
            minutes is not None for minutes in activity_minutes
        ) and sum(activity_minutes) <= target_minutes:
            activity_names = "\n".join(
                f"• {title} ({duration})"
                for _activity_id, title, duration in activities
            )
            answer = QMessageBox.question(
                self,
                "تأكيد إعادة الحصة كاملة",
                "مدة الحصة القادمة مساوية لمدة الحصة المطلوب إعادتها. "
                "هل توافق على إعادة جميع أنشطتها؟\n\n"
                + activity_names,
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            selected_ids = (
                [activity[0] for activity in activities]
                if answer == QMessageBox.StandardButton.Yes else []
            )
        elif target_minutes > source_minutes:
            dialog = RepeatActivitiesSelectionDialog(
                activities, target_minutes, self
            )
            if not dialog.exec():
                return None
            selected_ids = dialog.selected_activity_ids()
        else:
            selected_ids = []
            selected_minutes = 0
            for activity, minutes in zip(activities, activity_minutes):
                if minutes is None or selected_minutes + minutes > target_minutes:
                    break
                selected_ids.append(activity[0])
                selected_minutes += minutes
            if not selected_ids:
                QMessageBox.information(
                    self,
                    "تعذر إعادة نشاط",
                    "لا توجد أنشطة متتالية من الحصة الأصلية تلائم مدة "
                    "الحصة القادمة؛ بقيت أنشطة الإعادة معلقة.",
                )
                return None
            remaining_count = len(activities) - len(selected_ids)
            answer = QMessageBox.question(
                self,
                "تأكيد إعادة جزء من الحصة",
                f"ستُنسخ الأنشطة الأولى التي تلائم مدة الحصة "
                f"({selected_minutes} من {target_minutes} دقيقة)، "
                f"وتبقى {remaining_count} من الأنشطة لإكمالها لاحقًا. "
                "هل توافق؟",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None

        if not selected_ids:
            return None
        return {
            "request_id": request["id"],
            "activity_ids": selected_ids,
        }

    def add_lesson(self):
        if not self.ensure_school_year_writable():
            return
        if getattr(self, "_lesson_history_thread", None) is not None:
            return
        try:
            if not self._has_free_timetable_time():
                QMessageBox.information(
                    self, "لا توجد فترة شاغرة",
                    "امتلأت ساعات العمل المحددة في جدول المعلم؛ "
                    "لا يمكن إضافة حصة جديدة.",
                )
                return
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self, "تعذر التحقق من ساعات العمل",
                f"تعذر تحديد إمكانية إضافة حصة:\n{exc}",
            )
            return

        self._start_lesson_history_load(
            self._open_lesson_entry_dialog,
            self.lesson_table.rowCount(),
        )

    def _select_monthly_club_session(
        self, lesson_values, scheduled_club_name=None
    ):
        club_loader = getattr(self.db, "cultural_clubs", None)
        plans_loader = getattr(
            self.db, "cultural_club_monthly_plans", None
        )
        if not callable(club_loader) or not callable(plans_loader):
            return None, None, False

        class_name = str(lesson_values[0] or "").strip()
        domain = str(lesson_values[1] or "").strip().casefold()
        clubs = club_loader(self.db.year_id)
        club = next((
            candidate
            for candidate in clubs
            if str(candidate.get("club_type") or "").strip().casefold()
            == domain
            and (
                not scheduled_club_name
                or str(candidate.get("name") or "").strip().casefold()
                == str(scheduled_club_name).strip().casefold()
            )
            and (
                bool(scheduled_club_name)
                or class_name.casefold() in {
                    str(section.get("section_name") or "").strip().casefold()
                    for section in candidate.get("sections", [])
                }
            )
        ), None)
        if club is None:
            return None, None, False

        work_month = self.date_edit.date().toString("yyyy-MM")
        plan = next((
            candidate
            for candidate in plans_loader(self.db.year_id)
            if candidate.get("club_id") == club["id"]
            and candidate.get("month") == work_month
        ), None)
        if plan is None:
            return club, None, False

        sessions = plan.get("sessions", [])
        if not sessions:
            return club, None, False

        selection_dialog = MonthlyClubSessionSelectionDialog(
            sessions,
            plan.get("month", work_month),
            lesson_values[5] if len(lesson_values) > 5 else None,
            self,
        )
        if not selection_dialog.exec():
            return club, None, True
        session_number, session = selection_dialog.selected_session()
        if session is None:
            return club, None, True
        if selection_dialog.selected_action() == "edit":
            details_dialog = MonthlyClubSessionDetailsDialog(
                self.db,
                club["id"],
                session,
                session_number,
                len(sessions),
                plan.get("month", work_month),
                self,
            )
            if not details_dialog.exec():
                return club, None, True
            session = dict(session)
            session["properties"] = details_dialog.values()
        return club, session, False

    def _monthly_club_session_count(self, lesson):
        if not _is_cultural_club_lesson(lesson):
            return None
        clubs_loader = getattr(self.db, "cultural_clubs", None)
        plans_loader = getattr(
            self.db, "cultural_club_monthly_plans", None
        )
        if not callable(clubs_loader) or not callable(plans_loader):
            return None

        club_name = str(
            lesson[5] if len(lesson) > 5 and lesson[5] else lesson[0] or ""
        ).strip().casefold()
        section_name = str(lesson[0] or "").strip().casefold()
        club_type = str(lesson[1] or "").strip().casefold()
        club = next((
            candidate
            for candidate in clubs_loader(self.db.year_id)
            if str(candidate.get("club_type") or "").strip().casefold()
            == club_type
            and (
                str(candidate.get("name") or "").strip().casefold()
                == club_name
                or section_name in {
                    str(section.get("section_name") or "").strip().casefold()
                    for section in candidate.get("sections", [])
                }
            )
        ), None)
        if club is None:
            return None

        month = self.date_edit.date().toString("yyyy-MM")
        plan = next((
            candidate
            for candidate in plans_loader(self.db.year_id)
            if candidate.get("club_id") == club["id"]
            and candidate.get("month") == month
        ), None)
        return len(plan.get("sessions", [])) if plan else None

    def _save_monthly_club_session_activity(
        self, club, session, lesson_id, lesson_values
    ):
        class_name = str(lesson_values[0] or "").strip().casefold()
        class_id = next((
            member_id
            for member_id, member_name, _level_name
            in self.db.lesson_classes(lesson_id)
            if str(member_name or "").strip().casefold() == class_name
        ), None)
        existing_activity = next((
            activity for activity in self.db.activities(lesson_id)
            if str(activity[1] or "").strip().casefold()
            == str(club["name"] or "").strip().casefold()
        ), None) if callable(getattr(self.db, "activities", None)) else None
        activity_id = (
            existing_activity[0]
            if existing_activity is not None
            else self.db.save_activity(
                club["name"],
                lesson_values[3],
                lesson_id,
                class_id=class_id,
            )
        )
        for prop in session.get("properties", []):
            key_name = str(prop.get("key_name") or "").strip()
            value_text = str(prop.get("value_text") or "").strip()
            if key_name and value_text:
                self.db.save_detail(key_name, value_text, activity_id)
        return activity_id

    def _start_lesson_history_load(
        self, result_handler, existing_count, generate_defaults=True
    ):
        if getattr(self, "_lesson_history_thread", None) is not None:
            return
        waiting_text = "في انتظار توليد البيانات ..."
        self.lesson_loading_label.setText(waiting_text)
        self.lesson_loading_label.show()
        self.scheduled_lessons_list.setEnabled(False)
        self.scheduled_exam_lessons_list.setEnabled(False)
        self.date_edit.setEnabled(False)

        self._lesson_history_thread = QThread(self)
        self._lesson_history_worker = LessonHistoryLoadWorker(
            self.db.path,
            self.date_edit.date().dayOfWeek() - 1,
            existing_count,
            generate_defaults,
        )
        self._lesson_history_worker.moveToThread(self._lesson_history_thread)
        self._lesson_history_thread.started.connect(
            self._lesson_history_worker.run, Qt.QueuedConnection
        )
        self._lesson_history_worker.result_ready.connect(result_handler)
        self._lesson_history_worker.failed.connect(self._lesson_history_failed)
        self._lesson_history_worker.finished.connect(
            self._lesson_history_thread.quit
        )
        self._lesson_history_worker.finished.connect(
            self._lesson_history_worker.deleteLater
        )
        self._lesson_history_thread.finished.connect(
            self._lesson_history_thread_finished
        )
        self._lesson_history_thread.start()

    @Slot(object, object)
    def _open_lesson_entry_dialog(self, df_history, predicted):
        if not self.ensure_school_year_writable():
            return
        def_hessa_num = max(1, self.lesson_table.rowCount() + 1)
        default_vals = ["", "", "08:00-09:00", "60 دقيقة", 1, def_hessa_num, "منهجي"]
        if predicted:
            default_vals[0] = predicted.get("classe", "")
            default_vals[1] = predicted.get("majal", "")
            default_vals[2] = predicted.get("heure", "08:00-09:00")
            default_vals[3] = predicted.get("time", "60 دقيقة")
            default_vals[4] = predicted.get("wehda", 1)
            default_vals[5] = def_hessa_num
            default_vals[6] = predicted.get("namat", "منهجي")
        try:
            existing_lessons = (
                self.db.lessons(self.day_id) if self.day_id else []
            )
            existing_lessons = SchoolPlanner._include_cultural_club_sessions(
                self, existing_lessons
            )
            work_bounds = self._teacher_work_bounds()
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self,
                "تعذر قراءة جدول الأوقات",
                f"تعذر تحديد فترة شاغرة من جدول الأوقات:\n{error}",
            )
            return

        try:
            free_intervals = _unoccupied_work_intervals(
                existing_lessons, *work_bounds
            )
        except ValueError as error:
            QMessageBox.critical(
                self,
                "توقيت حصة غير صالح",
                f"تعذر تحديد الفترات المتاحة:\n{error}",
            )
            return
        available_hours = []
        for gap_start, gap_end in free_intervals:
            first_full_hour = ((gap_start + 59) // 60) * 60
            for start_minute in range(first_full_hour, gap_end, 60):
                end_minute = start_minute + 60
                if end_minute > gap_end:
                    continue
                start_text = (
                    f"{start_minute // 60:02d}:"
                    f"{start_minute % 60:02d}"
                )
                end_text = (
                    f"{end_minute // 60:02d}:"
                    f"{end_minute % 60:02d}"
                )
                available_hours.append(
                    f"{start_text}-{end_text}"
                )
        if not available_hours:
            QMessageBox.information(
                self,
                "لا توجد فترة شاغرة",
                "لا توجد فترة متصلة مدتها 30 دقيقة على الأقل لإضافة حصة.",
            )
            return
        default_vals[2] = available_hours[0]
        start, end = _parse_hour_interval(default_vals[2])
        default_vals[3] = f"{end - start} دقيقة"

        dlg = LessonEntryDialog(
            "إضافة حصة", df_history, default_values=default_vals,
            parent=self,
            db=self.db,
            available_hours=available_hours,
            reserved_hours=[],
            work_bounds=work_bounds,
        )
        if dlg.exec():
            v = dlg.values()
            if not v[0] or not v[1]:
                QMessageBox.warning(self, "بيانات ناقصة", "يرجى إدخال القسم والمجال / المادة.")
                return
            try:
                existing_lessons = self.db.lessons(self.day_id)
                if not self._validate_new_lesson_intervals(
                    [v], existing_lessons
                ):
                    QMessageBox.warning(
                        self, "التوقيت غير متاح",
                        "التوقيت يتداخل مع حصة أخرى أو يقع خارج ساعات العمل "
                        "المتاحة في جدول المعلم.",
                    )
                    return
                repeat_selection = self._prepare_repeat_selection(v, set())
                club, monthly_session, selection_cancelled = (
                    self._select_monthly_club_session(v)
                )
                if selection_cancelled:
                    return
                if club is not None:
                    v = list(v)
                    v[5] = self.db.next_cultural_club_lesson_number(
                        self.db.year_id, club["id"], v[0]
                    )
                new_id = self.db.save_lesson(
                    v,
                    self.day_id,
                    repeat_selection=repeat_selection,
                )
                activity_id = None
                if monthly_session is not None:
                    activity_id = self._save_monthly_club_session_activity(
                        club, monthly_session, new_id, v
                    )
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(
                    self, "تعذر حفظ الحصة", f"حدث خطأ أثناء حفظ الحصة:\n{exc}"
                )
                return
            self.refresh_lessons(
                select_id=new_id if activity_id is not None else None,
                select_first=False,
            )
            if activity_id is not None:
                self.refresh_activities(select_id=activity_id)

    @Slot(str)
    def _lesson_history_failed(self, message):
        self.lesson_loading_label.setText(message)
        self.lesson_loading_label.show()
        QMessageBox.critical(self, "تعذر تحميل الحصص السابقة", message)

    @Slot()
    def _lesson_history_thread_finished(self):
        thread = self._lesson_history_thread
        self._lesson_history_worker = None
        self._lesson_history_thread = None
        if thread is not None:
            thread.deleteLater()
        self.date_edit.setEnabled(True)
        if not self.lesson_loading_label.text().startswith("تعذر"):
            self.lesson_loading_label.hide()
        self.scheduled_lessons_list.setEnabled(
            not self.is_school_year_read_only
        )
        self.scheduled_exam_lessons_list.setEnabled(
            not self.is_school_year_read_only
        )

    def add_all_lessons(self):
        if not self.ensure_school_year_writable():
            return
        lessons = []
        for scheduled_list in (
            self.scheduled_lessons_list,
            self.scheduled_club_lessons_list,
            self.scheduled_exam_lessons_list,
        ):
            for row in range(scheduled_list.count()):
                lesson = scheduled_list.item(row).data(
                    Qt.ItemDataRole.UserRole
                )
                if isinstance(lesson, (tuple, list)):
                    lessons.append(lesson)

        if not lessons:
            QMessageBox.information(
                self, "لا توجد حصص مسجلة",
                "لا توجد حصص مجدولة لإضافتها لهذا اليوم."
            )
            return
        self.add_scheduled_lessons(lessons)

    def _add_scheduled_exam_from_card(self, item):
        lesson = item.data(Qt.ItemDataRole.UserRole)
        if (
            not isinstance(lesson, (tuple, list))
            or len(lesson) < 8
            or lesson[6] != "scheduled_exam"
        ):
            return
        self.add_scheduled_lessons([lesson])

    def add_scheduled_lessons(self, lessons):
        if not self.ensure_school_year_writable():
            return
        scheduled_exam_lessons = [
            lesson for lesson in lessons
            if (
                len(lesson) > 7
                and lesson[6] == "scheduled_exam"
            )
        ]
        lessons = [
            lesson for lesson in lessons
            if not (
                len(lesson) > 7
                and lesson[6] == "scheduled_exam"
            )
        ]
        added_exam_lesson_ids = []
        if scheduled_exam_lessons:
            target_day = self.date_edit.date().toString("yyyy-MM-dd")
            try:
                for lesson in scheduled_exam_lessons:
                    added_exam_lesson_ids.extend(
                        self.db.sync_exam_diary_lesson(
                            target_day, int(lesson[7])
                        )
                    )
            except (sqlite3.Error, ValueError, TypeError) as error:
                if added_exam_lesson_ids:
                    self.refresh_lessons(
                        select_id=added_exam_lesson_ids[0]
                    )
                QMessageBox.critical(
                    self,
                    "تعذر إضافة حصة التقييم",
                    f"تعذر إضافة التقييم المبرمج إلى دفتر اليوم:\n{error}",
                )
                return
            if not lessons:
                self.refresh_lessons(
                    select_id=(
                        added_exam_lesson_ids[0]
                        if added_exam_lesson_ids else None
                    )
                )
                if added_exam_lesson_ids:
                    self.statusBar().showMessage(
                        f"تمت إضافة {len(added_exam_lesson_ids)} "
                        "حصة تقييم مبرمجة إلى دفتر اليوم.",
                        3000,
                    )
                else:
                    QMessageBox.information(
                        self, "حصص التقييم موجودة",
                        "حصص التقييم المحددة مضافة بالفعل إلى دفتر اليوم.",
                    )
                return

        existing_rows = self.db.lessons(self.day_id)
        existing_ids = {row[0] for row in existing_rows}
        existing_keys = {
            (str(row[2] or "").strip(), str(row[3] or "").strip(),
             str(row[4] or "").strip(), str(row[5] or "").strip())
            for row in existing_rows
        }
        seen_keys = set()
        new_lessons = []
        for lesson in lessons:
            if (
                len(lesson) > 7
                and lesson[6] == "cultural_club"
                and isinstance(lesson[7], list)
            ):
                missing_classes = []
                for class_name in lesson[7]:
                    key = (
                        str(class_name or "").strip(),
                        str(lesson[1] or "").strip(),
                        str(lesson[2] or "").strip(),
                        str(lesson[3] or "").strip(),
                    )
                    if key not in existing_keys and key not in seen_keys:
                        missing_classes.append(class_name)
                        seen_keys.add(key)
                if missing_classes:
                    new_lessons.append((
                        *lesson[:7], missing_classes
                    ))
                continue
            key = tuple(
                str(value or "").strip() for value in lesson[:4]
            )
            if key not in existing_keys and key not in seen_keys:
                new_lessons.append(lesson)
                seen_keys.add(key)

        if not new_lessons:
            if added_exam_lesson_ids:
                self.refresh_lessons(
                    select_id=added_exam_lesson_ids[0]
                )
                self.statusBar().showMessage(
                    f"تمت إضافة {len(added_exam_lesson_ids)} "
                    "حصة تقييم مبرمجة؛ أما الحصص الأخرى فكانت مضافة.",
                    3000,
                )
                return
            QMessageBox.information(
                self, "الحصص موجودة",
                "جميع الحصص المسجلة لهذا اليوم مضافة بالفعل."
            )
            return

        try:
            if not self._validate_new_lesson_intervals(
                new_lessons, existing_rows
            ):
                QMessageBox.warning(
                    self, "التوقيت غير متاح",
                    "توجد حصة في توقيت محجوز أو خارج ساعات العمل، "
                    "ولا يمكن إضافة الحصص المحددة.",
                )
                return
        except ValueError as exc:
            QMessageBox.critical(
                self, "توقيت غير صالح",
                f"تعذر التحقق من توقيت الحصة:\n{exc}",
            )
            return

        target_date = self.date_edit.date().toString("yyyy-MM-dd")
        future_number_keys = {}
        try:
            for lesson in new_lessons:
                key = (
                    str(lesson[0] or "").strip(),
                    str(lesson[1] or "").strip(),
                )
                if key not in future_number_keys:
                    future_number_keys[key] = self.db.future_lesson_dates(
                        *key, target_date
                    )
        except (sqlite3.Error, ValueError) as e:
            QMessageBox.critical(
                self,
                "تعذر التحقق من الحصص المستقبلية",
                f"تعذر التحقق من وجود حصص لاحقة:\n{e}",
            )
            return

        future_number_keys = {
            key: dates for key, dates in future_number_keys.items() if dates
        }
        if future_number_keys:
            future_descriptions = "\n".join(
                f"• {classe} — {majal}: {', '.join(dates)}"
                for (classe, majal), dates in future_number_keys.items()
            )
            QMessageBox.warning(
                self,
                "توجد حصص بتاريخ لاحق",
                "توجد حصص مسجلة لهذا القسم والمجال في تواريخ لاحقة:\n"
                f"{future_descriptions}\n\n"
                "لن يتم احتساب رقم الوحدة أو رقم الحصة تلقائيًا "
                "لهذه الحصص. يرجى إدخالهما يدويًا.",
            )

        number_defaults = {}
        repeat_number_defaults = {}
        try:
            number_request_ids = set()
            for lesson in new_lessons:
                classe, majal = lesson[:2]
                key = (str(classe or "").strip(), str(majal or "").strip())
                if key not in number_defaults:
                    number_defaults[key] = (
                        (1, 1)
                        if key in future_number_keys
                        else self.db.lesson_number_defaults(*key)
                    )
                requests = self.db.lesson_repeat_requests_for_match(
                    {
                        "classe": lesson[0],
                        "majal": lesson[1],
                        "heure": lesson[2],
                        "time": lesson[3],
                    },
                    self.day_id,
                )
                request = next(
                    (
                        candidate for candidate in requests
                        if candidate["id"] not in number_request_ids
                    ),
                    None,
                )
                if request is not None:
                    number_request_ids.add(request["id"])
                    repeat_number_defaults[
                        tuple(str(value or "").strip() for value in lesson[:3])
                    ] = (
                        request["unit_number"], request["lesson_number"]
                    )
        except (sqlite3.Error, ValueError) as e:
            QMessageBox.critical(
                self, "خطأ",
                f"تعذر تحميل أرقام الحصص أو طلبات الإعادة: {e}"
            )
            return

        dlg = BulkLessonEntryDialog(
            new_lessons,
            number_defaults,
            self,
            repeat_number_defaults=repeat_number_defaults,
            learning_mode_resolver=lambda lesson, unit, number: (
                self.db.teaching_plan_learning_mode(
                    lesson[0], lesson[1], unit, number, self.day_id
                )
            ),
            plan_lesson_count_resolver=lambda lesson, unit: (
                self._monthly_club_session_count(lesson)
                if _is_cultural_club_lesson(lesson)
                else self.db.teaching_plan_lesson_count(
                    lesson[0], lesson[1], unit, self.day_id
                )
            ),
            assigned_activity_resolver=lambda lesson: (
                self.db.teaching_assignment_activities(
                    lesson[0], lesson[1]
                )
            ),
            manual_number_keys=future_number_keys.keys(),
        )
        if not dlg.exec():
            return

        values = dlg.values()
        if any(not lesson[0] or not lesson[1] for lesson in values):
            QMessageBox.warning(self, "بيانات ناقصة", "تعذر إضافة حصة لا تحتوي على القسم والمجال.")
            return

        try:
            if not self._validate_new_lesson_intervals(
                values, existing_rows
            ):
                QMessageBox.warning(
                    self, "التوقيت غير متاح",
                    "تغيّر التوقيت إلى فترة محجوزة أو خارج ساعات العمل.",
                )
                return
            used_request_ids = set()
            repeat_selections = {}
            lesson_indexes = []
            for lesson_index, lesson in enumerate(values):
                is_scheduled_club = (
                    len(lesson) > 9
                    and isinstance(lesson[9], list)
                    and str(lesson[8] or "").strip()
                )
                if is_scheduled_club:
                    continue
                lesson_indexes.append(lesson_index)
                selection = self._prepare_repeat_selection(
                    lesson, used_request_ids
                )
                if selection is not None:
                    repeat_selections[lesson_index] = selection
            selected_sessions_by_club = {}
            monthly_sessions = []
            for lesson_index, lesson in enumerate(values):
                scheduled_club_name = (
                    str(lesson[8] or "").strip()
                    if len(lesson) > 8 else ""
                )
                if not scheduled_club_name:
                    monthly_sessions.append(None)
                    continue
                club_key = (
                    scheduled_club_name.casefold(),
                    str(lesson[1] or "").strip().casefold(),
                )
                if club_key not in selected_sessions_by_club:
                    club, session, cancelled = (
                        self._select_monthly_club_session(
                            lesson, scheduled_club_name
                        )
                    )
                    if cancelled:
                        return
                    selected_sessions_by_club[club_key] = (
                        (club, session)
                        if club is not None
                        else None
                    )
                session_data = selected_sessions_by_club[club_key]
                monthly_sessions.append(session_data)
                if session_data is not None:
                    club, _session = session_data
                    if not (
                        len(lesson) > 9 and isinstance(lesson[9], list)
                    ):
                        lesson_values = list(lesson)
                        lesson_values[5] = (
                            self.db.next_cultural_club_lesson_number(
                                self.db.year_id, club["id"], lesson_values[0]
                            )
                        )
                        values[lesson_index] = tuple(lesson_values)

            saved_lesson_ids = self.db.save_lessons(
                [values[index] for index in lesson_indexes],
                self.day_id,
                repeat_selections={
                    lesson_indexes.index(index): selection
                    for index, selection in repeat_selections.items()
                },
            )
            selected_club_activity = None
            for lesson_index, lesson in enumerate(values):
                session_data = monthly_sessions[lesson_index]
                scheduled_club = (
                    len(lesson) > 9
                    and isinstance(lesson[9], list)
                    and str(lesson[8] or "").strip()
                )
                if scheduled_club:
                    if session_data is None:
                        raise ValueError(
                            f"النادي «{lesson[8]}» غير مسجل في السنة الدراسية."
                        )
                    club, session = session_data
                    self.db.save_cultural_club_daily_session(
                        self.db.year_id,
                        club["id"],
                        target_date,
                        lesson[2],
                        duration_minutes(lesson[3]),
                        properties=(
                            session.get("properties", [])
                            if session is not None else None
                        ),
                        monthly_session_id=(
                            session.get("id") if session is not None else None
                        ),
                    )
                    continue
                if lesson_index not in lesson_indexes:
                    continue
                saved_lesson_id = saved_lesson_ids[
                    lesson_indexes.index(lesson_index)
                ]
                if session_data is None or session_data[1] is None:
                    continue
                club, session = session_data
                activity_id = self._save_monthly_club_session_activity(
                    club, session, saved_lesson_id, lesson
                )
                selected_club_activity = (
                    saved_lesson_id, activity_id
                )
        except (sqlite3.Error, ValueError) as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء إضافة الحصص: {e}")
            return

        self.refresh_lessons(
            select_id=(
                selected_club_activity[0]
                if selected_club_activity is not None else None
            ),
            select_first=False,
        )
        if selected_club_activity is not None:
            self.refresh_activities(
                select_id=selected_club_activity[1]
            )
        added_count = len(values) + len(added_exam_lesson_ids)
        self.statusBar().showMessage(
            f"تمت إضافة {added_count} حصة بنجاح.", 3000
        )

    def edit_lesson(self, lesson_id=None):
        if not self.ensure_school_year_writable():
            return
        if getattr(self, "_lesson_history_thread", None) is not None:
            return
        lid = lesson_id or self.current_id(self.lesson_table)
        if not lid:
            return self.warn_select("حصة")
        try:
            row = self.db.lesson(lid)
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "تعذر تحميل الحصة", str(exc))
            return
        if row is None:
            QMessageBox.warning(self, "تعذر تحميل الحصة", "لم تعد الحصة موجودة.")
            return

        existing_request = self.db.lesson_repeat_request(lid)
        repeat_requested = bool(
            existing_request
            and existing_request.get("repeat_for_next_session")
            and existing_request.get("confirmed_by_user")
            and not existing_request.get("is_applied")
        )
        dialog = LessonScheduleEditDialog(
            row[3], row[5], row[6], self,
            repeat_reason=(existing_request or {}).get("reason", ""),
            repeat_requested=repeat_requested,
        )
        if not dialog.exec():
            return
        hour_interval, unit_number, lesson_number, repeat_requested, repeat_reason = dialog.values()
        try:
            start, end = _parse_hour_interval(hour_interval)
            original_duration = duration_minutes(row[4])
            if (
                original_duration is not None
                and end - start != original_duration
            ):
                QMessageBox.warning(
                    self, "مدة غير مطابقة",
                    "يجب أن يحافظ التوقيت الجديد على مدة الحصة الأصلية.",
                )
                return
            existing_lessons = self.db.lessons(self.day_id)
            work_bounds = self._teacher_work_bounds()
            if not _hour_interval_is_available(
                hour_interval,
                existing_lessons,
                work_bounds,
                excluded_lesson_id=lid,
            ):
                QMessageBox.warning(
                    self, "التوقيت محجوز",
                    "لا يمكن نقل الحصة إلى فترة تتداخل مع حصة أخرى "
                    "أو تقع خارج ساعات العمل.",
                )
                return
            self.db.update_lesson_schedule(
                lid, hour_interval, unit_number, lesson_number
            )
            if repeat_requested:
                self.db.set_lesson_repeat_request(
                    lid,
                    repeat_reason,
                    repeat_for_next_session=True,
                    confirmed_by_user=True,
                    matched_interval=hour_interval,
                    duration_minutes=original_duration,
                )
            else:
                self.db.cancel_lesson_repeat_request(lid)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self, "تعذر تعديل الحصة",
                f"حدث خطأ أثناء تعديل توقيت الحصة أو أرقامها:\n{exc}",
            )
            return
        self.refresh_lessons(lid)

    def delete_lesson(self, lesson_id=None):
        if not self.ensure_school_year_writable():
            return
        lid = lesson_id or self.current_id(self.lesson_table)
        if not lid:
            return self.warn_select("حصة")
        if self.confirm("حذف الحصة المحددة وكل أنشطتها وخصائصها؟"):
            self.db.delete_lesson(lid)
            self.selected_lesson_id = None
            self.refresh_lessons()
            self.activity_cards.clear()
            self.detail_cards.clear()

    def copy_selected_lessons(self, lesson_ids=None):
        if lesson_ids is None:
            lesson_ids = [
                int(self.lesson_table.item(index.row(), 0).text())
                for index in self.lesson_table.selectionModel().selectedRows()
                if self.lesson_table.item(index.row(), 0) is not None
            ]
        if not lesson_ids:
            return self.warn_select("حصة واحدة على الأقل لنسخها")
        
        self.copied_lessons = []
        for lesson_id in lesson_ids:
            lesson_row = self.db.lesson(lesson_id)
            if not lesson_row:
                continue
            
            lesson_data = {
                "classe": lesson_row[1],
                "classe_level_id": lesson_row[9],
                "majal": lesson_row[2],
                "heure": lesson_row[3],
                "time": lesson_row[4],
                "wehda_number": lesson_row[5],
                "hessa_number": lesson_row[6],
                "namat_taallom": lesson_row[7],
                "activities": []
            }
            
            for act in self.db.activities(lesson_id):
                act_id, act_title, act_time = act[0], act[1], act[2]
                details = self.db.details(act_id)
                act_data = {
                    "title": act_title,
                    "time": act_time,
                    "classe": next(
                        (
                            class_name
                            for class_id, class_name, _level
                            in self.db.lesson_classes(lesson_id)
                            if class_id
                            == self.db.activity_class_id(act_id)
                        ),
                        "",
                    ),
                    "details": [(d[1], d[2]) for d in details]
                }
                lesson_data["activities"].append(act_data)
                
            self.copied_lessons.append(lesson_data)
        self.update_paste_lessons_button_state()
        self.statusBar().showMessage(f"تم نسخ {len(self.copied_lessons)} حصة بنجاح.", 3000)

    def update_paste_lessons_button_state(self):
        button = getattr(self, "paste_lessons_button", None)
        if button is not None:
            button.setEnabled(
                bool(self.copied_lessons)
                and not self.is_school_year_read_only
            )

    def paste_lessons(self):
        if not self.ensure_school_year_writable():
            return
        if not self.copied_lessons:
            QMessageBox.warning(self, "تنبيه", "لا توجد حصص منسوخة حالياً.")
            return
        if not self.day_id:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد اليوم المراد لصق الحصص فيه.")
            return

        try:
            existing_lessons = self.db.lessons(self.day_id)
            pasted_lessons = [
                (
                    lesson["classe"],
                    lesson["majal"],
                    lesson["heure"],
                    lesson["time"],
                )
                for lesson in self.copied_lessons
            ]
            if not self._validate_new_lesson_intervals(
                pasted_lessons, existing_lessons
            ):
                QMessageBox.warning(
                    self, "التوقيت غير متاح",
                    "لا يمكن لصق الحصص لأن أحد توقيتاتها يتداخل مع حصة "
                    "أخرى أو يقع خارج ساعات العمل.",
                )
                return
        except (sqlite3.Error, ValueError, KeyError) as exc:
            QMessageBox.critical(
                self, "تعذر التحقق من توقيت الحصص",
                f"حدث خطأ أثناء التحقق من الحصص المراد لصقها:\n{exc}",
            )
            return

        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                for les in self.copied_lessons:
                    classe_id, class_group_id, class_ids = (
                        self.db._resolve_lesson_class(
                        con, les["classe"], les["classe_level_id"]
                        )
                    )
                    majal_id, learning_mode_id = (
                        self.db.resolve_lesson_lookup_ids(
                            con, les["majal"], les["namat_taallom"]
                        )
                    )
                    cursor.execute("""
                        INSERT INTO hessa(
                            classe_id, majal_id, heure, time, wehda_number,
                            hessa_number, learning_mode_id, day_data_id,
                            class_group_id
                        )
                        VALUES(?,?,?,?,?,?,?,?,?)
                    """, (
                        classe_id, majal_id, les["heure"], les["time"],
                        les["wehda_number"], les["hessa_number"],
                        learning_mode_id, self.day_id, class_group_id
                    ))
                    new_hessa_id = cursor.lastrowid
                    self.db._replace_hessa_classes(
                        con, new_hessa_id, class_ids
                    )
                    
                    for act in les["activities"]:
                        activity_class_id = self.db.resolve_activity_class(
                            con, new_hessa_id, act.get("classe")
                        )
                        cursor.execute("""
                            INSERT INTO nachat(
                                title, time, hessa_id, classe_id
                            ) VALUES(?, ?, ?, ?)
                        """, (
                            act["title"], act["time"], new_hessa_id,
                            activity_class_id,
                        ))
                        new_nachat_id = cursor.lastrowid
                        
                        for detail in act["details"]:
                            cursor.execute("""
                                INSERT INTO nachat_detail(key_name, value_text, nachat_id) VALUES(?,?,?)
                            """, (detail[0], detail[1], new_nachat_id))
                con.commit()
                
            self.refresh_lessons()
            self.statusBar().showMessage("تم لصق الحصص المنسوخة بنجاح.", 3000)
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء لصق الحصص: {e}")

    def _current_lesson_context(self):
        if not self.selected_lesson_id:
            return "", "", None
        row = self.db.lesson(self.selected_lesson_id)
        if not row:
            return "", "", None
        return str(row[2] or ""), str(row[7] or ""), row[8]

    def add_activity(self):
        if not self.ensure_school_year_writable():
            return
        if not self.selected_lesson_id:
            return self.warn_select("حصة أولاً")
        majal, _namat, _day_data_id = self._current_lesson_context()
        weekday = self.date_edit.date().dayOfWeek() - 1
        dlg = ActivityEntryDialog(
            "إضافة نشاط", majal, self.db, weekday,
            parent=self, lesson_id=self.selected_lesson_id,
        )
        while dlg.exec():
            title, duration, class_id = dlg.values()
            if not title:
                return QMessageBox.warning(self, "بيانات ناقصة", "عنوان النشاط مطلوب.")
            duration_minutes = self._duration_minutes(duration)
            if duration_minutes is None:
                return QMessageBox.warning(
                    self, "مدة غير صالحة", "يرجى تحديد مدة النشاط بالدقائق."
                )
            lesson_minutes, activity_minutes = self._activity_time_budget(
                class_id=class_id
            )
            if lesson_minutes is None:
                return QMessageBox.warning(
                    self, "مدة الحصة غير صالحة",
                    "حدد مدة الحصة بالدقائق قبل إضافة نشاط."
                )
            if activity_minutes is None:
                return QMessageBox.warning(
                    self, "مدد أنشطة غير صالحة",
                    "تعذر حساب مجموع مدد الأنشطة؛ صحح مددها لتكون بالدقائق."
                )
            if activity_minutes + duration_minutes > lesson_minutes:
                remaining_minutes = max(lesson_minutes - activity_minutes, 0)
                QMessageBox.warning(
                    self, "تجاوز مدة الحصة",
                    f"مجموع مدد الأنشطة سيتجاوز مدة الحصة "
                    f"({lesson_minutes} دقيقة). غيّر مدة هذا النشاط إلى "
                    f"{remaining_minutes} دقيقة أو أقل."
                )
                dlg.time_combo.setFocus()
                continue
            aid = self.db.save_activity(
                title, duration, self.selected_lesson_id,
                class_id=class_id,
            )
            self.refresh_activities(aid)
            self._show_shared_activity_time_status()
            break

    def edit_activity(self, activity_id=None):
        if not self.ensure_school_year_writable():
            return
        aid = activity_id or self.current_id(self.activity_cards)
        if not aid:
            return self.warn_select("نشاط")
        majal, _namat, _day_data_id = self._current_lesson_context()
        row = next((x for x in self.db.activities(self.selected_lesson_id) if x[0] == aid), None)
        if not row:
            return
        weekday = self.date_edit.date().dayOfWeek() - 1
        dlg = ActivityEntryDialog("تعديل نشاط", majal, self.db, weekday,
                                  values=[
                                      row[1], row[2],
                                      self.db.activity_class_id(aid),
                                  ],
                                  parent=self,
                                  lesson_id=self.selected_lesson_id)
        while dlg.exec():
            title, duration, class_id = dlg.values()
            if not title:
                return QMessageBox.warning(self, "بيانات ناقصة", "عنوان النشاط مطلوب.")
            duration_minutes = self._duration_minutes(duration)
            if duration_minutes is None:
                return QMessageBox.warning(
                    self, "مدة غير صالحة", "يرجى تحديد مدة النشاط بالدقائق."
                )
            lesson_minutes, activity_minutes = self._activity_time_budget(
                exclude_activity_id=aid,
                class_id=class_id,
            )
            if lesson_minutes is None:
                return QMessageBox.warning(
                    self, "مدة الحصة غير صالحة",
                    "حدد مدة الحصة بالدقائق قبل تعديل النشاط."
                )
            if activity_minutes is None:
                return QMessageBox.warning(
                    self, "مدد أنشطة غير صالحة",
                    "تعذر حساب مجموع مدد الأنشطة؛ صحح مددها لتكون بالدقائق."
                )
            if activity_minutes + duration_minutes > lesson_minutes:
                remaining_minutes = max(lesson_minutes - activity_minutes, 0)
                QMessageBox.warning(
                    self, "تجاوز مدة الحصة",
                    f"مجموع مدد الأنشطة سيتجاوز مدة الحصة "
                    f"({lesson_minutes} دقيقة). غيّر مدة هذا النشاط إلى "
                    f"{remaining_minutes} دقيقة أو أقل."
                )
                dlg.time_combo.setFocus()
                continue
            self.db.save_activity(
                title, duration, self.selected_lesson_id, aid,
                class_id=class_id,
            )
            self.refresh_activities(aid)
            self._show_shared_activity_time_status()
            break

    def delete_activity(self, activity_id=None):
        if not self.ensure_school_year_writable():
            return
        aid = activity_id or self.current_id(self.activity_cards)
        if not aid:
            return self.warn_select("نشاط")
        if self.confirm("حذف النشاط المحدد وكل خصائصه؟"):
            self.db.delete_activity(aid)
            self.selected_activity_id = None
            self.refresh_activities()
            self._show_shared_activity_time_status()
            self.detail_cards.clear()

    def _detail_dialog_context(self):
        majal, namat, _day_data_id = self._current_lesson_context()
        activity_row = next((x for x in self.db.activities(self.selected_lesson_id or -1)
                             if x[0] == self.selected_activity_id), None)
        activity_title = activity_row[1] if activity_row else ""
        return namat, activity_title

    def add_detail(self):
        if not self.ensure_school_year_writable():
            return
        if not self.selected_activity_id:
            return self.warn_select("نشاط أولاً")
        namat, activity_title = self._detail_dialog_context()
        current_details = self.db.details(self.selected_activity_id)
        current_count = len(current_details)
        contextual_content = next(
            (
                str(detail[2] or "")
                for detail in current_details
                if str(detail[1] or "").strip() == "المحتوى"
            ),
            None,
        )
        dlg = DetailEntryDialog("إضافة خاصية للنشاط", namat, activity_title,
                                self.db, current_count=current_count,
                                parent=self,
                                contextual_content=contextual_content,
                                default_key=_default_detail_key(
                                    namat, current_details
                                ),
                                activity_id=self.selected_activity_id)
        if dlg.exec():
            key, value = dlg.values()
            if not key:
                return QMessageBox.warning(self, "بيانات ناقصة", "يرجى اختيار اسم الخاصية.")
            if any(d[1] == key for d in current_details):
                reply = QMessageBox.question(
                    self,
                    "تنبيه: خاصية موجودة مسبقاً",
                    f"اسم الخاصية '{key}' موجود مسبقاً لهذا النشاط.\nهل تريد متابعة الإضافة رغم ذلك؟",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            did = self.db.save_detail(key, value, self.selected_activity_id)
            self.refresh_details(did)

    def edit_detail(self, detail_id=None):
        if not self.ensure_school_year_writable():
            return
        did = detail_id or self.current_id(self.detail_cards)
        if not did:
            return self.warn_select("خاصية")
        current_details = self.db.details(self.selected_activity_id)
        row = next((x for x in current_details if x[0] == did), None)
        if not row:
            return
        namat, activity_title = self._detail_dialog_context()
        contextual_content = next(
            (
                str(detail[2] or "")
                for detail in current_details
                if str(detail[1] or "").strip() == "المحتوى"
            ),
            None,
        )
        dlg = DetailEntryDialog("تعديل خاصية", namat, activity_title, self.db,
                                values=[row[1], row[2]], parent=self,
                                contextual_content=contextual_content,
                                activity_id=self.selected_activity_id)
        if dlg.exec():
            key, value = dlg.values()
            if not key:
                return QMessageBox.warning(self, "بيانات ناقصة", "يرجى اختيار اسم الخاصية.")
            self.db.save_detail(key, value, self.selected_activity_id, did)
            self.refresh_details(did)

    def delete_detail(self, detail_id=None):
        if not self.ensure_school_year_writable():
            return
        did = detail_id or self.current_id(self.detail_cards)
        if not did:
            return self.warn_select("خاصية")
        if self.confirm("هل تريد حذف الخاصية المحددة؟"):
            self.db.delete_detail(did)
            self.refresh_details()

    def warn_select(self, what):
        QMessageBox.information(self, "تحديد مطلوب", f"يرجى تحديد {what} أولاً.")

    def confirm(self, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("تأكيد العملية")
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        btn_yes = msg_box.addButton("نعم", QMessageBox.AcceptRole)
        btn_yes.setProperty("actionType", "save")
        btn_no = msg_box.addButton("إلغاء", QMessageBox.RejectRole)
        btn_no.setProperty("actionType", "cancel")
        msg_box.exec()
        return msg_box.clickedButton() == btn_yes

    def export_pdf(self):
        selection_dialog = DaySelectionDialog(self.db, parent=self)
        if not selection_dialog.exec():
            return

        selected_date_text = selection_dialog.get_selected_date_str()
        try:
            day_id = self.db.recorded_day_id(selected_date_text)
            if not day_id:
                QMessageBox.information(
                    self,
                    "تنبيه",
                    f"لا توجد حصص مسجلة للتاريخ: {selected_date_text}",
                )
                return

            self.day_lessons_page.set_day(day_id, selected_date_text)
            self.day_lessons_page.export_pdf()
        except (sqlite3.Error, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                "تعذر تصدير PDF",
                f"حدث خطأ أثناء تحميل بيانات اليوم:\n{exc}",
            )

    def export_day_to_json(self):
        dlg = DaySelectionDialog(self.db, parent=self)
        if not dlg.exec():
            return

        selected_date_text = dlg.get_selected_date_str()
        try:
            day_id = self.db.recorded_day_id(selected_date_text)
        except sqlite3.Error as error:
            QMessageBox.critical(
                self, "تعذر تصدير اليوم",
                f"تعذر تحميل بيانات اليوم:\n{error}",
            )
            return
        if not day_id:
            QMessageBox.information(
                self, "تنبيه",
                f"لا توجد بيانات مسجلة للتاريخ: {selected_date_text}",
            )
            return

        database_path = self.db.path
        year_id = self.db.year_id

        def export_day():
            import json

            payload = DayLessonsBrowsePage._build_day_payload(
                database_path, year_id, day_id
            )
            documents = Path.home() / "Documents"
            documents.mkdir(parents=True, exist_ok=True)
            output_path = documents / f"school_day_{payload['date']}.json"
            with output_path.open("w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, indent=4)
            return output_path

        start_background_task(
            self,
            export_day,
            lambda output_path: QMessageBox.information(
                self,
                "نجاح التصدير",
                f"تم تصدير بيانات اليوم بنجاح إلى مجلد المستندات:\n{output_path}",
            ),
            lambda error: QMessageBox.critical(
                self, "تعذر تصدير اليوم",
                f"حدث خطأ أثناء تصدير بيانات اليوم:\n{error}",
            ),
        )

    def import_day_from_json(self):
        if not self.ensure_school_year_writable():
            return
        import json
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف JSON للاستيراد", str(APP_DIR), "ملفات JSON (*.json);;كل الملفات (*)")
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                day_data = json.load(f)
            target_date = day_data.get("date")
            if not target_date:
                QMessageBox.warning(self, "خطأ في الملف", "ملف JSON لا يحتوي على حقل التاريخ (date).")
                return
            with self.db.connect() as con:
                cursor = con.cursor()
                cursor.execute("SELECT id FROM day_data WHERE date = ? AND ann_scolaire_id = ?", (target_date, self.db.year_id))
                existing_day = cursor.fetchone()
                if existing_day:
                    old_day_id = existing_day[0]
                    cursor.execute("DELETE FROM day_data WHERE id = ?", (old_day_id,))
                cursor.execute("INSERT INTO day_data (date, ann_scolaire_id) VALUES (?, ?)", (target_date, self.db.year_id))
                new_day_id = cursor.lastrowid
                for lesson in day_data.get("lessons", []):
                    group_key = str(
                        lesson.get("class_group_key") or ""
                    ).strip()
                    class_name = group_key or lesson.get("classe", "")
                    class_level = (
                        f"group:{group_key}"
                        if group_key else lesson.get("classe_level")
                    )
                    classe_id, class_group_id, class_ids = (
                        self.db._resolve_lesson_class(
                            con, class_name, class_level
                        )
                    )
                    majal_id, learning_mode_id = (
                        self.db.resolve_lesson_lookup_ids(
                            con, lesson.get("majal", ""),
                            lesson.get("namat_taallom", ""),
                        )
                    )
                    cursor.execute("""
                        INSERT INTO hessa (
                            classe_id, majal_id, heure, time, wehda_number,
                            hessa_number, learning_mode_id, day_data_id,
                            class_group_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        classe_id, majal_id,
                        lesson.get("heure", ""), lesson.get("time", ""),
                        lesson.get("wehda_number", 1),
                        lesson.get("hessa_number", 1),
                        learning_mode_id, new_day_id, class_group_id,
                    ))
                    new_hessa_id = cursor.lastrowid
                    self.db._replace_hessa_classes(
                        con, new_hessa_id, class_ids
                    )
                    for activity in lesson.get("activities", []):
                        activity_class_id = self.db.resolve_activity_class(
                            con, new_hessa_id, activity.get("classe")
                        )
                        cursor.execute("""
                            INSERT INTO nachat(
                                title, time, hessa_id, classe_id
                            ) VALUES (?, ?, ?, ?)
                        """, (
                            activity.get("title", ""),
                            activity.get("time", ""),
                            new_hessa_id,
                            activity_class_id,
                        ))
                        new_nachat_id = cursor.lastrowid
                        for detail in activity.get("details", []):
                            cursor.execute("INSERT INTO nachat_detail (key_name, value_text, nachat_id) VALUES (?, ?, ?)", (detail.get("key_name", ""), detail.get("value_text", ""), new_nachat_id))
                con.commit()
            qd = QDate.fromString(target_date, "yyyy-MM-dd")
            if qd.isValid():
                self.date_edit.setDate(qd)
            self.load_day()
            QMessageBox.information(self, "نجاح الاستيراد", f"تم استيراد بيانات يوم {target_date} بنجاح وتسجيلها في التطبيق.")
        except Exception as e:
            QMessageBox.critical(self, "خطأ في الاستيراد", f"حدث خطأ أثناء قراءة أو استيراد ملف JSON:\n{e}")

    @staticmethod
    def _single_json_drop_path(event):
        """أرجع مسار ملف JSON واحد فقط، وتجاهل السحب الداخلي والعناصر الأخرى."""
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        urls = mime.urls()
        if len(urls) != 1:
            return None
        path = urls[0].toLocalFile()
        if not path or Path(path).suffix.lower() != ".json":
            return None
        return path

    @staticmethod
    def _classify_json_payload(data):
        """تصنيف ملفات التطبيق حتى لا تختلط نسخة البرامج الرسمية بملفات الأيام."""
        if not isinstance(data, dict):
            return None
        if data.get("format") == "almo3in_official_programs":
            return "official_full"
        if isinstance(data.get("programs"), list) and isinstance(data.get("levels"), list) and isinstance(data.get("majals"), list):
            return "official_full"
        if "moukawan_kifaya" in data and "matiere" in data:
            return "official_tree"
        if isinstance(data.get("days"), list) or ("school_info" in data and "date" not in data):
            return "school_year"
        if "date" in data and isinstance(data.get("lessons"), list):
            return "school_day"
        return None

    def dragEnterEvent(self, event):
        # نقبل الملفات الخارجية بصيغة JSON فقط؛ السحب الداخلي بين عناصر الواجهة لا يُلتقط هنا.
        path = self._single_json_drop_path(event)
        if path:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        file_path = self._single_json_drop_path(event)
        if not file_path:
            event.ignore()
            return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as source:
                data = json.load(source)
            payload_type = self._classify_json_payload(data)
            if payload_type in ("official_full", "official_tree"):
                self.pages_stack.setCurrentWidget(self.official_programs_page)
                self.import_programs_json(file_path)
            elif payload_type in ("school_year", "school_day"):
                self.process_json_import(file_path)
            else:
                QMessageBox.warning(
                    self,
                    "نوع ملف غير معروف",
                    "لم يتعرّف التطبيق على محتوى الملف. اسحب ملف JSON صادرًا عن التطبيق أو عن صفحة البرامج الرسمية.",
                )
                event.ignore()
                return
            event.acceptProposedAction()
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            QMessageBox.critical(self, "تعذّر قراءة الملف", f"لم نتمكّن من قراءة ملف JSON:\n{exc}")
            event.ignore()
        except Exception as exc:
            QMessageBox.critical(self, "خطأ أثناء الاستيراد", f"تعذّر استيراد الملف:\n{exc}")
            event.ignore()

    def import_all_years_from_json(self):
        if not self.ensure_school_year_writable():
            return
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "اختيار ملف JSON السنوي للاستيراد", str(Path.home() / "Documents"), "ملفات JSON (*.json);;كل الملفات (*)")
        if not file_path:
            return
        self.process_json_import(file_path)

    def process_json_import(self, file_path):
        if not self.ensure_school_year_writable():
            return
        import json
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if "days" in data:
                school_info = data.get("school_info", {})
                default_year_name = school_info.get("nom_annee", "2026-2027")
                
                dlg = YearImportDialog(self.db, default_year_name=default_year_name, parent=self)
                if not dlg.exec():
                    return
                target_year_name = dlg.get_selected_year_name()
                if not target_year_name:
                    QMessageBox.warning(self, "تنبيه", "اسم السنة الدراسية مطلوب.")
                    return

                with self.db.connect() as con:
                    cursor = con.cursor()
                    cursor.execute("SELECT id FROM ann_scolaire WHERE nom_annee = ?", (target_year_name,))
                    row = cursor.fetchone()
                    legacy_profile_columns = SCHOOL_INFO_COLUMNS[1:5]
                    extended_profile_columns = SCHOOL_INFO_COLUMNS[5:]
                    if row:
                        target_year_id = row[0]
                        assignments = [
                            f"{column}=?" for column in legacy_profile_columns
                        ] + [
                            f"{column}=COALESCE(?, {column})"
                            for column in extended_profile_columns
                        ]
                        cursor.execute(
                            f"UPDATE ann_scolaire SET {', '.join(assignments)} "
                            "WHERE id=?",
                            tuple(
                                school_info.get(column, "")
                                for column in legacy_profile_columns
                            )
                            + tuple(
                                school_info.get(column)
                                for column in extended_profile_columns
                            )
                            + (target_year_id,)
                        )
                    else:
                        insert_values = [target_year_name]
                        for column in SCHOOL_INFO_COLUMNS[1:]:
                            default_value = 0 if column == "nombre_enfants" else ""
                            insert_values.append(
                                school_info.get(column, default_value)
                            )
                        placeholders = ", ".join("?" for _ in SCHOOL_INFO_COLUMNS)
                        cursor.execute(
                            f"INSERT INTO ann_scolaire "
                            f"({', '.join(SCHOOL_INFO_COLUMNS)}) "
                            f"VALUES ({placeholders})",
                            insert_values
                        )
                        target_year_id = cursor.lastrowid

                    imported_days_count = 0
                    for day_item in data.get("days", []):
                        target_date = day_item.get("date")
                        if not target_date:
                            continue
                        
                        cursor.execute("SELECT id FROM day_data WHERE date = ? AND ann_scolaire_id = ?", (target_date, target_year_id))
                        existing_day = cursor.fetchone()
                        if existing_day:
                            cursor.execute("DELETE FROM day_data WHERE id = ?", (existing_day[0],))
                        
                        cursor.execute("INSERT INTO day_data (date, ann_scolaire_id) VALUES (?, ?)", (target_date, target_year_id))
                        new_day_id = cursor.lastrowid
                        
                        for lesson in day_item.get("lessons", []):
                            group_key = str(
                                lesson.get("class_group_key") or ""
                            ).strip()
                            classe_id, class_group_id, class_ids = (
                                self.db._resolve_lesson_class(
                                    con,
                                    group_key or lesson.get("classe", ""),
                                    (
                                        f"group:{group_key}"
                                        if group_key
                                        else lesson.get("classe_level")
                                    ),
                                )
                            )
                            majal_id, learning_mode_id = (
                                self.db.resolve_lesson_lookup_ids(
                                    con, lesson.get("majal", ""),
                                    lesson.get("namat_taallom", ""),
                                )
                            )
                            cursor.execute("""
                                INSERT INTO hessa (
                                    classe_id, majal_id, heure, time,
                                    wehda_number, hessa_number,
                                    learning_mode_id, day_data_id,
                                    class_group_id
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                classe_id, majal_id,
                                lesson.get("heure", ""), lesson.get("time", ""),
                                lesson.get("wehda_number", 1),
                                lesson.get("hessa_number", 1),
                                learning_mode_id, new_day_id, class_group_id,
                            ))
                            new_hessa_id = cursor.lastrowid
                            self.db._replace_hessa_classes(
                                con, new_hessa_id, class_ids
                            )
                            
                            for activity in lesson.get("activities", []):
                                activity_class_id = (
                                    self.db.resolve_activity_class(
                                        con, new_hessa_id,
                                        activity.get("classe"),
                                    )
                                )
                                cursor.execute("""
                                    INSERT INTO nachat(
                                        title, time, hessa_id, classe_id
                                    ) VALUES (?, ?, ?, ?)
                                """, (
                                    activity.get("title", ""),
                                    activity.get("time", ""),
                                    new_hessa_id,
                                    activity_class_id,
                                ))
                                new_nachat_id = cursor.lastrowid
                                
                                for detail in activity.get("details", []):
                                    cursor.execute("INSERT INTO nachat_detail (key_name, value_text, nachat_id) VALUES (?, ?, ?)", (detail.get("key_name", ""), detail.get("value_text", ""), new_nachat_id))
                        
                        imported_days_count += 1
                    con.commit()

                self.load_school_info()
                self.load_day()
                QMessageBox.information(self, "نجاح الاستيراد الشامل", f"تم استيراد السنة الدراسية بكافة أيامها ({imported_days_count} يوم) بنجاح!")
            else:
                target_date = data.get("date")
                if not target_date:
                    QMessageBox.warning(self, "خطأ في الملف", "ملف JSON لا يحتوي على حقل التاريخ (date) أو بيانات صحيحة.")
                    return
                with self.db.connect() as con:
                    cursor = con.cursor()
                    cursor.execute("SELECT id FROM day_data WHERE date = ? AND ann_scolaire_id = ?", (target_date, self.db.year_id))
                    existing_day = cursor.fetchone()
                    if existing_day:
                        cursor.execute("DELETE FROM day_data WHERE id = ?", (existing_day[0],))
                    cursor.execute("INSERT INTO day_data (date, ann_scolaire_id) VALUES (?, ?)", (target_date, self.db.year_id))
                    new_day_id = cursor.lastrowid
                    for lesson in data.get("lessons", []):
                        group_key = str(
                            lesson.get("class_group_key") or ""
                        ).strip()
                        classe_id, class_group_id, class_ids = (
                            self.db._resolve_lesson_class(
                                con,
                                group_key or lesson.get("classe", ""),
                                (
                                    f"group:{group_key}"
                                    if group_key
                                    else lesson.get("classe_level")
                                ),
                            )
                        )
                        majal_id, learning_mode_id = (
                            self.db.resolve_lesson_lookup_ids(
                                con, lesson.get("majal", ""),
                                lesson.get("namat_taallom", ""),
                            )
                        )
                        cursor.execute("""
                            INSERT INTO hessa (
                                classe_id, majal_id, heure, time, wehda_number,
                                hessa_number, learning_mode_id, day_data_id,
                                class_group_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            classe_id, majal_id,
                            lesson.get("heure", ""), lesson.get("time", ""),
                            lesson.get("wehda_number", 1),
                            lesson.get("hessa_number", 1),
                            learning_mode_id, new_day_id, class_group_id,
                        ))
                        new_hessa_id = cursor.lastrowid
                        self.db._replace_hessa_classes(
                            con, new_hessa_id, class_ids
                        )
                        for activity in lesson.get("activities", []):
                            activity_class_id = self.db.resolve_activity_class(
                                con, new_hessa_id, activity.get("classe")
                            )
                            cursor.execute("""
                                INSERT INTO nachat(
                                    title, time, hessa_id, classe_id
                                ) VALUES (?, ?, ?, ?)
                            """, (
                                activity.get("title", ""),
                                activity.get("time", ""),
                                new_hessa_id,
                                activity_class_id,
                            ))
                            new_nachat_id = cursor.lastrowid
                            for detail in activity.get("details", []):
                                cursor.execute("INSERT INTO nachat_detail (key_name, value_text, nachat_id) VALUES (?, ?, ?)", (detail.get("key_name", ""), detail.get("value_text", ""), new_nachat_id))
                    con.commit()
                qd = QDate.fromString(target_date, "yyyy-MM-dd")
                if qd.isValid():
                    self.date_edit.setDate(qd)
                self.load_day()
                QMessageBox.information(self, "نجاح الاستيراد", f"تم استيراد بيانات يوم {target_date} بنجاح وتسجيلها في التطبيق.")
        except Exception as e:
            QMessageBox.critical(self, "خطأ في الاستيراد", f"حدث خطأ أثناء قراءة أو استيراد ملف JSON:\n{e}")

    def clear_current_day_lessons(self):
        if not self.ensure_school_year_writable():
            return
        if self.confirm(
            "هل أنت متأكد من مسح جميع حصص اليوم الحالي، "
            "بما فيها حصص التقييم المسجلة وجلسات النوادي؟"
        ):
            try:
                day_text = self.date_edit.date().toString("yyyy-MM-dd")
                with self.db.connect() as con:
                    cursor = con.cursor()
                    if self.day_id:
                        cursor.execute(
                            """
                            DELETE FROM exam_schedule_diary_lesson
                            WHERE lesson_id IN (
                                SELECT id FROM hessa WHERE day_data_id=?
                            )
                            """,
                            (self.day_id,),
                        )
                        cursor.execute(
                            "DELETE FROM hessa WHERE day_data_id = ?",
                            (self.day_id,),
                        )
                    cursor.execute(
                        "DELETE FROM cultural_club_daily_session "
                        "WHERE session_date = ? AND ann_scolaire_id = ?",
                        (day_text, self.db.year_id),
                    )
                    con.commit()
                self.selected_lesson_id = None
                self.selected_activity_id = None
                self.load_day()
                self.statusBar().showMessage(
                    "تم مسح جميع حصص اليوم، بما فيها التقييمات، "
                    "وجلسات النوادي بنجاح.",
                    3000,
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "خطأ",
                    f"حدث خطأ أثناء مسح حصص اليوم والتقييمات "
                    f"وجلسات النوادي: {e}",
                )

    def refresh_pages_after_clearing_lessons(self):
        day_text = self.date_edit.date().toString("yyyy-MM-dd")
        self.load_day()
        self.day_lessons_page.calendar.year_id = self.db.year_id
        self.day_lessons_page.set_day(
            self.db.recorded_day_id(day_text), day_text
        )
        self.load_statistics(force_refresh=True)

        timetable_page = self.timetable_page
        timetable_page.set_automatic_schedule(
            {},
            timetable_page.automatic_first_hour,
            timetable_page.automatic_last_hour,
        )
        if getattr(self, "_timetable_thread", None) is not None:
            self._timetable_refresh_pending = True
        else:
            self.open_timetable_dialog()

    def clear_all_lessons_in_db(self):
        if not self.ensure_school_year_writable():
            return
        confirmation_code = _new_clear_confirmation_code()
        dialog = ClearAllConfirmationDialog(confirmation_code, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not _clear_confirmation_code_matches(
            dialog.code_edit.text(), confirmation_code
        ):
            QMessageBox.warning(
                self,
                "رمز التحقق غير صحيح",
                "لم يتم مسح أي بيانات لأن الرمز المدخل لا يطابق الرمز المعروض.",
            )
            return
        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                cursor.execute("DELETE FROM nachat_detail")
                cursor.execute("DELETE FROM nachat")
                cursor.execute("DELETE FROM hessa")
                con.commit()
            self.selected_lesson_id = None
            self.selected_activity_id = None
            self.refresh_pages_after_clearing_lessons()
            self.statusBar().showMessage(
                "تم مسح جميع الحصص في قاعدة البيانات بالكامل.", 3000
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "تعذر مسح الحصص",
                f"حدث خطأ أثناء مسح جميع الحصص:\n{error}",
            )

    def clear_all_activities_for_lesson(self):
        if not self.ensure_school_year_writable():
            return
        if not self.selected_lesson_id:
            return self.warn_select("حصة أولاً")
        if self.confirm("هل أنت متأكد من مسح جميع أنشطة هذه الحصة وخصائصها؟"):
            try:
                with self.db.connect() as con:
                    cursor = con.cursor()
                    cursor.execute("DELETE FROM nachat WHERE hessa_id = ?", (self.selected_lesson_id,))
                    con.commit()
                self.selected_activity_id = None
                self.refresh_activities()
                self.detail_cards.clear()
                self.statusBar().showMessage("تم مسح جميع أنشطة الحصة بنجاح.", 3000)
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء مسح أنشطة الحصة: {e}")

    def clear_all_details_for_activity(self):
        if not self.ensure_school_year_writable():
            return
        if not self.selected_activity_id:
            return self.warn_select("نشاط أولاً")
        if self.confirm("هل أنت متأكد من مسح جميع خصائص هذا النشاط؟"):
            try:
                with self.db.connect() as con:
                    cursor = con.cursor()
                    cursor.execute("DELETE FROM nachat_detail WHERE nachat_id = ?", (self.selected_activity_id,))
                    con.commit()
                self.refresh_details()
                self.statusBar().showMessage("تم مسح جميع خصائص النشاط بنجاح.", 3000)
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء مسح خصائص النشاط: {e}")

    def copy_activity_details(self):
        if not self.selected_activity_id:
            return self.warn_select("نشاط أولاً لنسخ خصائصه")
        details = self.db.details(self.selected_activity_id)
        if not details:
            QMessageBox.information(self, "تنبيه", "النشاط المحدد لا يحتوي على خصائص لنسخها.")
            return
        self.copied_details = [(d[1], d[2]) for d in details]
        self.statusBar().showMessage(f"تم نسخ {len(self.copied_details)} خاصية بنجاح.", 3000)

    def paste_activity_details(self):
        if not self.ensure_school_year_writable():
            return
        if not self.selected_activity_id:
            return self.warn_select("نشاط أولاً لصق الخصائص فيه")
        if not self.copied_details:
            QMessageBox.warning(self, "تنبيه", "لا توجد خصائص منسوخة حالياً.")
            return
        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                for key_name, value_text in self.copied_details:
                    cursor.execute("INSERT INTO nachat_detail (key_name, value_text, nachat_id) VALUES (?, ?, ?)", (key_name, value_text, self.selected_activity_id))
                con.commit()
            self.refresh_details()
            self.statusBar().showMessage("تم لصق الخصائص بنجاح.", 3000)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء لصق الخصائص: {e}")

    def export_all_days_for_year(self):
        dlg = SchoolYearSelectionDialog(self.db, parent=self)
        if not dlg.exec():
            return

        year_id, year_name = dlg.get_selected_year_info()
        if not year_id:
            QMessageBox.warning(self, "تنبيه", "لم يتم تحديد سنة دراسية.")
            return

        database_path = self.db.path

        def export_year():
            import json

            columns = ", ".join(SCHOOL_INFO_COLUMNS)
            with connect_database(database_path) as connection:
                school_info_row = connection.execute(
                    f"SELECT {columns} FROM ann_scolaire WHERE id = ?",
                    (year_id,),
                ).fetchone()
                if school_info_row is None:
                    raise ValueError("السنة الدراسية المحددة غير موجودة.")
                school_info = dict(zip(SCHOOL_INFO_COLUMNS, school_info_row))
                days = connection.execute(
                    """SELECT d.id, d.date,
                              EXISTS (
                                  SELECT 1 FROM hessa h
                                  WHERE h.day_data_id=d.id
                              )
                       FROM day_data d
                       WHERE d.ann_scolaire_id=?
                       ORDER BY d.date ASC""",
                    (year_id,),
                ).fetchall()
            if not days:
                raise ValueError(
                    f"لا توجد أيام مسجلة للسنة الدراسية: {year_name}"
                )

            all_days_data = {"school_info": school_info, "days": []}
            for day_id, day_date, has_lessons in days:
                lessons = (
                    DayLessonsBrowsePage._build_day_payload(
                        database_path, year_id, day_id
                    )["lessons"]
                    if has_lessons else []
                )
                all_days_data["days"].append({
                    "date": day_date,
                    "lessons": lessons,
                })

            documents = Path.home() / "Documents"
            documents.mkdir(parents=True, exist_ok=True)
            safe_year_name = str(year_name).replace("/", "-")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = documents / (
                f"school_year_{safe_year_name}_export_{timestamp}.json"
            )
            with output_path.open("w", encoding="utf-8") as output:
                json.dump(all_days_data, output, ensure_ascii=False, indent=4)
            return output_path

        start_background_task(
            self,
            export_year,
            lambda output_path: QMessageBox.information(
                self,
                "نجاح التصدير الشامل",
                f"تم تصدير جميع أيام السنة الدراسية ({year_name}) بنجاح "
                f"إلى مجلد المستندات:\n{output_path}",
            ),
            lambda error: QMessageBox.critical(
                self,
                "خطأ في التصدير",
                f"حدث خطأ أثناء تصدير بيانات السنة الدراسية:\n{error}",
            ),
        )

    def update_prog_actions_state(self):
        """التصدير والاستيراد الشاملان لا يتطلبان تحديد مادة بعينها."""
        self.export_prog_action.setEnabled(True)
        self.import_prog_action.setEnabled(True)

    def export_programs_json(self):
        """تصدير كامل البرامج الرسمية، من المستويات إلى المحتويات، في ملف JSON واحد."""
        from PySide6.QtWidgets import QFileDialog

        documents_dir = Path.home() / "Documents"
        start_dir = documents_dir if documents_dir.exists() else Path.home()
        default_name = start_dir / f"البرامج_الرسمية_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "تصدير البرامج الرسمية كاملة",
            str(default_name),
            "ملفات JSON (*.json);;كل الملفات (*)",
        )
        if not file_path:
            return
        if Path(file_path).suffix.lower() != ".json":
            file_path += ".json"
        database_path = self.db.path

        def export_programs():
            with connect_database(database_path) as con:
                levels = [row[0] for row in con.execute("SELECT name FROM level ORDER BY id").fetchall()]
                majals = [row[0] for row in con.execute("SELECT name FROM majal ORDER BY id").fetchall()]

                majal_comp_rows = con.execute(
                    """SELECT cmj.id, cmj.competence, m.name, l.name
                       FROM competence_majal cmj
                       JOIN majal m ON m.id = cmj.id_majal
                       JOIN level l ON l.id = cmj.id_level
                       ORDER BY l.id, m.id, cmj.id"""
                ).fetchall()
                matiere_rows = con.execute(
                    """SELECT id, matiere, competence, id_competence_majal
                       FROM competence_matiere ORDER BY id"""
                ).fetchall()
                mouk_rows = con.execute(
                    """SELECT id, competence, id_competence_matiere
                       FROM moukawan_kifaya ORDER BY id"""
                ).fetchall()
                objectif_rows = con.execute(
                    """SELECT id, objectif_specifique, description, id_moukawa_kifaya
                       FROM objectif_specifique ORDER BY id"""
                ).fetchall()
                content_rows = con.execute(
                    """SELECT content, description, id_objectif_specifique
                       FROM content ORDER BY id"""
                ).fetchall()

            contents_by_objectif = {}
            for content_text, description, objectif_id in content_rows:
                contents_by_objectif.setdefault(objectif_id, []).append({
                    "content": content_text or "", "description": description or ""
                })

            objectifs_by_mouk = {}
            for objectif_id, objectif_text, description, mouk_id in objectif_rows:
                objectifs_by_mouk.setdefault(mouk_id, []).append({
                    "objectif_specifique": objectif_text or "",
                    "description": description or "",
                    "content": contents_by_objectif.get(objectif_id, []),
                })

            mouk_by_matiere = {}
            for mouk_id, competence, matiere_id in mouk_rows:
                mouk_by_matiere.setdefault(matiere_id, []).append({
                    "competence": competence or "",
                    "objectif_specifique": objectifs_by_mouk.get(mouk_id, []),
                })

            matieres_by_competence_majal = {}
            for matiere_id, matiere, competence, competence_majal_id in matiere_rows:
                matieres_by_competence_majal.setdefault(competence_majal_id, []).append({
                    "matiere": matiere or "",
                    "competence_matiere": competence or "",
                    "moukawan_kifaya": mouk_by_matiere.get(matiere_id, []),
                })

            programs = []
            for cmj_id, competence_majal, majal_name, level_name in majal_comp_rows:
                programs.append({
                    "level": level_name,
                    "majal": majal_name,
                    "competence_majal": competence_majal or "",
                    "matieres": matieres_by_competence_majal.get(cmj_id, []),
                })

            payload = {
                "format": "almo3in_official_programs",
                "version": 1,
                "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "levels": levels,
                "majals": majals,
                "programs": programs,
            }

            target = Path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.write("\n")
            return target, len(levels), len(majals), len(programs)

        def show_export_success(result):
            target, level_count, majal_count, program_count = result
            QMessageBox.information(
                self, "تمّ التصدير",
                "تمّ تصدير البرامج الرسمية كاملة بنجاح.\n"
                f"عدد المستويات: {level_count}\n"
                f"عدد المجالات: {majal_count}\n"
                f"عدد كفايات المجالات: {program_count}\n"
                f"الملف: {target}",
            )

        start_background_task(
            self,
            export_programs,
            show_export_success,
            lambda error: QMessageBox.critical(
                self,
                "تعذّر التصدير",
                f"حدث خطأ أثناء تصدير البرامج الرسمية:\n{error}",
            ),
        )

    def import_programs_json(self, file_path=None):
        """استيراد نسخة كاملة، مع دعم ملفات الشجرة القديمة للحفاظ على التوافق."""
        from PySide6.QtWidgets import QFileDialog

        if not file_path:
            documents_dir = Path.home() / "Documents"
            start_dir = documents_dir if documents_dir.exists() else Path.home()
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "استيراد البرامج الرسمية من ملف JSON",
                str(start_dir),
                "ملفات JSON (*.json);;كل الملفات (*)",
            )
            if not file_path:
                return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as source:
                data = json.load(source)
            payload_type = self._classify_json_payload(data)

            if payload_type == "official_full":
                answer = QMessageBox.question(
                    self,
                    "تأكيد استبدال البرامج الرسمية",
                    "سيُستبدل محتوى البرامج الرسمية الحالي بالكامل بالمحتوى الموجود في الملف، بما يشمل المستويات والمجالات والكفايات والأهداف والمحتويات.\n\nيُنصح بتصدير نسخة احتياطية قبل المتابعة. هل تريد مواصلة الاستيراد؟",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
                counts = self._restore_full_official_programs(data)
                self.pages_stack.setCurrentWidget(self.official_programs_page)
                self.official_programs_page.load_levels_and_majals()
                QMessageBox.information(
                    self, "تمّ الاستيراد",
                    "تمّ استيراد البرامج الرسمية بنجاح.\n"
                    f"المستويات: {counts['levels']}، المجالات: {counts['majals']}، "
                    f"كفايات المجالات: {counts['competences_majal']}، المواد: {counts['matieres']}، "
                    f"مكوّنات الكفاية: {counts['moukawan']}، الأهداف: {counts['objectifs']}، المحتويات: {counts['contents']}."
                )
                return

            if payload_type == "official_tree":
                page = self.official_programs_page
                matiere_id = page.selected_competence_matiere_id
                if not matiere_id:
                    QMessageBox.warning(
                        self, "لم تُحدّد المادة",
                        "هذا الملف يحتوي على شجرة كفاية واحدة. افتح البرامج الرسمية وحدّد المستوى والمجال والمادة المستهدفة، ثم أعد الاستيراد.",
                    )
                    return
                imported = self._import_single_competence_tree(data, matiere_id)
                if not imported:
                    return
                page.load_moukawan_data()
                QMessageBox.information(self, "تمّ الاستيراد", "تمّ استيراد شجرة الكفاية المحددة بنجاح.")
                return

            QMessageBox.warning(
                self, "ملف غير صالح",
                "لا يحتوي الملف على نسخة برامج رسمية معروفة أو شجرة كفاية قابلة للاستيراد.",
            )
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            QMessageBox.critical(self, "تعذّر قراءة الملف", f"لم نتمكّن من قراءة ملف JSON:\n{exc}")
        except Exception as exc:
            QMessageBox.critical(self, "تعذّر الاستيراد", f"حدث خطأ أثناء استيراد البرامج الرسمية:\n{exc}")

    def _restore_full_official_programs(self, data):
        """استعادة نسخة كاملة داخل معاملة واحدة؛ يُلغى التغيير كله عند وقوع خطأ."""
        if not isinstance(data, dict):
            raise ValueError("يجب أن تكون بيانات ملف النسخة الاحتياطية كائن JSON.")
        if data.get("format") not in (None, "almo3in_official_programs"):
            raise ValueError("صيغة ملف البرامج الرسمية غير مدعومة.")
        if data.get("format") == "almo3in_official_programs" and data.get("version") != 1:
            raise ValueError("إصدار ملف البرامج الرسمية غير مدعوم.")
        if not all(key in data for key in ("levels", "majals", "programs")):
            raise ValueError("ملف النسخة الاحتياطية ناقص؛ لم يقع تغيير قاعدة البيانات.")
        levels_data = data["levels"]
        majals_data = data["majals"]
        programs = data["programs"]
        if not all(isinstance(value, list) for value in (levels_data, majals_data, programs)):
            raise ValueError("بنية ملف النسخة الاحتياطية غير سليمة.")

        def get_name(value):
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, dict):
                return str(value.get("name", "")).strip()
            return ""

        level_names = list(dict.fromkeys(name for name in map(get_name, levels_data) if name))
        majal_names = list(dict.fromkeys(name for name in map(get_name, majals_data) if name))
        for program in programs:
            if not isinstance(program, dict):
                raise ValueError("توجد كفاية مجال بصيغة غير سليمة داخل الملف.")
            level_name = str(program.get("level", "")).strip()
            majal_name = str(program.get("majal", "")).strip()
            if level_name and level_name not in level_names:
                level_names.append(level_name)
            if majal_name and majal_name not in majal_names:
                majal_names.append(majal_name)
            if not isinstance(program.get("matieres", []), list):
                raise ValueError("قائمة المواد في الملف غير سليمة.")

        counts = {
            "levels": 0, "majals": 0, "competences_majal": 0, "matieres": 0,
            "moukawan": 0, "objectifs": 0, "contents": 0,
        }
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            # حذف مرتب لتبقى العلاقات سليمة حتى عند تعطيل بعض قيود الحماية خارج التطبيق.
            con.execute("DELETE FROM content")
            con.execute("DELETE FROM objectif_specifique")
            con.execute("DELETE FROM moukawan_kifaya")
            con.execute("DELETE FROM competence_matiere")
            con.execute("DELETE FROM competence_majal")
            con.execute("""
                DELETE FROM level
                WHERE id NOT IN (SELECT level_id FROM classe)
            """)
            con.execute("""
                DELETE FROM majal
                WHERE id NOT IN (
                    SELECT majal_id FROM hessa WHERE majal_id IS NOT NULL
                )
                AND id NOT IN (SELECT majal_id FROM teaching_plan)
            """)

            level_ids = {}
            for name in level_names:
                con.execute("INSERT OR IGNORE INTO level(name) VALUES(?)", (name,))
                level_ids[name] = con.execute("SELECT id FROM level WHERE name=?", (name,)).fetchone()[0]
            counts["levels"] = len(level_ids)

            majal_ids = {}
            for name in majal_names:
                con.execute("INSERT OR IGNORE INTO majal(name) VALUES(?)", (name,))
                majal_ids[name] = con.execute("SELECT id FROM majal WHERE name=?", (name,)).fetchone()[0]
            counts["majals"] = len(majal_ids)

            for program in programs:
                level_name = str(program.get("level", "")).strip()
                majal_name = str(program.get("majal", "")).strip()
                competence_majal = str(program.get("competence_majal", "")).strip()
                if not level_name or not majal_name or not competence_majal:
                    # تجاهل كفايات المجال غير المكتملة بدلاً من إنشاء سجلات عديمة الفائدة.
                    continue
                level_id = level_ids[level_name]
                majal_id = majal_ids[majal_name]
                con.execute(
                    "INSERT OR IGNORE INTO competence_majal(competence, id_majal, id_level) VALUES(?,?,?)",
                    (competence_majal, majal_id, level_id),
                )
                cmj_id = con.execute(
                    "SELECT id FROM competence_majal WHERE competence=? AND id_majal=? AND id_level=?",
                    (competence_majal, majal_id, level_id),
                ).fetchone()[0]
                counts["competences_majal"] += 1

                for matiere in program.get("matieres", []):
                    if not isinstance(matiere, dict):
                        raise ValueError("توجد مادة بصيغة غير سليمة داخل الملف.")
                    matiere_name = str(matiere.get("matiere", "")).strip()
                    competence_matiere = str(matiere.get("competence_matiere", "")).strip()
                    if not matiere_name or not competence_matiere:
                        continue
                    con.execute(
                        "INSERT OR IGNORE INTO competence_matiere(matiere, competence, id_competence_majal) VALUES(?,?,?)",
                        (matiere_name, competence_matiere, cmj_id),
                    )
                    matiere_id = con.execute(
                        "SELECT id FROM competence_matiere WHERE matiere=? AND competence=? AND id_competence_majal=?",
                        (matiere_name, competence_matiere, cmj_id),
                    ).fetchone()[0]
                    counts["matieres"] += 1

                    mouk_list = matiere.get("moukawan_kifaya", [])
                    if not isinstance(mouk_list, list):
                        raise ValueError("قائمة مكوّنات الكفاية غير سليمة.")
                    for mouk in mouk_list:
                        if isinstance(mouk, str):
                            mouk_text, objectifs = mouk.strip(), []
                        elif isinstance(mouk, dict):
                            mouk_text = str(mouk.get("competence", "")).strip()
                            objectifs = mouk.get("objectif_specifique", [])
                            if not isinstance(objectifs, list):
                                raise ValueError("قائمة الأهداف المميزة غير سليمة.")
                        else:
                            raise ValueError("يوجد مكوّن كفاية بصيغة غير سليمة.")
                        if not mouk_text:
                            continue
                        con.execute(
                            "INSERT OR IGNORE INTO moukawan_kifaya(competence, id_competence_matiere) VALUES(?,?)",
                            (mouk_text, matiere_id),
                        )
                        mouk_id = con.execute(
                            "SELECT id FROM moukawan_kifaya WHERE competence=? AND id_competence_matiere=?",
                            (mouk_text, matiere_id),
                        ).fetchone()[0]
                        counts["moukawan"] += 1

                        for objectif in objectifs:
                            if isinstance(objectif, str):
                                objectif_text, description, contents = objectif.strip(), "", []
                            elif isinstance(objectif, dict):
                                objectif_text = str(objectif.get("objectif_specifique", "")).strip()
                                description = str(objectif.get("description", "") or "")
                                contents = objectif.get("content", [])
                                if not isinstance(contents, list):
                                    raise ValueError("قائمة المحتويات غير سليمة.")
                            else:
                                raise ValueError("يوجد هدف مميز بصيغة غير سليمة.")
                            if not objectif_text:
                                continue
                            con.execute(
                                "INSERT OR IGNORE INTO objectif_specifique(objectif_specifique, id_moukawa_kifaya, description) VALUES(?,?,?)",
                                (objectif_text, mouk_id, description),
                            )
                            objectif_id = con.execute(
                                "SELECT id FROM objectif_specifique WHERE objectif_specifique=? AND id_moukawa_kifaya=?",
                                (objectif_text, mouk_id),
                            ).fetchone()[0]
                            counts["objectifs"] += 1

                            for content in contents:
                                if isinstance(content, str):
                                    content_text, content_description = content.strip(), ""
                                elif isinstance(content, dict):
                                    content_text = str(content.get("content", "")).strip()
                                    content_description = str(content.get("description", "") or "")
                                else:
                                    raise ValueError("يوجد محتوى بصيغة غير سليمة.")
                                if not content_text:
                                    continue
                                con.execute(
                                    "INSERT OR IGNORE INTO content(content, id_objectif_specifique, description) VALUES(?,?,?)",
                                    (content_text, objectif_id, content_description),
                                )
                                counts["contents"] += 1
            con.commit()
        return counts

    def _import_single_competence_tree(self, data, matiere_id):
        """توافق رجعي مع ملفات JSON القديمة التي تصدّر شجرة مادة واحدة."""
        file_majal = str(data.get("majal", "")).strip()
        file_matiere = str(data.get("matiere", "")).strip()
        with self.db.connect() as con:
            current_info = con.execute(
                """SELECT m.name, cm.matiere
                   FROM competence_matiere cm
                   JOIN competence_majal cmj ON cmj.id = cm.id_competence_majal
                   JOIN majal m ON m.id = cmj.id_majal
                   WHERE cm.id = ?""",
                (matiere_id,),
            ).fetchone()
            if not current_info:
                raise ValueError("المادة المحددة لم تعد موجودة في قاعدة البيانات.")
            current_majal, current_matiere = current_info[0].strip(), current_info[1].strip()
            if (file_majal and file_majal != current_majal) or (file_matiere and file_matiere != current_matiere):
                raise ValueError(
                    "لا تتطابق بيانات الملف مع المادة المحددة.\n"
                    f"الملف: المجال {file_majal}، المادة {file_matiere}.\n"
                    f"التحديد الحالي: المجال {current_majal}، المادة {current_matiere}."
                )
            tree = data.get("moukawan_kifaya", [])
            if not isinstance(tree, list):
                raise ValueError("قائمة مكوّنات الكفاية في الملف غير سليمة.")
            answer = QMessageBox.question(
                self,
                "تأكيد استبدال شجرة الكفاية",
                "سيتم حذف الشجرة الحالية للمادة المحددة وتعويضها بالشجرة الموجودة في الملف. هل تواصل؟",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return False

            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM moukawan_kifaya WHERE id_competence_matiere = ?", (matiere_id,))
            for mouk in tree:
                if isinstance(mouk, str):
                    mouk_text, objectifs = mouk.strip(), []
                elif isinstance(mouk, dict):
                    mouk_text = str(mouk.get("competence", "")).strip()
                    objectifs = mouk.get("objectif_specifique", [])
                else:
                    raise ValueError("يوجد مكوّن كفاية بصيغة غير سليمة.")
                if not mouk_text:
                    continue
                cur = con.execute(
                    "INSERT INTO moukawan_kifaya(competence, id_competence_matiere) VALUES(?,?)",
                    (mouk_text, matiere_id),
                )
                new_mouk_id = cur.lastrowid
                if not isinstance(objectifs, list):
                    raise ValueError("قائمة الأهداف المميزة غير سليمة.")
                for obj in objectifs:
                    if isinstance(obj, str):
                        obj_text, obj_desc, contents = obj.strip(), "", []
                    elif isinstance(obj, dict):
                        obj_text = str(obj.get("objectif_specifique", "")).strip()
                        obj_desc = str(obj.get("description", "") or "")
                        contents = obj.get("content", [])
                    else:
                        raise ValueError("يوجد هدف مميز بصيغة غير سليمة.")
                    if not obj_text:
                        continue
                    if not isinstance(contents, list):
                        raise ValueError("قائمة المحتويات غير سليمة.")
                    obj_cur = con.execute(
                        "INSERT INTO objectif_specifique(objectif_specifique, id_moukawa_kifaya, description) VALUES(?,?,?)",
                        (obj_text, new_mouk_id, obj_desc),
                    )
                    new_obj_id = obj_cur.lastrowid
                    for cnt in contents:
                        if isinstance(cnt, str):
                            cnt_text, cnt_desc = cnt.strip(), ""
                        elif isinstance(cnt, dict):
                            cnt_text = str(cnt.get("content", "")).strip()
                            cnt_desc = str(cnt.get("description", "") or "")
                        else:
                            raise ValueError("يوجد محتوى بصيغة غير سليمة.")
                        if cnt_text:
                            con.execute(
                                "INSERT INTO content(content, id_objectif_specifique, description) VALUES(?,?,?)",
                                (cnt_text, new_obj_id, cnt_desc),
                            )
            con.commit()
        return True


WINDOW_SIZE_PRESETS = {
    "small": (1024, 768),
    "medium": (1366, 900),
    "large": (1600, 1000),
}


def _parse_window_size(arguments):
    parser = argparse.ArgumentParser(
        description="تشغيل دفتر التخطيط بحجم نافذة محدد."
    )
    parser.add_argument(
        "size",
        nargs="?",
        choices=tuple(WINDOW_SIZE_PRESETS),
        default="maximized",
        help="حجم النافذة: small أو medium أو large (الافتراضي: maximized)",
    )
    return parser.parse_args(arguments).size


def _show_window_at_size(window, size):
    window.set_small_window_profile(size == "small")

    if size == "maximized":
        window.showMaximized()
        return

    available = window.screen().availableGeometry()
    requested_width, requested_height = WINDOW_SIZE_PRESETS[size]
    width = min(requested_width, available.width())
    height = min(requested_height, available.height())
    geometry = window.geometry()
    geometry.setWidth(width)
    geometry.setHeight(height)
    geometry.moveCenter(available.center())
    window.setGeometry(geometry)
    window.show()


def main(size=None):
    if size is None:
        size = _parse_window_size(sys.argv[1:])
    elif size not in (*WINDOW_SIZE_PRESETS, "maximized"):
        raise ValueError("size must be small, medium, large, or maximized")

    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.RightToLeft)
    arabic_dialog_translator = ArabicDialogTranslator()
    app.installTranslator(arabic_dialog_translator)

    custom_font_family = load_custom_font()
    app.setFont(QFont(custom_font_family, 10))

    style_file = APP_DIR / "style_1.qss"
    if style_file.exists():
        with open(style_file, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    install_action_button_icon_filter(app)
    install_dialog_size_filter(app)

    try:
        window = SchoolPlanner()
    except sqlite3.Error as exc:
        QMessageBox.critical(
            None,
            "تعذّر فتح قاعدة البيانات",
            f"تعذّر فتح قاعدة البيانات:\n{exc}",
        )
        sys.exit(1)
    _show_window_at_size(window, size)
    warm_completion_cache(window.db.path, window.db.year_id)
    warm_activity_duration_cache(window.db.path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
