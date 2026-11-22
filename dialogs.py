# -*- coding: utf-8 -*-
"""Extracted module dialogs."""
import re
import json
import sqlite3
import uuid
from datetime import datetime, time

from PySide6.QtCore import (
    Qt, QDate, QLocale, QObject, QRunnable, Signal, QThreadPool, QTimer,
    QSize,
)
from PySide6.QtGui import (
    QAction, QColor, QFontMetrics, QIntValidator, QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QAbstractItemView,
    QBoxLayout, QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout,
    QGroupBox,
    QDateEdit, QFileDialog, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QMenu, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem,
    QTextEdit, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget, QListWidget, QScrollArea,
    QSizePolicy,
    QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem,
    QTabWidget,
)

from app_config import (
    DETAIL_KEYS_BY_NAMAT,
    PLANS_NAMES,
    TEACHER_GENDER_OPTIONS,
    is_small_window,
    level_firak_label,
    level_firak_selection_label,
    set_action_button_type,
    set_card_action_type,
)
from class_assignment_ui import add_assignment_editor
from widgets import CustomCalendarWidget

from app_config import DB_PATH, set_dialog_button_action_types
from completion import AutoCompletionTextEdit
from database import Database, duration_minutes


def _domain_for_activity_name(activity_name):
    normalized_name = str(activity_name or "").strip()
    if not normalized_name:
        return ""
    for plan_name, plan in PLANS_NAMES.items():
        domain = str(plan.get("المجال") or "").strip()
        if normalized_name == plan_name or normalized_name in plan.get(
            "الأنشطة", []
        ):
            return domain or normalized_name
        if normalized_name == domain:
            return domain
    return normalized_name


def _configure_compact_club_action(button, action_type, label):
    button.setText("")
    button.setProperty("compactClubAction", True)
    button.setAccessibleName(label)
    button.setToolTip(label)
    set_action_button_type(button, action_type)
    button.setIconSize(QSize(18, 18))
    button.setProperty("responsiveScaleFixedSize", QSize(44, 40))
    button.setFixedSize(44, 40)


class YearImportDialog(QDialog):
    def __init__(self, db, default_year_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("تحديد السنة الدراسية للاستيراد")
        self.setMinimumWidth(380)
        self.db = db
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.combo_years = QComboBox()
        self.combo_years.setEditable(True)
        self.load_existing_years()
        if default_year_name:
            self.combo_years.setCurrentText(default_year_name)
            
        form.addRow("السنة الدراسية المستهدفة:", self.combo_years)
        layout.addLayout(form)
        
        buttons = QDialogButtonBox()
        buttons.addButton("متابعة الاستيراد", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_existing_years(self):
        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                cursor.execute("SELECT id, nom_annee FROM ann_scolaire")
                rows = cursor.fetchall()
                for row in rows:
                    self.combo_years.addItem(row[1], row[0])
        except Exception as e:
            print(f"Error loading years: {e}")

    def get_selected_year_name(self):
        return self.combo_years.currentText().strip()


class SchoolYearSelectionDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setObjectName("schoolYearExportDialog")
        self.setWindowTitle("اختيار السنة الدراسية للتصدير")
        self.setMinimumWidth(350)
        self.db = db
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.combo_years = QComboBox()
        self.load_years()
        
        form.addRow("السنة الدراسية:", self.combo_years)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        export_button = buttons.addButton("تصدير", QDialogButtonBox.AcceptRole)
        export_button.setProperty("actionType", "export")
        cancel_button = buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        cancel_button.setProperty("actionType", "cancel")
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_years(self):
        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                cursor.execute("SELECT id, nom_annee FROM ann_scolaire")
                rows = cursor.fetchall()
                for row in rows:
                    self.combo_years.addItem(row[1], row[0])
        except Exception as e:
            print(f"Error loading years: {e}")

    def get_selected_year_info(self):
        year_id = self.combo_years.currentData()
        year_name = self.combo_years.currentText()
        return year_id, year_name


class PreviousSchoolYearsDialog(QDialog):
    def __init__(self, db, selected_year_id=None, parent=None):
        super().__init__(parent)
        self.setObjectName("previousSchoolYearsDialog")
        self.setWindowTitle("عرض السنوات الدراسية السابقة")
        self.setMinimumWidth(340)
        self.db = db

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combo_years = QComboBox()
        for year_id, year_name in self.db.school_years():
            self.combo_years.addItem(str(year_name or ""), year_id)
            if year_id == selected_year_id:
                self.combo_years.setCurrentIndex(self.combo_years.count() - 1)
        form.addRow("السنة الدراسية:", self.combo_years)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        buttons.addButton("عرض", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_year(self):
        return self.combo_years.currentData(), self.combo_years.currentText()


class TeachingAssignmentCard(QFrame):
    changed = Signal()
    removeRequested = Signal(object)

    def __init__(self, db, assignment=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.assignment = assignment or {}
        self._loading = True
        self._previous_subjects = {}
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("تعيين قسم ومواد تدريسه")
        title.setStyleSheet("font-weight: bold;")
        remove_button = QPushButton("حذف القسم")
        remove_button.clicked.connect(
            lambda: self.removeRequested.emit(self)
        )
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(remove_button)
        layout.addLayout(header)

        sections_panel = QWidget(self)
        form = QFormLayout()
        self.level_combo = QComboBox()
        self.level_combo.addItem("اختر المستوى", None)
        for level_id, level_name in self.db.levels():
            self.level_combo.addItem(level_name, level_id)
        for group_key, group in self.db.class_groups().items():
            self.level_combo.addItem(
                level_firak_selection_label(group_key),
                f"group:{group_key}",
            )

        self.class_combo = QComboBox()
        self.class_combo.setEditable(True)
        self.class_combo.addItem("اختر القسم أو اكتب اسمه", None)
        form.addRow("المستوى:", self.level_combo)
        form.addRow("اسم القسم:", self.class_combo)
        sections_panel.setLayout(form)

        activities_panel = QWidget(self)
        activities_layout = QVBoxLayout(activities_panel)
        activities_layout.setContentsMargins(0, 0, 0, 0)
        activities_layout.addWidget(QLabel("أنشطة التدريس:"))
        self.subjects_layout = QVBoxLayout()
        self.subjects_layout.setContentsMargins(0, 0, 0, 0)
        self.subjects_layout.setSpacing(6)
        activities_layout.addLayout(self.subjects_layout)
        activities_layout.addStretch(1)

        panels = QHBoxLayout()
        panels.addWidget(sections_panel, 1)
        panels.addWidget(activities_panel, 2)
        layout.addLayout(panels)

        self.level_combo.currentIndexChanged.connect(
            self._level_changed
        )
        self.class_combo.currentTextChanged.connect(
            self._emit_changed
        )
        self._load_assignment()
        self._loading = False

    def _load_assignment(self):
        level_id = self.assignment.get("level_id")
        group_key = str(
            self.assignment.get("class_group_key") or ""
        ).strip()
        if group_key:
            level_id = f"group:{group_key}"
        if level_id is not None:
            index = self.level_combo.findData(level_id)
            if index >= 0:
                self.level_combo.setCurrentIndex(index)
        self._reload_classes(self.assignment.get("class_name", ""))
        subjects = self.assignment.get("subjects", [])
        if not isinstance(subjects, list):
            subjects = []
        for subject in subjects:
            self._add_subject_row(subject)
        self._add_subject_row()

    def _reload_classes(self, selected_name=""):
        selected_name = str(selected_name or "").strip()
        if selected_name.startswith("اختر "):
            selected_name = ""
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        self.class_combo.addItem("اختر القسم أو اكتب اسمه", None)
        level_id = self.level_combo.currentData()
        if isinstance(level_id, str) and level_id.startswith("group:"):
            group_key = level_id[len("group:"):].strip()
            if group_key in self.db.class_groups():
                self.class_combo.addItem(
                    group_key, f"group:{group_key}"
                )
                if not selected_name:
                    selected_name = group_key
        elif level_id is not None:
            for class_id, class_name, class_level_id in self.db.classes():
                if class_level_id == level_id:
                    self.class_combo.addItem(class_name, class_id)
        index = self.class_combo.findText(
            selected_name, Qt.MatchFlag.MatchFixedString
        )
        if index >= 0:
            self.class_combo.setCurrentIndex(index)
        elif selected_name:
            self.class_combo.setEditText(selected_name)
        self.class_combo.blockSignals(False)

    def _level_changed(self, *_args):
        previous_name = self.class_combo.currentText()
        self._reload_classes(previous_name)
        self._emit_changed()

    def _emit_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    def _add_subject_row(self, selected_subject=""):
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        combo = QComboBox(row)
        combo.addItem("اختر مادة التدريس", "")
        for subject_name in PLANS_NAMES:
            combo.addItem(subject_name, subject_name)
        if selected_subject:
            index = combo.findData(selected_subject)
            if index < 0:
                combo.addItem(selected_subject, selected_subject)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
        remove_button = QPushButton("", row)
        remove_button.setProperty("actionType", "delete")
        remove_button.setFixedWidth(38)
        combo.currentIndexChanged.connect(
            lambda *_args, current_combo=combo: self._subject_changed(
                current_combo
            )
        )
        remove_button.clicked.connect(
            lambda _checked=False, current_row=row, current_combo=combo:
            self._remove_subject_row(current_row, current_combo)
        )
        row_layout.addWidget(combo, 1)
        row_layout.addWidget(remove_button)
        self.subjects_layout.addWidget(row)
        self._previous_subjects[combo] = combo.currentData()
        return combo

    def _subject_changed(self, combo):
        if self._loading:
            return
        value = combo.currentData()
        selected = [
            item.currentData()
            for item in self._subject_combos()
            if item.currentData()
        ]
        previous_value = self._previous_subjects.get(combo)
        if not value and previous_value and not selected:
            combo.blockSignals(True)
            index = combo.findData(previous_value)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
            QMessageBox.warning(
                self,
                "مادة التدريس مطلوبة",
                "يجب اختيار مادة تدريس واحدة على الأقل للقسم.",
            )
            return
        self._previous_subjects[combo] = value
        if value and not any(
            not item.currentData() for item in self._subject_combos()
        ):
            self._add_subject_row()
        self.changed.emit()

    def _subject_combos(self):
        combos = []
        for index in range(self.subjects_layout.count()):
            row = self.subjects_layout.itemAt(index).widget()
            if row is not None:
                combo = row.findChild(QComboBox)
                if combo is not None:
                    combos.append(combo)
        return combos

    def _remove_subject_row(self, row, combo):
        if combo.currentData() and sum(
            bool(item.currentData()) for item in self._subject_combos()
        ) <= 1:
            QMessageBox.warning(
                self,
                "مادة التدريس مطلوبة",
                "يجب اختيار مادة تدريس واحدة على الأقل للقسم.",
            )
            return
        self.subjects_layout.removeWidget(row)
        self._previous_subjects.pop(combo, None)
        row.deleteLater()
        if not any(
            not item.currentData() for item in self._subject_combos()
        ):
            self._add_subject_row()
        self.changed.emit()

    def assignment_values(self):
        selected_level = self.level_combo.currentData()
        class_name = self.class_combo.currentText().strip()
        class_group_key = None
        if (
            isinstance(selected_level, str)
            and selected_level.startswith("group:")
        ):
            class_group_key = selected_level[len("group:"):].strip()
            group = self.db.class_groups().get(class_group_key)
            if group is None or not group["classes"]:
                return None
            level_ids_by_name = {
                name: level_id for level_id, name in self.db.levels()
            }
            level_id = level_ids_by_name.get(
                group["classes"][0]["level_name"]
            )
            if level_id is None:
                return None
        else:
            level_id = selected_level
        subjects = list(dict.fromkeys(
            combo.currentData()
            for combo in self._subject_combos()
            if combo.currentData()
        ))
        if level_id is None or not class_name or not subjects:
            return None
        return {
            "id": str(self.assignment.setdefault("id", uuid.uuid4().hex)),
            "level_id": level_id,
            "class_name": class_name,
            "subjects": subjects,
            "class_group_key": class_group_key,
        }


class CulturalClubCountDelegate(QStyledItemDelegate):
    def createEditor(self, parent, _option, _index):
        editor = QSpinBox(parent)
        editor.setRange(0, 100000)
        return editor

    def setEditorData(self, editor, index):
        try:
            value = int(index.data(Qt.ItemDataRole.EditRole) or 0)
        except (TypeError, ValueError):
            value = 0
        editor.setValue(value)

    def setModelData(self, editor, model, index):
        model.setData(
            index,
            str(editor.value()),
            Qt.ItemDataRole.EditRole,
        )


class CulturalClubDialog(QDialog):
    CLUB_TYPES = ("ثقافي", "ثقافي - فني", "صحي", "علمي")

    def __init__(
        self, club=None, parent=None, embedded=False,
        small_window_profile=None,
    ):
        super().__init__(parent)
        self.club = club or {}
        self.embedded = embedded
        self._small_window_profile = (
            bool(small_window_profile)
            if small_window_profile is not None
            else embedded and is_small_window(
                parent if parent is not None else self
            )
        )
        self.setWindowTitle(
            "تعديل النادي" if club else "إضافة نادٍ"
        )
        self.setLayoutDirection(Qt.RightToLeft)
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        else:
            self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(str(self.club.get("name") or ""))
        self.description_edit = QTextEdit()
        self.description_edit.setPlainText(
            str(self.club.get("description") or "")
        )
        self.description_edit.setFixedHeight(72)
        self.type_combo = QComboBox()
        self.type_combo.addItems(self.CLUB_TYPES)
        club_type = self.club.get("club_type")
        if club_type:
            self.type_combo.setCurrentText(club_type)
        self.duration_combo = QComboBox()
        self.duration_combo.addItem("60 دقيقة", 60)
        self.duration_combo.addItem("120 دقيقة", 120)
        duration_index = self.duration_combo.findData(
            self.club.get("session_duration_minutes", 60)
        )
        if duration_index >= 0:
            self.duration_combo.setCurrentIndex(duration_index)
        form.addRow("اسم النادي:", self.name_edit)
        form.addRow("وصف النادي:", self.description_edit)
        form.addRow("نوع النادي:", self.type_combo)
        form.addRow("مدة الحصة:", self.duration_combo)
        layout.addLayout(form)

        layout.addWidget(QLabel("توزيع المشاركين حسب الأقسام:"))
        self.sections_table = QTableWidget(0, 3, self)
        self.sections_table.setHorizontalHeaderLabels(
            ("القسم", "عدد الإناث", "عدد الذكور")
        )
        self.sections_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.sections_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.sections_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.sections_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.count_delegate = CulturalClubCountDelegate(
            self.sections_table
        )
        self.sections_table.setItemDelegateForColumn(
            1, self.count_delegate
        )
        self.sections_table.setItemDelegateForColumn(
            2, self.count_delegate
        )
        layout.addWidget(self.sections_table)

        section_actions = QHBoxLayout()
        add_section = QPushButton("إضافة قسم")
        add_section.setProperty("actionType", "add")
        remove_section = QPushButton("حذف القسم المحدد")
        remove_section.setProperty("actionType", "delete")
        if self._small_window_profile:
            _configure_compact_club_action(
                add_section, "add", "إضافة قسم"
            )
            _configure_compact_club_action(
                remove_section, "delete", "حذف القسم المحدد"
            )
        add_section.clicked.connect(self.add_section_row)
        remove_section.clicked.connect(self.remove_selected_section)
        if self._small_window_profile:
            section_actions.addStretch(1)
        section_actions.addWidget(add_section)
        section_actions.addWidget(remove_section)
        if self._small_window_profile:
            section_actions.addStretch(1)
        layout.addLayout(section_actions)

        if not embedded:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Save
                | QDialogButtonBox.StandardButton.Cancel
            )
            set_dialog_button_action_types(buttons)
            buttons.accepted.connect(self._accept_if_valid)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        for section in self.club.get("sections", []):
            self.add_section_row(section)
        if not self.sections_table.rowCount():
            self.add_section_row()

    def add_section_row(self, section=None):
        section = section or {}
        row = self.sections_table.rowCount()
        self.sections_table.insertRow(row)
        self.sections_table.setItem(
            row, 0,
            QTableWidgetItem(str(section.get("section_name") or "")),
        )
        for column, key in ((1, "female_count"), (2, "male_count")):
            count_item = QTableWidgetItem(str(int(section.get(key) or 0)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sections_table.setItem(row, column, count_item)
        self.sections_table.setCurrentCell(row, 0)
        self.sections_table.scrollToBottom()

    def remove_selected_section(self):
        row = self.sections_table.currentRow()
        if row >= 0:
            self.sections_table.removeRow(row)

    def values(self):
        sections = []
        for row in range(self.sections_table.rowCount()):
            section_name = self.sections_table.item(row, 0)
            female_count = self.sections_table.item(row, 1)
            male_count = self.sections_table.item(row, 2)
            try:
                female_value = int(female_count.text()) if female_count else 0
                male_value = int(male_count.text()) if male_count else 0
            except ValueError:
                female_value = male_value = 0
            sections.append({
                "section_name": section_name.text() if section_name else "",
                "female_count": female_value,
                "male_count": male_value,
            })
        return {
            "name": self.name_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "club_type": self.type_combo.currentText(),
            "session_duration_minutes": self.duration_combo.currentData(),
            "sections": sections,
        }

    def set_club(self, club=None):
        self.club = club or {}
        self.name_edit.setText(str(self.club.get("name") or ""))
        self.description_edit.setPlainText(
            str(self.club.get("description") or "")
        )
        club_type = self.club.get("club_type")
        type_index = self.type_combo.findText(club_type or self.CLUB_TYPES[0])
        if type_index >= 0:
            self.type_combo.setCurrentIndex(type_index)
        duration_index = self.duration_combo.findData(
            self.club.get("session_duration_minutes", 60)
        )
        if duration_index >= 0:
            self.duration_combo.setCurrentIndex(duration_index)
        self.sections_table.setRowCount(0)
        for section in self.club.get("sections", []):
            self.add_section_row(section)
        if not self.sections_table.rowCount():
            self.add_section_row()

    def validation_error(self):
        data = self.values()
        if not data["name"]:
            return "أدخل اسم النادي."
        if not data["sections"] or any(
            not section["section_name"] for section in data["sections"]
        ):
            return "أدخل اسم قسم لكل صف أو احذف الصف الفارغ."
        seen_sections = set()
        for section in data["sections"]:
            normalized = section["section_name"].casefold()
            if normalized in seen_sections:
                return f"القسم «{section['section_name']}» مكرر."
            seen_sections.add(normalized)
        return ""

    def _accept_if_valid(self):
        error = self.validation_error()
        if error:
            QMessageBox.warning(self, "بيانات غير مكتملة", error)
            return
        self.accept()


class MonthlyClubPropertyEditor(QWidget):
    removed = Signal(object)
    PROPERTY_OPTIONS = (
        "الأدوات", "الأهداف", "الملاحظات", "المواد المستخدمة",
    )

    class ValueEdit(AutoCompletionTextEdit):
        editing_started = Signal()

        def focusInEvent(self, event):
            super().focusInEvent(event)
            self.editing_started.emit()

    def __init__(
        self, db, club_id, key_name, value_text="", required=False,
        parent=None,
    ):
        super().__init__(parent)
        self.required = required
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.setDirection(QBoxLayout.Direction.RightToLeft)
        header.addWidget(QLabel("الخاصية الرئيسية" if required else "خاصية إضافية"))
        self.key_combo = QComboBox(self)
        self.key_combo.setEditable(not required)
        if required:
            self.key_combo.addItem("المحتوى")
        else:
            self.key_combo.addItems(self.PROPERTY_OPTIONS)
            self.key_combo.setCurrentText(key_name or "الأدوات")
        header.addWidget(self.key_combo)
        self.remove_button = None
        if not required:
            self.remove_button = QToolButton(self)
            self.remove_button.setText("")
            set_card_action_type(self.remove_button, "delete")
            self.remove_button.setToolTip("حذف الخاصية")
            self.remove_button.setAccessibleName("حذف الخاصية")
            self.remove_button.setFixedSize(28, 28)
            self.remove_button.clicked.connect(
                lambda: self.removed.emit(self)
            )
            header.addWidget(self.remove_button)
        header.addStretch(1)
        layout.addLayout(header)

        self.value_edit = self.ValueEdit(
            db,
            self.key_combo,
            f"نادي:{club_id}",
            self,
            completion_source="monthly_club",
            completion_scope_id=club_id,
            allow_inline_completion=False,
        )
        self.value_edit.setPlaceholderText(
            "اكتب محتوى الجلسة" if required else "اكتب قيمة الخاصية"
        )
        self.value_edit.setFixedHeight(86 if required else 62)
        layout.addWidget(self.value_edit)
        self.key_combo.currentTextChanged.connect(
            self.value_edit.refresh_for_key_change
        )
        self.value_edit.setPlainText(value_text or "")

    def set_club_id(self, club_id):
        self.value_edit.activity_title = f"نادي:{club_id}"
        self.value_edit.set_completion_scope("monthly_club", club_id)

    def values(self):
        return {
            "key_name": self.key_combo.currentText().strip(),
            "value_text": self.value_edit.toPlainText().strip(),
        }


class MonthlyClubSessionEditor(QFrame):
    removed = Signal(object)
    property_editing_started = Signal(object)
    property_suggestions_ready = Signal(object, object)

    def __init__(
        self, db, club_id, session_date, month_date, parent=None,
        show_remove=True, show_date=True,
    ):
        super().__init__(parent)
        self.db = db
        self.club_id = club_id
        self.optional_properties = []
        self.setObjectName("monthlyClubSessionCard")
        self.setStyleSheet(
            "QFrame#monthlyClubSessionCard { background:#FFFFFF; "
            "border:1px solid #CBD5E1; border-radius:8px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(QLabel("الموعد المقترح"))
        self.date_edit = QDateEdit(session_date, self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dddd، dd/MM/yyyy")
        self.date_edit.setLocale(QLocale(QLocale.Arabic, QLocale.Tunisia))
        header.addWidget(self.date_edit, 1)
        if show_remove:
            self.remove_button = QPushButton("حذف الجلسة", self)
            self.remove_button.setProperty("actionType", "delete")
            self.remove_button.clicked.connect(
                lambda: self.removed.emit(self)
            )
            header.addWidget(self.remove_button)
        if show_date:
            layout.addLayout(header)
        else:
            self.date_edit.hide()

        self.properties_layout = QVBoxLayout()
        self.properties_layout.setSpacing(8)
        self.content_editor = MonthlyClubPropertyEditor(
            db, club_id, "المحتوى", required=True, parent=self
        )
        self._connect_property_editor(self.content_editor)
        self.properties_layout.addWidget(self.content_editor)
        layout.addLayout(self.properties_layout)
        self.add_property_button = QPushButton("إضافة خاصية")
        self.add_property_button.setProperty("actionType", "add")
        self.add_property_button.clicked.connect(self.add_property)
        layout.addWidget(
            self.add_property_button, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.set_month(month_date)
        self.add_property()

    def set_month(self, month_date):
        first_day = QDate(month_date.year(), month_date.month(), 1)
        last_day = first_day.addMonths(1).addDays(-1)
        self.date_edit.setDateRange(first_day, last_day)
        if not first_day <= self.date_edit.date() <= last_day:
            self.date_edit.setDate(first_day)

    def add_property(self, key_name="الأدوات", value_text=""):
        editor = MonthlyClubPropertyEditor(
            self.db, self.club_id, key_name, value_text, parent=self
        )
        self._connect_property_editor(editor)
        editor.removed.connect(self.remove_property)
        self.optional_properties.append(editor)
        self.properties_layout.addWidget(editor)
        return editor

    def _connect_property_editor(self, editor):
        editor.value_edit.editing_started.connect(
            lambda editor=editor: self.property_editing_started.emit(editor)
        )
        editor.value_edit.suggestions_ready.connect(
            lambda suggestions, editor=editor:
                self.property_suggestions_ready.emit(editor, suggestions)
        )

    def remove_property(self, editor):
        if editor not in self.optional_properties:
            return
        self.optional_properties.remove(editor)
        self.properties_layout.removeWidget(editor)
        editor.deleteLater()

    def set_club_id(self, club_id):
        self.club_id = club_id
        self.content_editor.set_club_id(club_id)
        for editor in self.optional_properties:
            editor.set_club_id(club_id)

    def set_values(self, session):
        session_date = QDate.fromString(
            str(session.get("session_date") or ""), "yyyy-MM-dd"
        )
        if session_date.isValid():
            self.date_edit.setDate(session_date)
        properties = session.get("properties", [])
        self.content_editor.value_edit.setPlainText(next((
            prop.get("value_text", "")
            for prop in properties
            if str(prop.get("key_name") or "").strip() == "المحتوى"
        ), ""))
        for editor in self.optional_properties:
            self.properties_layout.removeWidget(editor)
            editor.deleteLater()
        self.optional_properties.clear()
        for prop in properties:
            key_name = str(prop.get("key_name") or "").strip()
            if key_name == "المحتوى":
                continue
            self.add_property(key_name, prop.get("value_text", ""))
        if not self.optional_properties:
            self.add_property()

    def validation_error(self):
        if not self.content_editor.values()["value_text"]:
            return "أدخل محتوى الجلسة."
        seen_keys = {"المحتوى"}
        for editor in self.optional_properties:
            data = editor.values()
            if not data["value_text"]:
                continue
            if not data["key_name"]:
                return "أكمل اسم الخاصية وقيمتها أو احذف صف الخاصية الفارغ."
            normalized_key = data["key_name"].casefold()
            if normalized_key in seen_keys:
                return f"الخاصية «{data['key_name']}» مكررة في الجلسة."
            seen_keys.add(normalized_key)
        return ""

    def values(self):
        properties = [self.content_editor.values()]
        for editor in self.optional_properties:
            data = editor.values()
            if data["key_name"] and data["value_text"]:
                properties.append(data)
        return {
            "session_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "properties": properties,
        }


class MonthlyClubSessionDetailsDialog(QDialog):
    def __init__(
        self, db, club_id, session, session_number, session_count,
        month, parent=None,
    ):
        super().__init__(parent)
        month_date = QDate.fromString(f"{month}-01", "yyyy-MM-dd")
        month_label = (
            QLocale(QLocale.Language.Arabic, QLocale.Country.Tunisia).toString(
                month_date, "MMMM yyyy"
            )
            if month_date.isValid() else str(month or "")
        )
        self.setWindowTitle(f"بيانات حصة النادي — {month_label}")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setObjectName("monthlyClubSessionDetailsDialog")
        self.setMinimumSize(620, 500)
        self.resize(760, 620)

        layout = QVBoxLayout(self)
        heading = QLabel(
            f"{month_label} — الحصة {session_number} / {session_count}"
        )
        heading.setStyleSheet(
            "font-size:15px; font-weight:700; color:#1E3A8A;"
        )
        layout.addWidget(heading)
        layout.addWidget(QLabel(
            "راجع محتوى الحصة وخصائصها، ويمكنك تعديلها قبل الإضافة."
        ))

        if not month_date.isValid():
            month_date = QDate.currentDate()
        session_date = QDate.fromString(
            str(session.get("session_date") or ""), "yyyy-MM-dd"
        )
        self.session_editor = MonthlyClubSessionEditor(
            db,
            club_id,
            session_date,
            month_date,
            self,
            show_remove=False,
            show_date=False,
        )
        self.session_editor.set_values(session)
        session_scroll = QScrollArea(self)
        session_scroll.setWidgetResizable(True)
        session_scroll.setWidget(self.session_editor)
        layout.addWidget(session_scroll, 1)

        self.suggestions_window = QDialog(
            self,
            Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.suggestions_window.setObjectName(
            "monthlyClubSuggestionsWindow"
        )
        self.suggestions_window.setWindowTitle("اقتراحات قيم الخصائص")
        self.suggestions_window.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )
        self.suggestions_window.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating, True
        )
        self.suggestions_window.setMinimumSize(260, 360)
        self.suggestions_window.resize(280, 440)
        suggestions_layout = QVBoxLayout(self.suggestions_window)
        suggestions_layout.setContentsMargins(8, 8, 8, 8)
        suggestions_layout.setSpacing(6)
        suggestions_heading = QLabel("اقتراحات القيم")
        suggestions_heading.setStyleSheet("font-weight:700;")
        suggestions_layout.addWidget(suggestions_heading)
        self.suggestions_property_label = QLabel()
        self.suggestions_property_label.setWordWrap(True)
        suggestions_layout.addWidget(self.suggestions_property_label)
        self.suggestions_status_label = QLabel(
            "ابدأ تعديل قيمة خاصية لعرض الاقتراحات."
        )
        self.suggestions_status_label.setWordWrap(True)
        suggestions_layout.addWidget(self.suggestions_status_label)
        self.suggestions_list = QListWidget(self.suggestions_window)
        self.suggestions_list.setObjectName(
            "monthlyClubAutocompleteSuggestions"
        )
        suggestions_layout.addWidget(self.suggestions_list, 1)
        self.suggestions_list.itemClicked.connect(
            self._apply_suggestion
        )
        self.suggestions_window.hide()
        self.finished.connect(self.suggestions_window.close)

        self._active_suggestion_editor = None
        self.session_editor.property_editing_started.connect(
            self._show_property_suggestions
        )
        self.session_editor.property_suggestions_ready.connect(
            self._update_property_suggestions
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "إضافة الحصة"
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setProperty("actionType", "add")
        save_button.setProperty("responsiveTextRequired", True)
        save_button.setMinimumWidth(150)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setProperty("actionType", "cancel")
        cancel_button.setProperty("responsiveTextRequired", True)
        cancel_button.setMinimumWidth(120)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        set_dialog_button_action_types(buttons)
        layout.addWidget(buttons)

    def moveEvent(self, event):
        super().moveEvent(event)
        if (
            hasattr(self, "suggestions_window")
            and self.suggestions_window.isVisible()
        ):
            self._position_suggestions_window()

    def _show_property_suggestions(self, editor):
        self._active_suggestion_editor = editor
        self.suggestions_property_label.setText(
            f"الخاصية: {editor.key_combo.currentText().strip()}"
        )
        self.suggestions_list.clear()
        self.suggestions_status_label.setText("جار تحميل الاقتراحات...")
        self.suggestions_status_label.show()
        if not self.suggestions_window.isVisible():
            self._position_suggestions_window()
            self.suggestions_window.show()
        editor.value_edit.schedule_completion(allow_completion=False)

    def _position_suggestions_window(self):
        screen_geometry = self.screen().availableGeometry()
        dialog_geometry = self.frameGeometry()
        window_size = self.suggestions_window.size()
        x = dialog_geometry.right() + 6
        if x + window_size.width() > screen_geometry.right() + 1:
            x = dialog_geometry.left() - window_size.width() - 6
        x = max(
            screen_geometry.left(),
            min(x, screen_geometry.right() - window_size.width() + 1),
        )
        y = max(
            screen_geometry.top(),
            min(
                dialog_geometry.top(),
                screen_geometry.bottom() - window_size.height() + 1,
            ),
        )
        self.suggestions_window.move(x, y)

    def _update_property_suggestions(self, editor, suggestions):
        if editor is not self._active_suggestion_editor:
            return
        self.suggestions_list.clear()
        for value, score in suggestions:
            item = QListWidgetItem(value)
            item.setToolTip(f"درجة التشابه: {score:.0%}")
            self.suggestions_list.addItem(item)
        has_suggestions = bool(suggestions)
        self.suggestions_status_label.setVisible(not has_suggestions)
        if not has_suggestions:
            status = (
                "تعذر تحميل الاقتراحات."
                if editor.value_edit.completion_failed
                else "لا توجد اقتراحات مطابقة."
            )
            self.suggestions_status_label.setText(status)

    def _apply_suggestion(self, item):
        editor = self._active_suggestion_editor
        if editor is None:
            return
        editor.value_edit.setPlainText(item.text())
        editor.value_edit.moveCursor(QTextCursor.MoveOperation.End)
        editor.value_edit.setFocus()

    def _accept_if_valid(self):
        error = self.session_editor.validation_error()
        if error:
            QMessageBox.warning(self, "بيانات الحصة غير مكتملة", error)
            return
        self.accept()

    def values(self):
        return self.session_editor.values()["properties"]


class MonthlyClubSessionSelectionDialog(QDialog):
    def __init__(
        self, sessions, month, selected_session_number=None, parent=None,
    ):
        super().__init__(parent)
        month_date = QDate.fromString(f"{month}-01", "yyyy-MM-dd")
        self.month_label = (
            QLocale(QLocale.Language.Arabic, QLocale.Country.Tunisia).toString(
                month_date, "MMMM yyyy"
            )
            if month_date.isValid() else str(month or "")
        )
        self.sessions = list(sessions)
        self.setWindowTitle(
            f"اختيار حصة النادي — {self.month_label}"
        )
        self.setObjectName("monthlyClubSessionSelectionDialog")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(600, 420)
        self.resize(720, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(f"حصص مخطط شهر {self.month_label}")
        heading.setStyleSheet(
            "font-size:15px; font-weight:700; color:#1E3A8A;"
        )
        layout.addWidget(heading)
        layout.addWidget(QLabel("اختر رقم الحصة لعرض بياناتها وتعديلها."))

        self.session_list = QListWidget(self)
        self.session_list.setObjectName("monthlyClubSessionSelectionList")
        self.session_list.setWordWrap(True)
        self.session_list.setSpacing(6)
        for index, session in enumerate(self.sessions, start=1):
            properties = session.get("properties", [])
            content = next((
                str(prop.get("value_text") or "").strip()
                for prop in properties
                if str(prop.get("key_name") or "").strip() == "المحتوى"
            ), "")
            item = QListWidgetItem(
                f"الحصة {index} / {len(self.sessions)}"
                + (f"\n{content}" if content else "")
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setData(Qt.ItemDataRole.UserRole + 1, session)
            item.setToolTip("\n".join(
                f"{prop.get('key_name')}: {prop.get('value_text')}"
                for prop in properties
            ))
            item.setSizeHint(QSize(560, 66 if content else 48))
            self.session_list.addItem(item)
        try:
            selected_session_number = int(selected_session_number)
        except (TypeError, ValueError):
            selected_session_number = None
        if selected_session_number is None:
            self.session_list.setCurrentRow(0)
        elif 1 <= selected_session_number <= len(self.sessions):
            self.session_list.setCurrentRow(selected_session_number - 1)
        else:
            self.session_list.setCurrentRow(-1)
        self.session_list.itemDoubleClicked.connect(
            lambda _item: self._accept_add()
        )
        layout.addWidget(self.session_list, 1)

        buttons = QDialogButtonBox(self)
        self.add_button = buttons.addButton(
            "إضافة", QDialogButtonBox.AcceptRole
        )
        self.edit_button = buttons.addButton(
            "تعديل", QDialogButtonBox.ActionRole
        )
        self.cancel_button = buttons.addButton(
            "إلغاء", QDialogButtonBox.RejectRole
        )
        self.add_button.setProperty("actionType", "add")
        self.edit_button.setProperty("actionType", "edit")
        self.cancel_button.setProperty("actionType", "cancel")
        for button in (
            self.add_button, self.edit_button, self.cancel_button
        ):
            button.setProperty("responsiveTextRequired", True)
            button.setMinimumWidth(120)
        self._selected_action = None
        buttons.accepted.connect(self._accept_add)
        self.edit_button.clicked.connect(self._accept_edit)
        buttons.rejected.connect(self.reject)
        self.session_list.currentRowChanged.connect(
            self._update_action_buttons
        )
        self._update_action_buttons(self.session_list.currentRow())
        set_dialog_button_action_types(buttons)
        layout.addWidget(buttons)

    def _update_action_buttons(self, row):
        has_selection = row >= 0
        self.add_button.setEnabled(has_selection)
        self.edit_button.setEnabled(has_selection)

    def _accept_add(self):
        if self.session_list.currentItem() is None:
            return
        self._selected_action = "add"
        self.accept()

    def _accept_edit(self):
        if self.session_list.currentItem() is None:
            return
        self._selected_action = "edit"
        self.accept()

    def selected_action(self):
        return self._selected_action

    def selected_session(self):
        item = self.session_list.currentItem()
        if item is None:
            return None, None
        return (
            int(item.data(Qt.ItemDataRole.UserRole)),
            item.data(Qt.ItemDataRole.UserRole + 1),
        )


class MonthlyClubSavedSessionCard(QFrame):
    editRequested = Signal(int)
    removeRequested = Signal(int)

    def __init__(self, session, index, parent=None):
        super().__init__(parent)
        self.setObjectName("monthlyClubSavedSessionCard")
        self.setMinimumWidth(320)
        self.setStyleSheet(
            "QFrame#monthlyClubSavedSessionCard { background:#FFFFFF; "
            "border:1px solid #CBD5E1; border-radius:8px; }"
        )
        self.edit_button = QToolButton(self)
        self.edit_button.setText("")
        set_card_action_type(self.edit_button, "edit")
        self.edit_button.setToolTip("تعديل الجلسة")
        self.edit_button.setAccessibleName("تعديل الجلسة")
        self.edit_button.setFixedSize(28, 28)
        self.edit_button.clicked.connect(
            lambda: self.editRequested.emit(index)
        )
        self.remove_button = QToolButton(self)
        self.remove_button.setText("")
        set_card_action_type(self.remove_button, "delete")
        self.remove_button.setToolTip("حذف الجلسة")
        self.remove_button.setAccessibleName("حذف الجلسة")
        self.remove_button.setFixedSize(28, 28)
        self.remove_button.clicked.connect(
            lambda: self.removeRequested.emit(index)
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        heading = QHBoxLayout()
        date_label = QLabel(f"الجلسة {index + 1}")
        date_label.setObjectName("monthlyClubSessionNumber")
        date_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        date_label.setStyleSheet(
            "font-weight:700; color:#1E3A8A; background:#EFF6FF;"
            "padding:4px 8px; border-radius:4px;"
        )
        heading.addWidget(date_label, 1)
        layout.addLayout(heading)
        self._property_lines = [
            f"{prop['key_name']}: {prop['value_text']}"
            for prop in session["properties"]
        ]
        self.details_label = QLabel()
        self.details_label.setObjectName("monthlyClubSessionDetails")
        self.details_label.setToolTip("\n".join(self._property_lines))
        layout.addWidget(self.details_label)
        self._update_details_preview()

    def _update_details_preview(self):
        visible_lines = self._property_lines[:3]
        if len(self._property_lines) > 3:
            visible_lines[-1] += " ..."
        metrics = QFontMetrics(self.details_label.font())
        available_width = max(1, self.details_label.contentsRect().width())
        self.details_label.setText("\n".join(
            metrics.elidedText(
                line, Qt.TextElideMode.ElideRight, available_width
            )
            for line in visible_lines
        ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_details_preview()
        self.remove_button.move(8, 8)
        self.edit_button.move(40, 8)
        self.remove_button.raise_()
        self.edit_button.raise_()


class MonthlyClubPlanDialog(QDialog):
    def __init__(self, db, year_id=None, parent=None, plan=None):
        super().__init__(parent)
        self.db = db
        self.year_id = db.year_id if year_id is None else year_id
        self.clubs = self.db.cultural_clubs(self.year_id)
        self.setObjectName("monthlyClubPlanDialog")
        self.setWindowTitle(
            "تعديل مخطط شهري للنادي" if plan else "إضافة مخطط شهري للنادي"
        )
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1000, 760)
        self.setMinimumSize(820, 560)
        self.sessions_data = []
        self._editing_session_index = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("مخطط شهري للنادي")
        title.setStyleSheet(
            "font-size:15px; font-weight:700; color:#1E3A8A;"
        )
        layout.addWidget(title)

        entry_panel = QWidget(self)
        entry_panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        entry_layout = QVBoxLayout(entry_panel)
        entry_layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.club_combo = QComboBox(self)
        self.club_combo.addItem("اختر النادي", None)
        for club in self.clubs:
            self.club_combo.addItem(
                f"{club['name']} — {club['club_type']}", club["id"]
            )
        self.month_edit = QDateEdit(QDate.currentDate(), self)
        self.month_edit.setCalendarPopup(True)
        self.month_edit.setDisplayFormat("MMMM yyyy")
        self.month_edit.setLocale(QLocale(QLocale.Arabic, QLocale.Tunisia))
        if plan:
            club_index = self.club_combo.findData(plan.get("club_id"))
            if club_index >= 0:
                self.club_combo.setCurrentIndex(club_index)
            month_date = QDate.fromString(
                f"{plan.get('month', '')}-01", "yyyy-MM-dd"
            )
            if month_date.isValid():
                self.month_edit.setDate(month_date)
            self.sessions_data = [
                {
                    "session_date": session.get("session_date", ""),
                    "properties": [
                        {
                            "key_name": prop.get("key_name", ""),
                            "value_text": prop.get("value_text", ""),
                        }
                        for prop in session.get("properties", [])
                    ],
                }
                for session in plan.get("sessions", [])
            ]
        form.addRow("النادي:", self.club_combo)
        form.addRow("الشهر:", self.month_edit)
        entry_layout.addLayout(form)

        self.session_editor = MonthlyClubSessionEditor(
            self.db,
            self.club_combo.currentData(),
            self._default_session_date(),
            self.month_edit.date(),
            entry_panel,
            show_remove=False,
        )
        entry_layout.addWidget(self.session_editor)

        self.add_session_button = QPushButton("إضافة جلسة", self)
        self.add_session_button.setProperty("actionType", "add")
        self.add_session_button.clicked.connect(self.add_session)
        entry_actions = QHBoxLayout()
        entry_actions.addStretch(1)
        entry_actions.addWidget(
            self.add_session_button, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.cancel_session_edit_button = QPushButton("إلغاء التعديل", self)
        self.cancel_session_edit_button.setProperty("actionType", "cancel")
        self.cancel_session_edit_button.clicked.connect(
            self.cancel_session_edit
        )
        self.cancel_session_edit_button.hide()
        entry_actions.addWidget(self.cancel_session_edit_button)
        entry_layout.addLayout(entry_actions)

        sessions_panel = QWidget(self)
        sessions_panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        sessions_layout = QVBoxLayout(sessions_panel)
        sessions_layout.setContentsMargins(0, 0, 0, 0)
        sessions_layout.addWidget(QLabel("الجلسات المضافة"))
        self.sessions_scroll = QScrollArea(self)
        self.sessions_scroll.setWidgetResizable(True)
        self.sessions_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sessions_container = QWidget()
        self.sessions_layout = QVBoxLayout(self.sessions_container)
        self.sessions_layout.setContentsMargins(2, 2, 2, 2)
        self.sessions_layout.setSpacing(10)
        self.sessions_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.sessions_scroll.setWidget(self.sessions_container)
        sessions_layout.addWidget(self.sessions_scroll, 1)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.content_splitter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(sessions_panel)
        self.content_splitter.addWidget(entry_panel)
        self.content_splitter.setSizes([360, 600])
        layout.addWidget(self.content_splitter, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.club_combo.currentIndexChanged.connect(self._club_changed)
        self.month_edit.dateChanged.connect(self._month_changed)
        self._render_sessions()
        self._club_changed()

    def _default_session_date(self):
        month_date = self.month_edit.date()
        today = QDate.currentDate()
        if today.year() == month_date.year() and today.month() == month_date.month():
            return today
        return QDate(month_date.year(), month_date.month(), 1)

    def add_session(self):
        error = self.session_editor.validation_error()
        if error:
            QMessageBox.warning(self, "بيانات الجلسة غير مكتملة", error)
            return
        session = self.session_editor.values()
        if self._editing_session_index is None:
            self.sessions_data.append(session)
        else:
            self.sessions_data[self._editing_session_index] = session
        self.cancel_session_edit()
        self._render_sessions()

    def _render_sessions(self):
        while self.sessions_layout.count():
            item = self.sessions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.sessions_data:
            empty_label = QLabel("لم تتم إضافة جلسات بعد.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sessions_layout.addWidget(empty_label)
            return
        for index, session in enumerate(self.sessions_data):
            card = MonthlyClubSavedSessionCard(
                session, index, self.sessions_container
            )
            card.editRequested.connect(self.edit_session)
            card.removeRequested.connect(self.remove_session)
            self.sessions_layout.addWidget(card)

    def edit_session(self, index):
        if not 0 <= index < len(self.sessions_data):
            return
        self._editing_session_index = index
        self.session_editor.set_values(self.sessions_data[index])
        self.add_session_button.setText("حفظ تعديل الجلسة")
        self.add_session_button.setProperty("actionType", "edit")
        self.add_session_button.style().unpolish(self.add_session_button)
        self.add_session_button.style().polish(self.add_session_button)
        self.cancel_session_edit_button.show()

    def cancel_session_edit(self):
        self._editing_session_index = None
        self.session_editor.set_values({})
        self.session_editor.date_edit.setDate(self._default_session_date())
        self.add_session_button.setText("إضافة جلسة")
        self.add_session_button.setProperty("actionType", "add")
        self.add_session_button.style().unpolish(self.add_session_button)
        self.add_session_button.style().polish(self.add_session_button)
        self.cancel_session_edit_button.hide()

    def remove_session(self, index):
        if not 0 <= index < len(self.sessions_data):
            return
        self.sessions_data.pop(index)
        if self._editing_session_index == index:
            self.cancel_session_edit()
        elif (
            self._editing_session_index is not None
            and index < self._editing_session_index
        ):
            self._editing_session_index -= 1
        self._render_sessions()

    def _club_changed(self, *_args):
        club_id = self.club_combo.currentData()
        self.session_editor.set_club_id(club_id)

    def _month_changed(self, month_date):
        self.session_editor.set_month(month_date)
        month_text = month_date.toString("yyyy-MM")
        for session in self.sessions_data:
            if not session["session_date"].startswith(month_text):
                session["session_date"] = QDate(
                    month_date.year(), month_date.month(), 1
                ).toString("yyyy-MM-dd")
        self._render_sessions()

    def _session_form_has_values(self):
        return any(
            prop["value_text"]
            for prop in self.session_editor.values()["properties"]
        )

    def values(self):
        return {
            "club_id": self.club_combo.currentData(),
            "month": self.month_edit.date().toString("yyyy-MM"),
            "sessions": [dict(session) for session in self.sessions_data],
        }

    def validation_error(self):
        if self.club_combo.currentData() is None:
            return "اختر النادي أولاً."
        if self._session_form_has_values():
            return "أضف الجلسة الحالية إلى القائمة أولاً."
        if not self.sessions_data:
            return "أضف جلسة واحدة على الأقل."
        return ""

    def _accept_if_valid(self):
        error = self.validation_error()
        if error:
            QMessageBox.warning(self, "بيانات المخطط غير مكتملة", error)
            return
        self.accept()


class TeachingAssignmentsDialog(QDialog):
    assignmentsChanged = Signal()

    def __init__(self, db, year_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.year_id = db.year_id if year_id is None else year_id
        self.setObjectName("teachingAssignmentsDialog")
        self.setWindowTitle("تحديد الأقسام والأنشطة")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1220, 900)
        self.setMinimumSize(1000, 720)
        self._small_window_profile = is_small_window(
            parent if parent is not None else self
        )
        self.setStyleSheet("""
            QDialog#teachingAssignmentsDialog {
                background: #F8FAFC;
            }
            QWidget#teachingAssignmentsSidePanel {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
            QWidget#teachingAssignmentsActivityPanel {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
        """)
        self.assignments = [
            {
                **assignment,
                "subjects": list(assignment.get("subjects", [])),
            }
            for assignment in self.db.teacher_teaching_assignments(
                self.year_id
            )
        ]
        self.selected_assignment_id = None
        self._editing_assignment_id = None

        layout = QVBoxLayout(self)
        self.portals_tabs = QTabWidget(self)
        self.portals_tabs.setObjectName("teachingAssignmentsPortals")
        official_distribution_portal = QWidget(self.portals_tabs)
        official_distribution_layout = QVBoxLayout(
            official_distribution_portal
        )
        official_distribution_layout.addWidget(QLabel(
            "اختر المستوى والقسم واضغط «إضافة قسم»، ثم اختر النشاط "
            "واضغط «إضافة» لإنشاء حصة."
        ))

        sections_panel = QWidget(self)
        sections_panel.setObjectName("teachingAssignmentsSidePanel")
        sections_layout = QVBoxLayout(sections_panel)
        sections_form = QFormLayout()
        self.level_combo = QComboBox()
        self.level_combo.addItem("اختر المستوى", None)
        for level_id, level_name in self.db.levels():
            self.level_combo.addItem(level_name, level_id)
        for group_key in self.db.class_groups():
            self.level_combo.addItem(
                level_firak_selection_label(group_key),
                f"group:{group_key}",
            )
        self.class_combo = QComboBox()
        self.class_combo.setEditable(True)
        self.class_combo.addItem("اختر القسم أو اكتب اسمه", None)
        self.level_combo.currentIndexChanged.connect(self._load_classes)
        sections_form.addRow("المستوى:", self.level_combo)
        sections_form.addRow("القسم:", self.class_combo)
        sections_layout.addLayout(sections_form)
        self.add_section_button = QPushButton("إضافة قسم")
        self.add_section_button.setProperty("actionType", "add")
        self.add_section_button.clicked.connect(self.add_section)
        sections_layout.addWidget(self.add_section_button)

        self.sections_group = QGroupBox("الأقسام", sections_panel)
        self.sections_group.setObjectName("teachingAssignmentSectionsGroup")
        sections_group_layout = QVBoxLayout(self.sections_group)
        sections_group_layout.setContentsMargins(8, 12, 8, 8)
        sections_group_layout.setSpacing(6)
        self.sections_scroll = QScrollArea(self.sections_group)
        self.sections_scroll.setObjectName("teachingAssignmentSectionsScroll")
        self.sections_scroll.setWidgetResizable(True)
        self.sections_container = QWidget()
        self.sections_layout = QGridLayout(self.sections_container)
        self.sections_layout.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        self.sections_layout.setContentsMargins(10, 10, 10, 10)
        self.sections_layout.setSpacing(14)
        self.sections_scroll.setWidget(self.sections_container)
        sections_group_layout.addWidget(self.sections_scroll)
        sections_layout.addWidget(self.sections_group, 1)

        activities_panel = QWidget(self)
        activities_panel.setObjectName("teachingAssignmentsActivityPanel")
        activities_layout = QVBoxLayout(activities_panel)
        activities_layout.setContentsMargins(14, 14, 14, 14)
        activities_layout.setSpacing(10)
        activities_title = QLabel("أنشطة التدريس للقسم المحدد")
        activities_title.setObjectName("teachingAssignmentPanelTitle")
        activities_layout.addWidget(activities_title)
        self.activity_combo = QComboBox()
        self.activity_combo.addItem("اختر النشاط", "")
        for subject_name in PLANS_NAMES:
            self.activity_combo.addItem(subject_name, subject_name)
        activities_layout.addWidget(self.activity_combo)
        self.add_activity_button = QPushButton("إضافة")
        self.add_activity_button.setProperty("actionType", "add")
        self.add_activity_button.clicked.connect(self.add_activity)
        activities_layout.addWidget(self.add_activity_button)

        self.subjects_group = QGroupBox("الأنشطة المضافة", activities_panel)
        self.subjects_group.setObjectName("teachingAssignmentSubjectsGroup")
        subjects_group_layout = QVBoxLayout(self.subjects_group)
        subjects_group_layout.setContentsMargins(8, 10, 8, 8)
        subjects_group_layout.setSpacing(6)

        self.subjects_scroll = QScrollArea(self.subjects_group)
        self.subjects_scroll.setObjectName("teachingAssignmentSubjectsScroll")
        self.subjects_scroll.setWidgetResizable(True)
        self.subjects_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.subjects_container = QWidget()
        self.subjects_container.setObjectName("teachingAssignmentSubjectsContainer")
        self.subjects_layout = QVBoxLayout(self.subjects_container)
        self.subjects_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.subjects_layout.setContentsMargins(2, 2, 2, 2)
        self.subjects_layout.setSpacing(10)
        self.subjects_scroll.setWidget(self.subjects_container)
        subjects_group_layout.addWidget(self.subjects_scroll)
        activities_layout.addWidget(self.subjects_group, 1)
        self._set_activity_controls_enabled(False)

        section_and_activity_panels = QHBoxLayout()
        section_and_activity_panels.addWidget(sections_panel, 1)
        section_and_activity_panels.addWidget(activities_panel, 1)
        official_distribution_layout.addLayout(
            section_and_activity_panels, 1
        )
        self.portals_tabs.addTab(
            official_distribution_portal,
            "التوزيع البيداغوجي الرسمي",
        )
        cultural_portal = QWidget(self.portals_tabs)
        cultural_portal.setObjectName("culturalActivitiesPortal")
        cultural_layout = QVBoxLayout(cultural_portal)
        cultural_columns = QHBoxLayout()
        cultural_columns.setDirection(QBoxLayout.Direction.RightToLeft)
        self.cultural_columns = cultural_columns
        clubs_panel = QWidget(cultural_portal)
        self.clubs_panel = clubs_panel
        clubs_panel_layout = QVBoxLayout(clubs_panel)
        clubs_panel_layout.setContentsMargins(0, 0, 0, 0)
        clubs_panel_layout.addWidget(QLabel("النوادي المضافة"))
        self.clubs_scroll = QScrollArea(cultural_portal)
        self.clubs_scroll.setWidgetResizable(True)
        self.clubs_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.clubs_container = QWidget()
        self.clubs_layout = QVBoxLayout(self.clubs_container)
        self.clubs_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.clubs_scroll.setWidget(self.clubs_container)
        clubs_panel_layout.addWidget(self.clubs_scroll, 1)
        form_panel = QWidget(cultural_portal)
        self.club_form_panel = form_panel
        form_panel_layout = QVBoxLayout(form_panel)
        form_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.club_form_title = QLabel("إضافة نادٍ")
        form_panel_layout.addWidget(self.club_form_title)
        self.club_form = CulturalClubDialog(
            parent=form_panel,
            embedded=True,
            small_window_profile=self._small_window_profile,
        )
        form_panel_layout.addWidget(self.club_form, 1)
        self.add_club_button = QPushButton(
            "" if self._small_window_profile else "إضافة نادٍ"
        )
        self.add_club_button.setProperty("actionType", "add")
        if self._small_window_profile:
            set_action_button_type(self.add_club_button, "add")
        self.add_club_button.setAccessibleName("إضافة نادٍ")
        self.add_club_button.setToolTip("إضافة نادٍ")
        self.add_club_button.clicked.connect(self.save_cultural_club_form)
        self.cancel_club_edit_button = QPushButton("إلغاء التعديل")
        self.cancel_club_edit_button.setProperty("actionType", "cancel")
        self.cancel_club_edit_button.clicked.connect(self.cancel_cultural_club_edit)
        self.cancel_club_edit_button.hide()
        if self._small_window_profile:
            _configure_compact_club_action(
                self.add_club_button, "add", "إضافة نادٍ"
            )
            _configure_compact_club_action(
                self.cancel_club_edit_button,
                "cancel",
                "إلغاء التعديل",
            )
            club_actions_layout = QHBoxLayout()
            club_actions_layout.setContentsMargins(0, 0, 0, 0)
            club_actions_layout.setSpacing(10)
            club_actions_layout.addStretch(1)
            club_actions_layout.addWidget(self.add_club_button)
            club_actions_layout.addWidget(self.cancel_club_edit_button)
            club_actions_layout.addStretch(1)
            form_panel_layout.addLayout(club_actions_layout)
        else:
            form_panel_layout.addWidget(self.add_club_button)
            form_panel_layout.addWidget(self.cancel_club_edit_button)
        cultural_columns.addWidget(clubs_panel, 3)
        cultural_columns.addWidget(form_panel, 2)
        cultural_layout.addLayout(cultural_columns, 1)
        self._editing_club_id = None
        self.portals_tabs.addTab(
            cultural_portal,
            "النوادي الثقافية والفنية والعلمية",
        )
        self.portals_tabs.currentChanged.connect(
            self._portal_changed
        )
        layout.addWidget(self.portals_tabs, 1)

        controls = QHBoxLayout()
        self.save_status = QLabel(
            "تُحفظ التعيينات والنوادي تلقائيًا."
        )
        controls.addWidget(self.save_status, 1)
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        set_dialog_button_action_types(buttons)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("إغلاق")
        buttons.button(QDialogButtonBox.StandardButton.Close).setProperty("actionType", "close")
        layout.addWidget(buttons)

        self._load_classes()
        self._render_sections()

    def _portal_changed(self, index):
        if self.portals_tabs.widget(index) is self.portals_tabs.widget(1):
            self._load_cultural_clubs()

    def _load_cultural_clubs(self):
        try:
            clubs = self.db.cultural_clubs(self.year_id)
        except sqlite3.Error as error:
            QMessageBox.warning(
                self, "تعذر تحميل النوادي", str(error)
            )
            return
        self._render_cultural_clubs(clubs)

    def _render_cultural_clubs(self, clubs):
        while self.clubs_layout.count():
            item = self.clubs_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not clubs:
            empty_label = QLabel("لم تتم إضافة نوادٍ لهذه السنة الدراسية.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #64748B; padding: 20px;")
            self.clubs_layout.addWidget(empty_label)
            return
        for club in clubs:
            card = QFrame(self.clubs_container)
            card.setObjectName("culturalClubCard")
            card.setStyleSheet(
                "QFrame#culturalClubCard { background: #EFF6FF; "
                "border: 1px solid #60A5FA; "
                "border-right: 5px solid #2563EB; border-radius: 8px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(8)
            header = QHBoxLayout()
            header.setSpacing(6)
            title = QLabel(club["name"])
            title.setStyleSheet(
                "font-weight: bold; font-size: 15px; color: #1D4ED8; "
                "text-align: center;"
            )
            title.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.addWidget(title)
            edit_button = QPushButton("")
            set_card_action_type(edit_button, "edit")
            edit_button.setToolTip("تعديل النادي")
            edit_button.setAccessibleName("تعديل النادي")
            edit_button.setFixedSize(32, 32)
            edit_button.clicked.connect(
                lambda _checked=False, record=club:
                self.edit_cultural_club(record)
            )
            delete_button = QPushButton("")
            set_card_action_type(delete_button, "delete")
            delete_button.setToolTip("حذف النادي")
            delete_button.setAccessibleName("حذف النادي")
            delete_button.setFixedSize(32, 32)
            delete_button.clicked.connect(
                lambda _checked=False, record_id=club["id"]:
                self.delete_cultural_club(record_id)
            )
            header.addWidget(edit_button)
            header.addWidget(delete_button)
            card_layout.addLayout(header)
            description = str(club.get("description") or "").strip()
            if description:
                description_label = QLabel(description)
                description_label.setWordWrap(True)
                description_label.setStyleSheet(
                    "color: #334155; text-align: center;"
                )
                description_label.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                card_layout.addWidget(description_label)
            metadata_label = QLabel(
                f"النوع: {club['club_type']}    |    "
                f"مدة الحصة: {club['session_duration_minutes']} دقيقة    |    "
                f"إجمالي المشاركين: {club['participant_count']}"
            )
            metadata_label.setStyleSheet(
                "font-weight: 600; color: #1E3A8A; "
                "background: #DBEAFE; padding: 6px 8px; "
                "border-radius: 4px; text-align: center;"
            )
            metadata_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            metadata_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            card_layout.addWidget(metadata_label)
            for section in club["sections"]:
                section_label = QLabel(
                    f"{section['section_name']}: "
                    f"{section['female_count']} إناث، "
                    f"{section['male_count']} ذكور"
                )
                section_label.setStyleSheet(
                    "color: #334155; text-align: center;"
                )
                section_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                section_label.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                card_layout.addWidget(section_label)
            self.clubs_layout.addWidget(card)

    def save_cultural_club_form(self):
        error = self.club_form.validation_error()
        if error:
            QMessageBox.warning(self, "بيانات غير مكتملة", error)
            return
        self._save_cultural_club(
            self.club_form.values(), self._editing_club_id
        )

    def edit_cultural_club(self, club):
        self._editing_club_id = club["id"]
        self.club_form.set_club(club)
        self.club_form_title.setText("تعديل النادي")
        self.add_club_button.setText(
            "" if self._small_window_profile else "حفظ التعديلات"
        )
        self.add_club_button.setAccessibleName("حفظ التعديلات")
        self.add_club_button.setToolTip("حفظ التعديلات")
        self.add_club_button.setProperty("actionType", "edit")
        if self._small_window_profile:
            _configure_compact_club_action(
                self.add_club_button, "edit", "حفظ التعديلات"
            )
        self.add_club_button.style().unpolish(self.add_club_button)
        self.add_club_button.style().polish(self.add_club_button)
        self.cancel_club_edit_button.show()

    def cancel_cultural_club_edit(self):
        self._editing_club_id = None
        self.club_form.set_club()
        self.club_form_title.setText("إضافة نادٍ")
        self.add_club_button.setText(
            "" if self._small_window_profile else "إضافة نادٍ"
        )
        self.add_club_button.setAccessibleName("إضافة نادٍ")
        self.add_club_button.setToolTip("إضافة نادٍ")
        self.add_club_button.setProperty("actionType", "add")
        if self._small_window_profile:
            _configure_compact_club_action(
                self.add_club_button, "add", "إضافة نادٍ"
            )
        self.add_club_button.style().unpolish(self.add_club_button)
        self.add_club_button.style().polish(self.add_club_button)
        self.cancel_club_edit_button.hide()

    def _save_cultural_club(self, club_data, club_id=None):
        try:
            self.db.save_cultural_club(
                self.year_id,
                club_data["name"],
                club_data["club_type"],
                club_data["session_duration_minutes"],
                club_data["sections"],
                club_id,
                description=club_data.get("description", ""),
            )
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "تعذر حفظ النادي", str(error))
            return
        self.cancel_cultural_club_edit()
        self._load_cultural_clubs()

    def delete_cultural_club(self, club_id):
        answer = QMessageBox.question(
            self, "تأكيد الحذف", "هل تريد حذف النادي المحدد؟"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.delete_cultural_club(self.year_id, club_id)
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "تعذر حذف النادي", str(error))
            return
        self._load_cultural_clubs()

    def _set_activity_controls_enabled(self, enabled):
        self.activity_combo.setEnabled(enabled)
        self.add_activity_button.setEnabled(enabled)

    def add_section(self):
        level_value = self.level_combo.currentData()
        class_name = self.class_combo.currentText().strip()
        if level_value is None or not class_name:
            QMessageBox.warning(
                self, "بيانات ناقصة", "يرجى اختيار المستوى واسم القسم."
            )
            return

        group_key = None
        if isinstance(level_value, str) and level_value.startswith("group:"):
            group_key = level_value[len("group:"):].strip()
            group = self.db.class_groups().get(group_key)
            if group is None or not group["classes"]:
                QMessageBox.warning(
                    self, "مستوى غير صالح", "فوج الأقسام المحدد غير مسجل."
                )
                return
            level_ids = {
                name: identifier for identifier, name in self.db.levels()
            }
            level_id = level_ids.get(group["classes"][0]["level_name"])
            if level_id is None:
                QMessageBox.warning(
                    self, "مستوى غير صالح", "تعذر تحديد مستوى فوج الأقسام."
                )
                return
            class_key = f"group:{group_key}"
        else:
            level_id = level_value
            class_key = f"{level_id}:{class_name.casefold()}"

        existing = next(
            (
                assignment for assignment in self.assignments
                if assignment["id"] != self._editing_assignment_id
                and (
                    f"group:{assignment.get('class_group_key')}"
                    if assignment.get("class_group_key")
                    else (
                        f"{assignment.get('level_id')}:"
                        f"{str(assignment.get('class_name', '')).casefold()}"
                    )
                ) == class_key
            ),
            None,
        )
        if existing is not None:
            self._select_assignment(existing["id"])
            return

        if self._editing_assignment_id is not None:
            assignment = next(
                (
                    item for item in self.assignments
                    if item["id"] == self._editing_assignment_id
                ),
                None,
            )
            if assignment is None:
                self._editing_assignment_id = None
                self.add_section_button.setText("إضافة قسم")
                return
            assignment.update({
                "level_id": level_id,
                "class_name": class_name,
                "class_group_key": group_key,
            })
            self._editing_assignment_id = None
            self.add_section_button.setText("إضافة قسم")
            self.add_section_button.setProperty("actionType", "add")
            self.add_section_button.style().unpolish(
                self.add_section_button
            )
            self.add_section_button.style().polish(
                self.add_section_button
            )
            if assignment["subjects"]:
                self._save_assignments()
            else:
                self._render_sections()
                self._select_assignment(assignment["id"])
            self.save_status.setText("تم تعديل بيانات القسم.")
            return

        assignment = {
            "id": uuid.uuid4().hex,
            "level_id": level_id,
            "class_name": class_name,
            "subjects": [],
            "class_group_key": group_key,
        }
        self.assignments.append(assignment)
        self._render_sections()
        self._select_assignment(assignment["id"])
        self.save_status.setText(
            "أُضيفت بطاقة القسم؛ اختر نشاطًا واضغط «إضافة» لحفظه."
        )

    def edit_section_by_id(self, assignment_id):
        assignment = next(
            (
                item for item in self.assignments
                if item["id"] == assignment_id
            ),
            None,
        )
        if assignment is None:
            return

        level_value = (
            f"group:{assignment['class_group_key']}"
            if assignment.get("class_group_key")
            else assignment["level_id"]
        )
        level_index = self.level_combo.findData(level_value)
        if level_index < 0:
            return
        self._editing_assignment_id = assignment_id
        self.level_combo.setCurrentIndex(level_index)
        self._load_classes()
        self.class_combo.setEditText(assignment["class_name"])
        self.add_section_button.setText("حفظ التعديل")
        self.add_section_button.setProperty("actionType", "save")
        self.add_section_button.style().unpolish(self.add_section_button)
        self.add_section_button.style().polish(self.add_section_button)
        self._select_assignment(assignment_id)
        self.save_status.setText("عدّل المستوى أو اسم القسم ثم احفظ التعديل.")

    def _load_classes(self, *_args):
        selected_value = self.level_combo.currentData()
        selected_name = self.class_combo.currentText()
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        if selected_value is None:
            self.class_combo.addItem("اختر المستوى أولاً", None)
        elif (
            isinstance(selected_value, str)
            and selected_value.startswith("group:")
        ):
            self.class_combo.addItem("اختر القسم أو اكتب اسمه", None)
            group_key = selected_value[len("group:"):].strip()
            if group_key in self.db.class_groups():
                self.class_combo.addItem(group_key, selected_value)
                if not selected_name or selected_name.startswith("اختر "):
                    selected_name = group_key
        else:
            self.class_combo.addItem("اختر القسم أو اكتب اسمه", None)
            for class_id, name, level_id in self.db.classes():
                if level_id == selected_value:
                    self.class_combo.addItem(name, class_id)
        index = self.class_combo.findText(
            selected_name, Qt.MatchFlag.MatchFixedString
        )
        if index >= 0:
            self.class_combo.setCurrentIndex(index)
        elif selected_name and not selected_name.startswith("اختر "):
            self.class_combo.setEditText(selected_name)
        self.class_combo.blockSignals(False)

    def _render_sections(self):
        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.assignments:
            empty_label = QLabel("أضف قسمًا ليظهر هنا.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sections_layout.addWidget(empty_label, 0, 0, 1, 2)
            return
        level_names = {
            level_id: level_name for level_id, level_name in self.db.levels()
        }
        group_labels = {
            key: level_firak_selection_label(key)
            for key in self.db.class_groups()
        }
        section_palettes = (
            ("#EFF6FF", "#2563EB"),
            ("#ECFDF5", "#059669"),
            ("#FFF7ED", "#EA580C"),
            ("#FDF4FF", "#C026D3"),
            ("#FEF2F2", "#DC2626"),
        )
        for index, assignment in enumerate(self.assignments):
            card = QWidget(self.sections_container)
            card.setObjectName("teachingAssignmentSectionCardContainer")
            card_width, card_height = (
                (124, 120)
                if self._small_window_profile
                else (154, 148)
            )
            card.setFixedSize(card_width, card_height)
            background, border = section_palettes[index % len(section_palettes)]
            card.setStyleSheet(
                "QWidget#teachingAssignmentSectionCardContainer {"
                f"background-color: {background}; border: 2px solid {border}; "
                "border-radius: 10px;"
                "}"
            )
            card_layout = QVBoxLayout(card)
            margin = 3 if self._small_window_profile else 8
            card_layout.setContentsMargins(margin, margin, margin, margin)
            card_layout.setSpacing(2 if self._small_window_profile else 8)

            remove_button = QToolButton(card)
            remove_button.setObjectName("teachingAssignmentRemoveButton")
            remove_button.setText("")
            set_card_action_type(remove_button, "delete")
            remove_button.setToolTip("حذف القسم")
            remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
            remove_button.clicked.connect(
                lambda _checked=False, assignment_id=assignment["id"]:
                self.remove_section_by_id(assignment_id)
            )
            remove_button.setFixedSize(16, 16)
            if not self._small_window_profile:
                remove_button.move(card_width - 24, 5)
                remove_button.raise_()

            edit_button = QToolButton(card)
            edit_button.setObjectName("teachingAssignmentEditButton")
            edit_button.setText("")
            set_card_action_type(edit_button, "edit")
            edit_button.setToolTip("تعديل بيانات القسم")
            edit_button.setAccessibleName("تعديل بيانات القسم")
            edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_button.clicked.connect(
                lambda _checked=False, assignment_id=assignment["id"]:
                self.edit_section_by_id(assignment_id)
            )
            edit_button.setFixedSize(16, 16)
            if not self._small_window_profile:
                edit_button.move(card_width - 46, 5)
                edit_button.raise_()

            card_text = str(assignment["class_name"])
            if not self._small_window_profile:
                card_text += (
                    "\n"
                    f"{group_labels.get(assignment.get('class_group_key')) or level_names.get(assignment['level_id'], '')}"
                )
            button = QPushButton(
                "" if self._small_window_profile else card_text
            )
            button.setObjectName("teachingAssignmentSectionCard")
            button.setCheckable(True)
            button.setChecked(
                assignment["id"] == self.selected_assignment_id
            )
            if self._small_window_profile:
                button.setProperty("compact", True)
                button.setAccessibleName(card_text)
                button.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                button.setMinimumWidth(0)
                button.setFixedWidth(card_width - 2 * margin)
                button.setFixedHeight(76)
                button.setProperty("responsiveScalePreserveWidth", True)
                text_layout = QVBoxLayout(button)
                text_layout.setContentsMargins(2, 2, 2, 2)
                text_label = QLabel(card_text, button)
                text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                text_label.setWordWrap(True)
                text_label.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
                text_label.setStyleSheet(
                    "background: transparent; border: none;"
                )
                text_layout.addWidget(text_label)
            else:
                button.setFixedSize(128, 94)
            button.clicked.connect(
                lambda _checked=False, assignment_id=assignment["id"]:
                self._select_assignment(assignment_id)
            )

            if self._small_window_profile:
                edit_button.hide()
                remove_button.hide()
                actions_menu_button = QToolButton(card)
                actions_menu_button.setObjectName(
                    "recordedLessonActionsMenu"
                )
                actions_menu_button.setText("")
                actions_menu_button.setAccessibleName("إجراءات القسم")
                actions_menu_button.setToolTip("إجراءات القسم")
                actions_menu_button.setFixedSize(24, 24)
                actions_menu_button.setAutoRaise(True)
                actions_menu_button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonIconOnly
                )
                set_action_button_type(actions_menu_button, "menu")

                actions_menu = QMenu(actions_menu_button)
                actions_menu.setObjectName(
                    "teachingAssignmentSectionActionsPopup"
                )
                actions_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                for label, action_button in (
                    ("تعديل بيانات القسم", edit_button),
                    ("حذف القسم", remove_button),
                ):
                    menu_action = QAction(
                        action_button.icon(), label, actions_menu
                    )
                    menu_action.triggered.connect(
                        lambda _checked=False, button=action_button:
                        button.click()
                    )
                    actions_menu.addAction(menu_action)
                actions_menu_button.setMenu(actions_menu)
                actions_menu_button.setPopupMode(
                    QToolButton.ToolButtonPopupMode.InstantPopup
                )
                actions_menu_button.move(card_width - 30, 3)
                actions_menu_button.raise_()

                card_layout.addWidget(button)
            else:
                card_layout.addWidget(button)
            self.sections_layout.addWidget(card, index // 3, index % 3)

    def _select_assignment(self, assignment_id):
        assignment = next(
            (
                item for item in self.assignments
                if item["id"] == assignment_id
            ),
            None,
        )
        self.selected_assignment_id = (
            assignment["id"] if assignment is not None else None
        )
        self._render_sections()
        self._render_subjects(
            assignment.get("subjects", []) if assignment else []
        )
        self._set_activity_controls_enabled(assignment is not None)

    def _render_subjects(self, subjects):
        while self.subjects_layout.count():
            item = self.subjects_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not subjects:
            empty_label = QLabel("لم يُضف أي نشاط لهذا القسم بعد.")
            empty_label.setWordWrap(True)
            self.subjects_layout.addWidget(empty_label)
            return
        activity_palettes = (
            ("#EFF6FF", "#2563EB"),
            ("#ECFDF5", "#059669"),
            ("#FFF7ED", "#EA580C"),
            ("#FDF4FF", "#C026D3"),
            ("#FEF2F2", "#DC2626"),
        )
        for index, subject in enumerate(subjects):
            row = QWidget(self)
            row.setObjectName("teachingAssignmentSubjectCard")
            background, border = activity_palettes[index % len(activity_palettes)]
            row.setStyleSheet(
                "QWidget#teachingAssignmentSubjectCard {"
                f"background-color: {background}; border: 2px solid {border}; "
                "border-radius: 10px;"
                "}"
            )
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            row_layout.setHorizontalSpacing(8)
            row_layout.setVerticalSpacing(0)
            row_layout.setColumnStretch(0, 1)
            label = QLabel(subject)
            label.setWordWrap(True)
            label.setStyleSheet("font-weight: 600;")
            remove_button = QToolButton(row)
            remove_button.setObjectName("teachingAssignmentSubjectRemoveButton")
            remove_button.setText("")
            set_card_action_type(remove_button, "delete")
            remove_button.setToolTip("حذف النشاط")
            remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
            remove_button.setFixedSize(16, 16)
            remove_button.clicked.connect(
                lambda _checked=False, name=subject:
                self.remove_activity(name)
            )
            row_layout.addWidget(label, 0, 0)
            row_layout.addWidget(
                remove_button, 0, 1,
                Qt.AlignmentFlag.AlignCenter
            )
            self.subjects_layout.addWidget(row)

    def add_activity(self):
        assignment = self._selected_assignment()
        subject = self.activity_combo.currentData()
        if assignment is None:
            QMessageBox.warning(
                self, "القسم مطلوب", "أضف قسمًا واختر بطاقته أولًا."
            )
            return
        if not subject:
            QMessageBox.warning(
                self, "النشاط مطلوب", "اختر نشاط التدريس أولًا."
            )
            return
        if subject in assignment["subjects"]:
            QMessageBox.information(
                self, "النشاط مضاف", "هذا النشاط مضاف لهذا القسم بالفعل."
            )
            return
        assignment["subjects"].append(subject)
        self._save_assignments()

    def remove_activity(self, subject):
        assignment = self._selected_assignment()
        if assignment is None or subject not in assignment["subjects"]:
            return
        assignment["subjects"].remove(subject)
        if not assignment["subjects"]:
            self.assignments.remove(assignment)
            self.selected_assignment_id = None
        self._save_assignments()

    def remove_section_by_id(self, assignment_id):
        assignment = next(
            (
                item for item in self.assignments
                if item["id"] == assignment_id
            ),
            None,
        )
        if assignment is None:
            return
        self.assignments.remove(assignment)
        if self._editing_assignment_id == assignment_id:
            self._editing_assignment_id = None
            self.add_section_button.setText("إضافة قسم")
            self.add_section_button.setProperty("actionType", "add")
            self.add_section_button.style().unpolish(
                self.add_section_button
            )
            self.add_section_button.style().polish(
                self.add_section_button
            )
        if self.selected_assignment_id == assignment_id:
            self.selected_assignment_id = None
        self._save_assignments()

    def remove_section(self):
        assignment = self._selected_assignment()
        if assignment is None:
            return
        self.remove_section_by_id(assignment["id"])

    def _selected_assignment(self):
        return next(
            (
                assignment for assignment in self.assignments
                if assignment["id"] == self.selected_assignment_id
            ),
            None,
        )

    def _save_assignments(self):
        assignments_to_save = [
            assignment for assignment in self.assignments
            if assignment["subjects"]
        ]
        try:
            self.db.save_teacher_teaching_assignments(
                assignments_to_save, self.year_id
            )
        except (ValueError, TypeError, sqlite3.Error) as error:
            QMessageBox.warning(
                self, "تعذر حفظ تعيينات التدريس", str(error)
            )
            self.assignments = [
                {
                    **assignment,
                    "subjects": list(assignment.get("subjects", [])),
                }
                for assignment in self.db.teacher_teaching_assignments(
                    self.year_id
                )
            ]
            self.selected_assignment_id = None
            self._set_activity_controls_enabled(False)
            self._render_sections()
            self._render_subjects([])
            return
        self.save_status.setText("تم حفظ النشاط تلقائيًا.")
        self._render_sections()
        self._select_assignment(self.selected_assignment_id)
        self._notify_assignment_change()

    def _notify_assignment_change(self):
        self.assignmentsChanged.emit()

        current_parent = self.parent()
        visited = set()
        while current_parent is not None and id(current_parent) not in visited:
            visited.add(id(current_parent))
            refresh_page = getattr(
                current_parent, "refresh_lesson_palette_from_database", None
            )
            if callable(refresh_page):
                refresh_page()
            plans_page = getattr(current_parent, "plans_page", None)
            refresh_plans = getattr(plans_page, "load_plans", None)
            if callable(refresh_plans):
                refresh_plans()
            timetable_page = getattr(current_parent, "timetable_page", None)
            refresh_page = getattr(
                timetable_page,
                "refresh_lesson_palette_from_database",
                None,
            )
            if callable(refresh_page):
                refresh_page()
            refresh_editor = getattr(
                current_parent,
                "_refresh_lesson_palette_from_assignments",
                None,
            )
            if callable(refresh_editor):
                refresh_editor()
            current_parent = current_parent.parent()
        QApplication.processEvents()

class LessonEntryDialog(QDialog):
    def __init__(
        self, title, df_history, weekday_num=None, default_values=None,
        parent=None, db=None, available_hours=None, reserved_hours=None,
        work_bounds=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.db = db
        self.weekday_num = weekday_num
        self.is_updating = False
        self._syncing_schedule = False
        self.available_hours = list(available_hours or [])
        self.reserved_hours = list(reserved_hours or [])
        self.work_bounds = work_bounds
        self.available_start_minutes = set()
        for interval in self.available_hours:
            try:
                self.available_start_minutes.add(
                    self._interval_start(interval)
                )
            except ValueError:
                continue
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.combo_classe = QComboBox()
        self.combo_level = QComboBox()
        self.class_level_by_name = {}
        self.group_class_names = {}
        self._refresh_assigned_class_options()

        self.combo_majal = QComboBox()
        self.combo_majal.setEditable(False)
        
        self.combo_heure = QComboBox()
        self.combo_heure.setEditable(True)
        self.combo_heure.addItems(self.available_hours)

        self.combo_time = QComboBox()
        self.combo_time.addItems(
            ["30 دقيقة", "60 دقيقة", "90 دقيقة", "120 دقيقة"]
        )
        
        self.spin_wehda = QSpinBox()
        self.spin_wehda.setRange(1, 999)
        self.spin_wehda.setValue(1)
        
        self.spin_hessa = QSpinBox()
        self.spin_hessa.setRange(1, 999)
        self.spin_hessa.setValue(1)
        
        self.combo_namat = QComboBox()
        self.combo_namat.addItems(["منهجي", "إدماج", "تقييم", "دعم وعلاج"])
        self.combo_namat.setCurrentText("منهجي")
        
        form.addRow(
            "القسم",
            add_assignment_editor(
                self.combo_classe,
                self.db,
                self,
                self._refresh_assigned_class_options,
            ),
        )
        form.addRow("المستوى الدراسي للقسم", self.combo_level)
        form.addRow("المجال", self.combo_majal)
        form.addRow("التوقيت (مثال: 08:00-09:00)", self.combo_heure)
        form.addRow("مدة الحصة", self.combo_time)
        form.addRow("الوحدة", self.spin_wehda)
        form.addRow("الحصة", self.spin_hessa)
        form.addRow("نمط التعلم", self.combo_namat)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.combo_classe.currentTextChanged.connect(self.on_classe_changed)
        self.combo_classe.currentTextChanged.connect(
            self.on_classe_level_changed
        )
        self.combo_heure.currentTextChanged.connect(self.on_heure_changed)
        self.combo_time.currentTextChanged.connect(self.on_duration_changed)
        
        default_subject = ""
        if default_values:
            if default_values[0]:
                self.combo_classe.setCurrentText(str(default_values[0]))
            if default_values[1]:
                default_subject = str(default_values[1]).strip()
            if default_values[2]:
                default_interval = str(default_values[2]).strip()
                if self.combo_heure.findText(default_interval) >= 0:
                    self.combo_heure.setCurrentText(default_interval)
            if default_values[3]:
                self.combo_time.setCurrentText(str(default_values[3]))
            if default_values[4]:
                self.spin_wehda.setValue(int(default_values[4] or 1))
            if default_values[5]:
                self.spin_hessa.setValue(int(default_values[5] or 1))
            if default_values[6]:
                self.combo_namat.setCurrentText(str(default_values[6]))
        self.on_classe_changed(self.combo_classe.currentText())
        default_domain = _domain_for_activity_name(default_subject)
        if self.combo_majal.findText(
            default_domain, Qt.MatchFlag.MatchFixedString
        ) >= 0:
            self.combo_majal.setCurrentText(default_domain)
        if self.combo_heure.currentText().strip():
            self.on_heure_changed(self.combo_heure.currentText())
        self.on_classe_level_changed(self.combo_classe.currentText())

    def _refresh_assigned_class_options(self):
        selected_name = self.combo_classe.currentText().strip()
        selected_level = self.combo_level.currentData()
        self.class_level_by_name = {}
        self.group_class_names = {}
        self.subjects_by_class_id = {}
        self.combo_classe.blockSignals(True)
        self.combo_classe.clear()
        self.combo_classe.addItem("اختر القسم", None)
        if self.db:
            for option in self.db.teaching_assignment_classes(
                include_groups=True
            ):
                class_name = str(option["name"])
                class_id = option["id"]
                self.combo_classe.addItem(class_name, class_id)
                self.class_level_by_name[class_name] = option["level_id"]
                self.subjects_by_class_id[class_id] = list(
                    option.get("subjects", [])
                )
                if option["group_key"]:
                    self.group_class_names[class_name] = option[
                        "group_key"
                    ]
        index = self.combo_classe.findText(
            selected_name, Qt.MatchFlag.MatchFixedString
        )
        self.combo_classe.setCurrentIndex(index if index >= 0 else 0)
        self.combo_classe.blockSignals(False)

        self.combo_level.blockSignals(True)
        self.combo_level.clear()
        self.combo_level.addItem("اختر المستوى", None)
        if self.db:
            for level_id, label in self.db.teaching_assignment_levels():
                self.combo_level.addItem(label, level_id)
        level_index = self.combo_level.findData(selected_level)
        self.combo_level.setCurrentIndex(
            level_index if level_index >= 0 else 0
        )
        self.combo_level.blockSignals(False)
        self.on_classe_level_changed(self.combo_classe.currentText())
        if hasattr(self, "combo_majal"):
            self.on_classe_changed(self.combo_classe.currentText())

    def on_classe_level_changed(self, class_name):
        normalized_name = class_name.strip()
        level_id = self.class_level_by_name.get(normalized_name)
        self.combo_level.setCurrentIndex(
            self.combo_level.findData(level_id)
            if level_id is not None else 0
        )

    def on_classe_changed(self, classe_text):
        if self.is_updating:
            return
        self.is_updating = True
        try:
            activities = self.subjects_by_class_id.get(
                self.combo_classe.currentData(), []
            )
            current_subject = self.combo_majal.currentText().strip()
            current_domain = _domain_for_activity_name(current_subject)
            domains = []
            for activity in activities:
                domain = _domain_for_activity_name(activity)
                if domain and domain not in domains:
                    domains.append(domain)
            self.combo_majal.blockSignals(True)
            self.combo_majal.clear()
            self.combo_majal.addItems(domains)
            if current_domain in domains:
                self.combo_majal.setCurrentText(current_domain)
            self.combo_majal.blockSignals(False)
        finally:
            self.is_updating = False

    def on_heure_changed(self, heure_text):
        if (
            self.is_updating or self._syncing_schedule
            or not heure_text.strip()
        ):
            return
        try:
            duration = self._interval_duration(heure_text)
        except ValueError:
            return
        duration_index = self.combo_time.findText(
            f"{duration} دقيقة", Qt.MatchFlag.MatchFixedString
        )
        if duration_index >= 0:
            self._syncing_schedule = True
            self.combo_time.setCurrentIndex(duration_index)
            self._syncing_schedule = False

    @staticmethod
    def _interval_start(interval):
        cleaned = (
            str(interval or "").replace("ـ", "-").replace("–", "-")
            .replace("—", "-").replace(" ", "")
        )
        parts = cleaned.split("-")
        if len(parts) != 2:
            raise ValueError("صيغة ساعة التدريس غير صالحة.")
        start = datetime.strptime(parts[0], "%H:%M")
        return start.hour * 60 + start.minute

    @staticmethod
    def _interval_duration(interval):
        cleaned = (
            str(interval or "").replace("ـ", "-").replace("–", "-")
            .replace("—", "-").replace(" ", "")
        )
        parts = cleaned.split("-")
        if len(parts) != 2:
            raise ValueError("صيغة ساعة التدريس غير صالحة.")
        start = datetime.strptime(parts[0], "%H:%M")
        end = datetime.strptime(parts[1], "%H:%M")
        duration = int((end - start).total_seconds() // 60)
        if duration <= 0:
            raise ValueError("وقت النهاية يجب أن يكون بعد البداية.")
        return duration

    def on_duration_changed(self, duration_text):
        if self._syncing_schedule or not duration_text.strip():
            return
        try:
            duration = int(duration_text.split()[0])
            current_text = self.combo_heure.currentText().strip()
            cleaned = (
                current_text.replace("ـ", "-").replace("–", "-")
                .replace("—", "-").replace(" ", "")
            )
            start_text = cleaned.split("-", 1)[0]
            start = datetime.strptime(start_text, "%H:%M")
        except (ValueError, IndexError):
            return
        end_minutes = start.hour * 60 + start.minute + duration
        if end_minutes >= 24 * 60:
            return
        end_text = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
        interval = f"{start_text}-{end_text}"
        self._syncing_schedule = True
        if self.combo_heure.findText(interval) < 0:
            self.combo_heure.addItem(interval)
        self.combo_heure.setCurrentText(interval)
        self._syncing_schedule = False

    def validate_and_accept(self):
        if self.combo_level.currentData() is None:
            QMessageBox.warning(
                self, "المستوى مطلوب",
                "يرجى اختيار المستوى الدراسي للقسم."
            )
            return
        if not self.combo_majal.currentText().strip():
            QMessageBox.warning(
                self, "المجال مطلوب",
                "يرجى اختيار مجال مرتبط بالقسم المحدد.",
            )
            return
        try:
            duration = self._interval_duration(
                self.combo_heure.currentText()
            )
            start_minute = self._interval_start(
                self.combo_heure.currentText()
            )
        except ValueError:
            QMessageBox.warning(
                self, "توقيت غير صالح",
                "أدخل فترة صحيحة بصيغة 08:00-09:00.",
            )
            return
        if duration not in (30, 60, 90, 120):
            QMessageBox.warning(
                self, "مدة غير مدعومة",
                "مدة الحصة يجب أن تكون 30 أو 60 أو 90 أو 120 دقيقة.",
            )
            return
        if self.combo_time.currentText().strip() != f"{duration} دقيقة":
            QMessageBox.warning(
                self, "المدة والتوقيت غير متطابقين",
                "تحقق من تطابق مدة الحصة مع فترة البداية والنهاية.",
            )
            return
        if (
            self.available_start_minutes
            and start_minute not in self.available_start_minutes
        ):
            QMessageBox.warning(
                self, "ساعة غير متاحة",
                "اختر بداية إحدى الفترات الشاغرة المعروضة.",
            )
            return
        try:
            _start, _end = self._interval_bounds(
                self.combo_heure.currentText()
            )
            if self.work_bounds is not None and (
                _start < self.work_bounds[0]
                or _end > self.work_bounds[1]
            ):
                QMessageBox.warning(
                    self, "خارج ساعات العمل",
                    "الفترة المحددة تقع خارج ساعات عمل المعلم.",
                )
                return
            for reserved_interval in self.reserved_hours:
                reserved_start, reserved_end = self._interval_bounds(
                    reserved_interval
                )
                if (
                    start_minute != reserved_start
                    and _start < reserved_end
                    and reserved_start < _end
                ):
                    QMessageBox.warning(
                        self, "الفترة تتعارض مع الجدول",
                        "الفترة المحددة تتداخل مع حصة أخرى في جدول الأوقات.",
                    )
                    return
        except ValueError:
            QMessageBox.warning(
                self, "توقيت غير صالح",
                "تعذر التحقق من تعارض التوقيت مع جدول الأوقات.",
            )
            return
        heure_text = self.combo_heure.currentText().strip().replace(" ", "").replace("ـ", "-")
        if "-" in heure_text:
            parts = heure_text.split("-")
            if len(parts) == 2:
                try:
                    t1 = datetime.strptime(parts[0].strip(), "%H:%M").time()
                    t2 = datetime.strptime(parts[1].strip(), "%H:%M").time()
                    work_start = time(7, 0)
                    work_end = time(17, 0)
                    if not (work_start <= t1 <= work_end and work_start <= t2 <= work_end):
                        QMessageBox.warning(self, "توقيت غير مقبول", "أوقات العمل الرسمية بين 07:00 و 17:00.")
                        return
                    if t2 <= t1:
                        QMessageBox.warning(self, "خطأ في التوقيت", "وقت النهاية يجب أن يكون بعد وقت البداية.")
                        return
                except ValueError:
                    QMessageBox.warning(self, "توقيت غير صالح", "صيغة التوقيت غير مقبولة (مثال: 08:00-09:30).")
                    return
        self.accept()

    def values(self):
        class_name = self.combo_classe.currentText().strip()
        class_name = self.group_class_names.get(class_name, class_name)
        return [
            class_name,
            self.combo_majal.currentText().strip(),
            self.combo_heure.currentText().strip(),
            self.combo_time.currentText().strip(),
            self.spin_wehda.value(),
            self.spin_hessa.value(),
            self.combo_namat.currentText().strip(),
            self.combo_level.currentData(),
        ]

    @staticmethod
    def _interval_bounds(interval):
        cleaned = (
            str(interval or "").replace("ـ", "-").replace("–", "-")
            .replace("—", "-").replace(" ", "")
        )
        parts = cleaned.split("-")
        if len(parts) != 2:
            raise ValueError("صيغة ساعة التدريس غير صالحة.")
        start = datetime.strptime(parts[0], "%H:%M")
        end = datetime.strptime(parts[1], "%H:%M")
        start_minute = start.hour * 60 + start.minute
        end_minute = end.hour * 60 + end.minute
        if end_minute <= start_minute:
            raise ValueError("وقت النهاية يجب أن يكون بعد البداية.")
        return start_minute, end_minute


class LessonScheduleEditDialog(QDialog):
    def __init__(
        self,
        hour_interval,
        unit_number,
        lesson_number,
        parent=None,
        allow_repeat=True,
        repeat_reason="",
        repeat_requested=False,
    ):
        super().__init__(parent)
        self.setWindowTitle("تعديل توقيت الحصة وأرقامها")
        self.setMinimumWidth(420)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.hour_interval_edit = QLineEdit(str(hour_interval or ""))
        self.hour_interval_edit.setPlaceholderText("08:00-09:00")
        form.addRow("ساعة التدريس", self.hour_interval_edit)

        self.unit_number_spin = QSpinBox()
        self.unit_number_spin.setRange(1, 999)
        self.unit_number_spin.setValue(int(unit_number or 1))
        form.addRow("عدد الوحدة", self.unit_number_spin)

        self.lesson_number_spin = QSpinBox()
        self.lesson_number_spin.setRange(1, 999)
        self.lesson_number_spin.setValue(int(lesson_number or 1))
        form.addRow("عدد الحصة", self.lesson_number_spin)
        layout.addLayout(form)

        self.repeat_checkbox = QCheckBox("إعادة الحصة في المرة القادمة")
        self.repeat_checkbox.setVisible(allow_repeat)
        self.repeat_checkbox.toggled.connect(self._toggle_repeat_fields)
        layout.addWidget(self.repeat_checkbox)

        self.repeat_reason_edit = QLineEdit(str(repeat_reason or ""))
        self.repeat_reason_edit.setPlaceholderText("غير مكتملة / طارئ / لم تنجح")
        self.repeat_reason_edit.setVisible(False)
        self.repeat_reason_label = QLabel("سبب إعادة الحصة:")
        self.repeat_reason_label.setVisible(False)
        self.repeat_reason_row = QWidget()
        repeat_row = QHBoxLayout(self.repeat_reason_row)
        repeat_row.setContentsMargins(0, 0, 0, 0)
        repeat_row.addWidget(self.repeat_reason_label)
        repeat_row.addWidget(self.repeat_reason_edit, 1)
        layout.addWidget(self.repeat_reason_row)

        self.confirm_checkbox = QCheckBox("أوافق على إعادة الحصة في المرة القادمة")
        self.confirm_checkbox.setChecked(repeat_requested)
        layout.addWidget(self.confirm_checkbox)
        self.repeat_checkbox.setChecked(repeat_requested)

        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_repeat_fields(self, checked):
        self.repeat_reason_label.setVisible(checked)
        self.repeat_reason_edit.setVisible(checked)
        self.confirm_checkbox.setVisible(checked)
        self.confirm_checkbox.setChecked(checked)

    def validate_and_accept(self):
        interval = self.hour_interval_edit.text().strip()
        parts = (
            interval.replace("ـ", "-")
            .replace("–", "-")
            .replace("—", "-")
            .replace(" ", "")
            .split("-")
        )
        if len(parts) != 2:
            QMessageBox.warning(
                self, "توقيت غير صالح",
                "أدخل الفترة بصيغة 08:00-09:00.",
            )
            return
        try:
            start = datetime.strptime(parts[0], "%H:%M")
            end = datetime.strptime(parts[1], "%H:%M")
        except ValueError:
            QMessageBox.warning(
                self, "توقيت غير صالح",
                "أدخل توقيتًا صحيحًا بصيغة 08:00-09:00.",
            )
            return
        if end <= start:
            QMessageBox.warning(
                self, "توقيت غير صالح",
                "يجب أن يكون وقت النهاية بعد وقت البداية.",
            )
            return
        if self.repeat_checkbox.isChecked() and not self.repeat_reason_edit.text().strip():
            QMessageBox.warning(
                self, "سبب مطلوب",
                "يرجى تحديد سبب إعادة الحصة في المرة القادمة.",
            )
            return
        if self.repeat_checkbox.isChecked() and not self.confirm_checkbox.isChecked():
            QMessageBox.warning(
                self, "موافقة مطلوبة",
                "يجب تأكيد إعادة الحصة في المرة القادمة قبل الحفظ.",
            )
            return
        self.hour_interval_edit.setText(
            f"{parts[0]}-{parts[1]}"
        )
        self.accept()

    def values(self):
        return (
            self.hour_interval_edit.text().strip(),
            self.unit_number_spin.value(),
            self.lesson_number_spin.value(),
            self.repeat_checkbox.isChecked(),
            self.repeat_reason_edit.text().strip(),
        )


class RepeatActivitiesSelectionDialog(QDialog):
    def __init__(self, activities, available_minutes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("اختيار أنشطة الإعادة")
        self.setMinimumWidth(420)
        self.setLayoutDirection(Qt.RightToLeft)
        self.available_minutes = int(available_minutes)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "اختر الأنشطة التي ستعاد في هذه الحصة. "
            "بقية الأنشطة ستبقى مؤجلة للحصة التالية."
        ))
        self.activity_list = QListWidget(self)
        for activity_id, title, activity_time in activities:
            item = QListWidgetItem(
                f"{title} — {activity_time or 'مدة غير محددة'}"
            )
            item.setData(Qt.UserRole, int(activity_id))
            item.setData(Qt.UserRole + 1, duration_minutes(activity_time))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.activity_list.addItem(item)
        self.activity_list.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.activity_list)

        self.duration_label = QLabel()
        layout.addWidget(self.duration_label)
        buttons = QDialogButtonBox()
        self.accept_button = buttons.addButton(
            "إعادة الأنشطة المحددة", QDialogButtonBox.AcceptRole
        )
        buttons.addButton("تأجيل", QDialogButtonBox.RejectRole)
        self.accept_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        set_dialog_button_action_types(buttons)
        layout.addWidget(buttons)
        self._selection_changed()

    def _selection_changed(self, *_args):
        selected_minutes = 0
        selected_count = 0
        valid = True
        for row in range(self.activity_list.count()):
            item = self.activity_list.item(row)
            if item.checkState() != Qt.Checked:
                continue
            selected_count += 1
            activity_minutes = item.data(Qt.UserRole + 1)
            if activity_minutes is None:
                valid = False
            else:
                selected_minutes += activity_minutes
        valid = (
            valid and selected_count > 0
            and selected_minutes <= self.available_minutes
        )
        self.duration_label.setText(
            f"المدة المختارة: {selected_minutes} من "
            f"{self.available_minutes} دقيقة"
        )
        self.accept_button.setEnabled(valid)

    def selected_activity_ids(self):
        return [
            int(self.activity_list.item(row).data(Qt.UserRole))
            for row in range(self.activity_list.count())
            if self.activity_list.item(row).checkState() == Qt.Checked
        ]


class LessonNumberDelegate(QStyledItemDelegate):
    NUMBER_ROLE = Qt.ItemDataRole.UserRole
    PLAN_COUNT_ROLE = Qt.ItemDataRole.UserRole + 1

    def paint(self, painter, option, index):
        ltr_option = QStyleOptionViewItem(option)
        ltr_option.direction = Qt.LeftToRight
        super().paint(painter, ltr_option, index)

    def createEditor(self, parent, _option, _index):
        editor = QLineEdit(parent)
        editor.setValidator(QIntValidator(1, 999, editor))
        return editor

    def setEditorData(self, editor, index):
        editor.setText(str(index.data(self.NUMBER_ROLE) or 1))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        try:
            lesson_number = int(editor.text().strip())
        except ValueError:
            return
        if not 1 <= lesson_number <= 999:
            return
        plan_count = index.data(self.PLAN_COUNT_ROLE)
        display_text = (
            f"{lesson_number} / {plan_count}"
            if plan_count is not None else str(lesson_number)
        )
        model.setData(index, lesson_number, self.NUMBER_ROLE)
        model.setData(index, display_text, Qt.ItemDataRole.DisplayRole)


class LearningModeDelegate(QStyledItemDelegate):
    MODES = ("منهجي", "إدماج", "تقييم", "دعم وعلاج")

    def createEditor(self, parent, _option, _index):
        editor = QComboBox(parent)
        editor.addItems(self.MODES)
        return editor

    def setEditorData(self, editor, index):
        editor.setCurrentText(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class AssignedActivityDelegate(QStyledItemDelegate):
    OPTIONS_ROLE = Qt.ItemDataRole.UserRole

    def createEditor(self, parent, _option, index):
        editor = QComboBox(parent)
        editor.addItems(index.data(self.OPTIONS_ROLE) or [])
        return editor

    def setEditorData(self, editor, index):
        editor.setCurrentText(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class BulkLessonEntryDialog(QDialog):
    @staticmethod
    def _duration_from_interval(hour_text):
        cleaned_text = str(hour_text or "").replace(" ", "").replace("ـ", "-")
        parts = cleaned_text.split("-")
        if len(parts) != 2:
            return None
        try:
            start = datetime.strptime(parts[0], "%H:%M")
            end = datetime.strptime(parts[1], "%H:%M")
        except ValueError:
            return None
        duration = int((end - start).total_seconds() // 60)
        return duration if duration > 0 else None

    def __init__(
        self, lessons, number_defaults, parent=None,
        repeat_number_defaults=None,
        learning_mode_resolver=None,
        plan_lesson_count_resolver=None,
        assigned_activity_resolver=None,
        manual_number_keys=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("إضافة كل الحصص")
        self.setObjectName("bulkLessonEntryDialog")
        self.setMinimumSize(1280, 520)
        self.setLayoutDirection(Qt.RightToLeft)

        def lesson_sort_key(lesson):
            hour_text = str(lesson[2] or "").strip().replace("ـ", "-").replace(" ", "")
            start_text = hour_text.split("-", 1)[0]
            try:
                return 0, datetime.strptime(start_text, "%H:%M").time(), hour_text
            except ValueError:
                return 1, time.max, hour_text

        self.lessons = []
        for lesson in sorted(lessons, key=lesson_sort_key):
            duration = self._duration_from_interval(lesson[2])
            if duration is not None:
                lesson = (
                    *lesson[:3], f"{duration} دقيقة", *lesson[4:]
                )
            self.lessons.append(lesson)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)
        info_label = QLabel("أدخل رقم الوحدة والحصة واختر نمط التعلم لكل حصة:")
        info_label.setObjectName("bulkLessonInfo")
        layout.addWidget(info_label)

        self.table = QTableWidget(len(self.lessons), 7)
        self.table.setHorizontalHeaderLabels([
            "القسم", "النشاط", "ساعة التدريس", "التوقيت",
            "عدد الوحدة", "عدد الحصة", "نمط التعلم"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setMinimumWidth(1230)
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.lesson_number_delegate = LessonNumberDelegate(self.table)
        self.table.setItemDelegateForColumn(
            5, self.lesson_number_delegate
        )
        self.learning_mode_delegate = LearningModeDelegate(self.table)
        self.table.setItemDelegateForColumn(
            6, self.learning_mode_delegate
        )
        self.assigned_activity_delegate = AssignedActivityDelegate(self.table)
        self.table.setItemDelegateForColumn(
            1, self.assigned_activity_delegate
        )

        self.learning_mode_resolver = learning_mode_resolver
        self.plan_lesson_count_resolver = plan_lesson_count_resolver
        self.assigned_activity_resolver = assigned_activity_resolver
        self.manual_number_keys = {
            (str(classe or "").strip(), str(majal or "").strip())
            for classe, majal in (manual_number_keys or ())
        }
        next_numbers = dict(number_defaults)
        repeat_number_defaults = repeat_number_defaults or {}
        for row, lesson in enumerate(self.lessons):
            is_cultural_club = (
                len(lesson) > 6 and lesson[6] == "cultural_club"
            )
            assigned_activities = []
            if self.assigned_activity_resolver is not None:
                try:
                    assigned_activities = list(
                        self.assigned_activity_resolver(lesson) or []
                    )
                except (sqlite3.Error, ValueError) as error:
                    QMessageBox.warning(
                        self,
                        "تعذر تحميل الأنشطة المسندة",
                        f"تعذر تحميل أنشطة القسم:\n{error}",
                    )
            for column, value in enumerate(lesson[:4]):
                display_value = value
                if column == 1:
                    scheduled_activity = (
                        str(lesson[5] or "").strip()
                        if len(lesson) > 5 else ""
                    )
                    display_value = (
                        scheduled_activity
                        if scheduled_activity in assigned_activities
                        else assigned_activities[0]
                        if assigned_activities else value
                    )
                if (
                    column == 0 and len(lesson) > 4
                    and str(lesson[4]).startswith("group:")
                ):
                    group_key = str(lesson[4])[len("group:"):]
                    display_value = (
                        f"{value} — {level_firak_label(group_key)}"
                    )
                item = QTableWidgetItem(str(display_value or ""))
                item.setTextAlignment(Qt.AlignCenter)
                if column == 1 and assigned_activities:
                    item.setData(
                        AssignedActivityDelegate.OPTIONS_ROLE,
                        assigned_activities,
                    )
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                elif column >= 4:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, column, item)

            default_unit, default_lesson = number_defaults.get(
                (str(lesson[0] or "").strip(), str(lesson[1] or "").strip()),
                (1, row + 1)
            )
            key = (str(lesson[0] or "").strip(), str(lesson[1] or "").strip())
            default_unit, default_lesson = next_numbers.get(key, (default_unit, default_lesson))
            repeat_numbers = repeat_number_defaults.get(
                tuple(str(value or "").strip() for value in lesson[:3])
            )
            if key in self.manual_number_keys and repeat_numbers is None:
                default_unit, default_lesson = 1, 1
            elif repeat_numbers is not None:
                default_unit, default_lesson = repeat_numbers
            self.table.setItem(
                row, 4, QTableWidgetItem(str(default_unit))
            )
            lesson_number = int(default_lesson)
            lesson_number_item = QTableWidgetItem()
            lesson_number_item.setData(
                LessonNumberDelegate.NUMBER_ROLE, lesson_number
            )
            lesson_number_item.setData(
                LessonNumberDelegate.PLAN_COUNT_ROLE, None
            )
            lesson_number_item.setText(str(lesson_number))
            self.table.setItem(row, 5, lesson_number_item)
            mode_item = QTableWidgetItem(
                "" if is_cultural_club else "منهجي"
            )
            mode_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_cultural_club:
                mode_item.setFlags(
                    mode_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
            self.table.setItem(row, 6, mode_item)
            if key not in self.manual_number_keys:
                lesson_duration = duration_minutes(lesson[3])
                increment = (
                    max(1, (lesson_duration + 59) // 60)
                    if "اللغة العربية" in key[1]
                    and lesson_duration is not None
                    else 1
                )
                next_numbers[key] = (
                    default_unit, default_lesson + increment
                )

        self.table.cellChanged.connect(self._lesson_number_changed)
        for row in range(self.table.rowCount()):
            self._update_lesson_number_suffix(row)
            self._auto_select_learning_mode(row)

        layout.addWidget(self.table)
        buttons = QDialogButtonBox()
        save_button = buttons.addButton("إضافة الحصص", QDialogButtonBox.AcceptRole)
        save_button.setObjectName("bulkSaveButton")
        cancel_button = buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        cancel_button.setObjectName("bulkCancelButton")
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _lesson_number_changed(self, row, column):
        if column == 4:
            self._update_lesson_number_suffix(row)
            self._auto_select_learning_mode(row)
        elif column == 5:
            self._auto_select_learning_mode(row)

    def _commit_current_editor(self):
        current_index = self.table.currentIndex()
        if not current_index.isValid():
            return
        row, column = current_index.row(), current_index.column()
        self.table.setCurrentCell(-1, -1)
        self.table.setCurrentCell(row, column)

    def _update_lesson_number_suffix(self, row):
        if self.plan_lesson_count_resolver is None:
            return
        lesson = self.lessons[row]
        try:
            unit_number = int(self.table.item(row, 4).text().strip())
            plan_lesson_count = self.plan_lesson_count_resolver(
                lesson, unit_number
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.warning(
                self,
                "تعذر قراءة المخطط",
                f"تعذر تحديد عدد حصص المخطط:\n{error}",
            )
            plan_lesson_count = None
        item = self.table.item(row, 5)
        lesson_number = item.data(LessonNumberDelegate.NUMBER_ROLE)
        item.setData(
            LessonNumberDelegate.PLAN_COUNT_ROLE,
            int(plan_lesson_count) if plan_lesson_count is not None else None,
        )
        item.setText(
            f"{lesson_number} / {int(plan_lesson_count)}"
            if plan_lesson_count is not None else str(lesson_number)
        )

    def _auto_select_learning_mode(self, row):
        if (
            len(self.lessons[row]) > 6
            and self.lessons[row][6] == "cultural_club"
        ):
            return
        if self.learning_mode_resolver is None:
            return
        lesson = self.lessons[row]
        try:
            unit_number = int(self.table.item(row, 4).text().strip())
            lesson_number = int(
                self.table.item(row, 5).data(
                    LessonNumberDelegate.NUMBER_ROLE
                )
            )
        except (AttributeError, TypeError, ValueError):
            return
        try:
            mode = self.learning_mode_resolver(
                lesson, unit_number, lesson_number
            )
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.warning(
                self,
                "تعذر تحديد نمط التعلم",
                f"تعذر البحث عن نمط التعلم في المخطط:\n{error}",
            )
            return
        if mode in ("منهجي", "إدماج", "تقييم", "دعم وعلاج"):
            self.table.item(row, 6).setText(mode)

    def validate_and_accept(self):
        self._commit_current_editor()
        for row in range(self.table.rowCount()):
            for column in (4, 5):
                item = self.table.item(row, column)
                try:
                    value = int(
                        item.text().strip() if column == 4
                        else item.data(LessonNumberDelegate.NUMBER_ROLE)
                    )
                except (AttributeError, TypeError, ValueError):
                    value = 0
                if not 1 <= value <= 999:
                    QMessageBox.warning(
                        self, "قيمة غير صالحة",
                        "يجب أن يكون عدد الوحدة ورقم الحصة بين 1 و999."
                    )
                    self.table.setCurrentCell(row, column)
                    return
        self.accept()

    def values(self):
        self._commit_current_editor()
        values = []
        for row, lesson in enumerate(self.lessons):
            is_cultural_club = (
                len(lesson) > 6 and lesson[6] == "cultural_club"
            )
            class_names = (
                lesson[7]
                if is_cultural_club and len(lesson) > 7
                else [lesson[0]]
            )
            scheduled_activity = (
                str(lesson[5] or "").strip()
                if is_cultural_club
                else self.table.item(row, 1).text().strip()
            )
            if is_cultural_club:
                values.append((
                    str(class_names[0] or "").strip(),
                    str(lesson[1] or "").strip(),
                    str(lesson[2] or "").strip(),
                    str(lesson[3] or "").strip(),
                    int(self.table.item(row, 4).text().strip()),
                    int(
                        self.table.item(row, 5).data(
                            LessonNumberDelegate.NUMBER_ROLE
                        )
                    ),
                    "",
                    None,
                    scheduled_activity,
                    [
                        str(class_name or "").strip()
                        for class_name in class_names
                        if str(class_name or "").strip()
                    ],
                ))
                continue
            for class_name in class_names:
                values.append((
                    str(class_name or "").strip(),
                    str(lesson[1] or "").strip(),
                    str(lesson[2] or "").strip(),
                    str(lesson[3] or "").strip(),
                    int(self.table.item(row, 4).text().strip()),
                    int(
                        self.table.item(row, 5).data(
                            LessonNumberDelegate.NUMBER_ROLE
                        )
                    ),
                    "" if is_cultural_club else self.table.item(row, 6).text(),
                    lesson[4] if len(lesson) > 4 else None,
                    scheduled_activity,
                ))
        return values


class EntryDialog(QDialog):
    def __init__(self, title, fields, values=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        if len(fields) > 10:
            self.setMinimumSize(1100, 650)
            self.resize(1250, 850)
        else:
            self.setMinimumWidth(480)
        self.widgets = []
        layout = QVBoxLayout(self)
        use_three_columns = len(fields) > 10
        form = QGridLayout() if use_three_columns else QFormLayout()
        if use_three_columns:
            for grid_column in range(3):
                form.setColumnStretch(grid_column, 1)
        row = 0
        column = 0
        
        for label, kind, default in fields:
            if kind in ("int", "nonnegative_int"):
                w = QSpinBox()
                w.setRange(0 if kind == "nonnegative_int" else 1, 999)
                initial_value = default if default is not None else (
                    0 if kind == "nonnegative_int" else 1
                )
                w.setValue(int(initial_value))
            elif kind in ["multiline", "plaintext"]:
                w = QTextEdit()
                w.setAcceptRichText(False)
                w.setPlainText(str(default or ""))
                w.setMinimumHeight(100)
                w.setAlignment(Qt.AlignCenter)
            elif kind == "gender":
                w = QComboBox()
                w.addItems(TEACHER_GENDER_OPTIONS)
            elif kind == "date":
                w = QLineEdit(str(default or ""))
                w.setPlaceholderText("YYYY-MM-DD")
            else:
                w = QLineEdit(str(default or ""))

            if isinstance(w, QLineEdit):
                w.setAlignment(Qt.AlignCenter)
            elif isinstance(w, QSpinBox):
                w.lineEdit().setAlignment(Qt.AlignCenter)

            self.widgets.append(w)
            if use_three_columns:
                if kind == "plaintext" and column:
                    row += 1
                    column = 0

                label_widget = QLabel(label)
                label_widget.setAlignment(Qt.AlignCenter)
                cell = QWidget()
                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.addWidget(label_widget)
                cell_layout.addWidget(w)
                if kind == "plaintext":
                    form.addWidget(cell, row, 0, 1, 3)
                    row += 1
                    column = 0
                else:
                    form.addWidget(cell, row, column)
                    column += 1
                    if column == 3:
                        row += 1
                        column = 0
            else:
                form.addRow(label, w)
            
        if values:
            for w, value in zip(self.widgets, values):
                if isinstance(w, QSpinBox):
                    w.setValue(int(
                        value if value is not None else
                        (0 if w.minimum() == 0 else 1)
                    ))
                elif isinstance(w, QTextEdit):
                    w.setPlainText(str(value or ""))
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(max(w.findText(str(value or "")), 0))
                else:
                    w.setText(str(value or ""))
                    
        layout.addLayout(form)
        
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        result = []
        for w in self.widgets:
            if isinstance(w, QSpinBox):
                result.append(w.value())
            elif isinstance(w, QTextEdit):
                result.append(w.toPlainText().strip())
            elif isinstance(w, QComboBox):
                result.append(w.currentText().strip())
            else:
                result.append(w.text().strip())
        return result


class DaySelectionDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setWindowTitle("اختيار يوم للتصدير")
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)
        self.db = db
        
        layout = QVBoxLayout(self)
        self.info_label = QLabel(
            "اختر اليوم المطلوب تصديره من التقويم أدناه:"
        )
        self.info_label.setStyleSheet(
            "font-weight: bold; color: #2c3e50; font-size: 11px;"
        )
        layout.addWidget(self.info_label)
        
        self.calendar = CustomCalendarWidget(self.db, self)
        layout.addWidget(self.calendar)
        self.calendar.setLocale(QLocale(QLocale.Arabic, QLocale.Tunisia))
        
        buttons = QDialogButtonBox()
        self.export_btn = buttons.addButton("تصدير الملف", QDialogButtonBox.AcceptRole)
        self.export_btn.setProperty("actionType", "export")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._configure_calendar_range()

    def get_selected_date_str(self):
        return self.calendar.selectedDate().toString("yyyy-MM-dd")

    def _configure_calendar_range(self):
        try:
            year_name = next(
                name for year_id, name in self.db.school_years()
                if year_id == self.db.year_id
            )
            match = re.fullmatch(
                r"\s*(\d{4})\s*-\s*(\d{4})\s*", str(year_name)
            )
            if match is None:
                raise ValueError(
                    f"اسم السنة الدراسية غير صالح: {year_name}"
                )
            first_year, second_year = map(int, match.groups())
            if second_year != first_year + 1:
                raise ValueError(
                    f"اسم السنة الدراسية غير متتالٍ: {year_name}"
                )
            first_date = QDate(first_year, 9, 1)
            last_date = QDate(second_year, 6, 30)
            self.calendar.setDateRange(first_date, last_date)

            workdays = {
                QDate.fromString(day_text, "yyyy-MM-dd")
                for _day_id, day_text in self.db.recorded_workdays(
                    self.db.year_id
                )
            }
            workdays = {
                day for day in workdays
                if day.isValid() and first_date <= day <= last_date
            }
            disabled_dates = set()
            current_date = first_date
            while current_date <= last_date:
                if current_date not in workdays:
                    disabled_dates.add(current_date)
                current_date = current_date.addDays(1)
            self.calendar.set_disabled_dates(
                disabled_dates,
                "لا يوجد يوم عمل مسجل لهذا التاريخ",
                background_color="#FFFFFF",
            )
            self.calendar.setEnabled(bool(workdays))
            self.export_btn.setEnabled(bool(workdays))
            if workdays:
                selected = self.calendar.selectedDate()
                if selected not in workdays:
                    self.calendar.setSelectedDate(min(workdays))
            else:
                self.info_label.setText(
                    "لا توجد أيام عمل مسجلة في هذه السنة الدراسية."
                )
        except (StopIteration, sqlite3.Error, TypeError, ValueError) as exc:
            self.calendar.setEnabled(False)
            self.export_btn.setEnabled(False)
            QMessageBox.critical(
                self,
                "تعذر إعداد تقويم التصدير",
                f"تعذر تحديد نطاق السنة الدراسية وأيام العمل:\n{exc}",
            )


class ActivityEntryDialog(QDialog):
    def __init__(
        self, title, majal, db, weekday, values=None, parent=None,
        lesson_id=None,
    ):
        super().__init__(parent)
        self.db = db
        self.majal = str(majal or "").strip()
        self.weekday = weekday
        self._activity_options_initialized = False
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        form = QFormLayout()
        layout = QVBoxLayout(self)

        self.class_scope_combo = QComboBox()
        self.class_scope_combo.addItem("مشترك بين المستويات", None)
        self.lesson_classes = db.lesson_classes(lesson_id) if lesson_id else []
        for class_id, class_name, level_name in self.lesson_classes:
            self.class_scope_combo.addItem(
                f"{class_name} — {level_name}", class_id
            )
        if len(self.lesson_classes) > 1:
            form.addRow("مستوى النشاط:", self.class_scope_combo)

        self.subjects_by_class_id = {}
        if hasattr(db, "teaching_assignment_classes"):
            for assignment in db.teaching_assignment_classes(
                include_groups=True
            ):
                subjects = list(assignment.get("subjects", []))
                class_ids = assignment.get(
                    "class_ids", [assignment.get("id")]
                )
                for class_id in class_ids:
                    self.subjects_by_class_id.setdefault(
                        class_id, []
                    ).extend(subjects)

        self.title_combo = QComboBox()
        self.title_combo.setEditable(True)
        
        self.time_combo = QComboBox()
        self.time_combo.setEditable(True)
        self.time_combo.addItems(["5 دقائق", "10 دقائق", "15 دقيقة", "20 دقيقة",
                                  "30 دقيقة", "45 دقيقة", "60 دقيقة"])
        form.addRow("عنوان النشاط", self.title_combo)
        form.addRow("المدة", self.time_combo)
        layout.addLayout(form)
        
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.class_scope_combo.currentIndexChanged.connect(
            self._refresh_activity_options
        )
        self.title_combo.currentTextChanged.connect(self.update_duration_suggestion)
        if values:
            self.time_combo.setCurrentText(str(values[1] or ""))
            if len(values) > 2:
                self.class_scope_combo.setCurrentIndex(
                    self.class_scope_combo.findData(values[2])
                )
        self._refresh_activity_options(
            preferred_title=values[0] if values else ""
        )

    def _refresh_activity_options(self, *_args, preferred_title=None):
        if preferred_title is None:
            preferred_title = self.title_combo.currentText().strip()
        class_id = self.class_scope_combo.currentData()
        class_ids = (
            [class_id]
            if class_id is not None
            else [row[0] for row in self.lesson_classes]
        )
        subjects = []
        for lesson_class_id in class_ids:
            for subject in self.subjects_by_class_id.get(
                lesson_class_id, []
            ):
                if subject not in subjects:
                    subjects.append(subject)

        activity_options = []
        for subject in subjects:
            plan = PLANS_NAMES.get(subject)
            if not isinstance(plan, dict):
                continue
            if str(plan.get("المجال") or "").strip() != self.majal:
                continue
            activities = plan.get("الأنشطة") or [subject]
            for activity in activities:
                activity = str(activity or "").strip()
                if activity and activity not in activity_options:
                    activity_options.append(activity)

        self.title_combo.blockSignals(True)
        self.title_combo.clear()
        self.title_combo.addItems(activity_options)
        if preferred_title in activity_options:
            self.title_combo.setCurrentText(preferred_title)
        elif not self._activity_options_initialized and preferred_title:
            self.title_combo.setCurrentText(preferred_title)
        else:
            self.title_combo.setCurrentIndex(-1)
        self.title_combo.blockSignals(False)
        self._activity_options_initialized = True

    def update_duration_suggestion(self, activity_title):
        if not activity_title.strip():
            return
        try:
            import pandas as pd

            with self.db.connect() as con:
                df = pd.read_sql_query("""
                    SELECT n.time, d.date
                    FROM nachat n
                    JOIN hessa h ON h.id = n.hessa_id
                    JOIN majal m ON m.id=h.majal_id
                    JOIN day_data d ON d.id = h.day_data_id
                    WHERE n.title = ? AND m.name = ?
                      AND COALESCE(n.time, '') <> ''
                """, con, params=(activity_title.strip(), self.majal))
            if df.empty:
                return
            dates = pd.to_datetime(df["date"], errors="coerce")
            df = df.loc[dates.dt.dayofweek == self.weekday].copy()
            if df.empty:
                return
            modes = df["time"].astype(str).mode()
            if not modes.empty:
                suggestion = modes.iloc[0]
                old = self.time_combo.currentText()
                if not old or old not in df["time"].astype(str).unique():
                    self.time_combo.setCurrentText(suggestion)
        except Exception as exc:
            print(f"Activity duration prediction error: {exc}")

    def values(self):
        return [
            self.title_combo.currentText().strip(),
            self.time_combo.currentText().strip(),
            self.class_scope_combo.currentData(),
        ]


class TargetCriteriaPickerDialog(QDialog):
    selection_changed = Signal(str)
    VALUE_PREFIX = (
        "أن يكون المتعلم قادرا على تجاوز الصعوبات المتصلة بالمعايير التالية:"
    )

    def __init__(self, records, parent=None):
        super().__init__(
            parent,
            Qt.Tool | Qt.WindowTitleHint | Qt.WindowCloseButtonHint,
        )
        self.setWindowTitle("المعايير ومؤشراتها")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(430, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "اختر مؤشرًا أو أكثر؛ ستُنظم الاختيارات تحت معاييرها."
        ))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.tree, 1)
        self.empty_label = QLabel(
            "لا توجد معايير ومؤشرات مرتبطة بهذا النشاط ومستوى القسم."
        )
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)

        level_names = {row[0]: row[1] for row in records}
        show_level_nodes = len(level_names) > 1
        level_nodes = {}
        criterion_nodes = {}
        criterion_indicators = {}
        self._criteria = []
        for (
            level_id, level_name, criterion_id, criterion,
            _criterion_order, indicator_id, indicator, _indicator_order,
            _subject,
        ) in records:
            if show_level_nodes:
                level_node = level_nodes.get(level_id)
                if level_node is None:
                    level_node = QTreeWidgetItem([str(level_name)])
                    self.tree.addTopLevelItem(level_node)
                    level_nodes[level_id] = level_node
                parent_item = level_node
            else:
                parent_item = self.tree.invisibleRootItem()

            criterion_key = (level_id, criterion_id)
            criterion_node = criterion_nodes.get(criterion_key)
            if criterion_node is None:
                criterion_node = QTreeWidgetItem([str(criterion)])
                parent_item.addChild(criterion_node)
                criterion_nodes[criterion_key] = criterion_node
                self._criteria.append((str(criterion), []))
                criterion_indicators[criterion_key] = self._criteria[-1][1]
            if indicator_id is not None:
                indicator_item = QTreeWidgetItem([str(indicator)])
                indicator_item.setFlags(
                    indicator_item.flags() | Qt.ItemIsUserCheckable
                )
                indicator_item.setCheckState(0, Qt.Unchecked)
                criterion_node.addChild(indicator_item)
                criterion_indicators[criterion_key].append(indicator_item)

        self.tree.expandAll()
        has_criteria = bool(criterion_nodes)
        self.tree.setVisible(has_criteria)
        self.empty_label.setVisible(not has_criteria)
        self.tree.itemChanged.connect(self._emit_selected_values)

    def set_selected_values(self, value):
        selected = set()
        criterion_name = None
        for line in str(value or "").splitlines():
            if line.startswith("* "):
                criterion_name = line[2:].strip()
                if criterion_name.endswith(":"):
                    criterion_name = criterion_name[:-1].rstrip()
            elif line.startswith("- "):
                criterion_name = line[2:].strip()
            elif line.startswith("  - ") and criterion_name:
                selected.add((criterion_name, line[4:].strip()))

        self.tree.blockSignals(True)
        try:
            for criterion_name, indicators in self._criteria:
                for item in indicators:
                    is_selected = (
                        criterion_name, item.text(0)
                    ) in selected
                    item.setCheckState(
                        0, Qt.Checked if is_selected else Qt.Unchecked
                    )
        finally:
            self.tree.blockSignals(False)

    def _emit_selected_values(self, item, _column):
        if not (item.flags() & Qt.ItemIsUserCheckable):
            return

        selected_criteria = []
        for criterion_name, indicators in self._criteria:
            selected = [
                indicator.text(0)
                for indicator in indicators
                if indicator.checkState(0) == Qt.Checked
            ]
            if selected:
                selected_criteria.append((criterion_name, selected))

        if not selected_criteria:
            self.selection_changed.emit("")
            return

        lines = [self.VALUE_PREFIX]
        for criterion_name, indicators in selected_criteria:
            lines.append(f"* {criterion_name}:")
            lines.extend(f"  - {indicator}" for indicator in indicators)
        self.selection_changed.emit("\n".join(lines))


class DetailEntryDialog(QDialog):
    def __init__(
        self, title, namat, activity_title, db, current_count=0, values=None,
        parent=None, contextual_content=None, default_key=None,
        activity_id=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self.db = db
        self.namat = namat or ""
        self.activity_title = activity_title or ""
        self.activity_id = activity_id
        self.contextual_content = contextual_content
        self._prediction_worker = None
        self._target_criteria_picker = None
        self._target_criteria_loaded = False
        self._updating_target_criteria = False
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.key_combo = QComboBox()
        self.key_combo.setEditable(True)
        self.key_combo.addItems(DETAIL_KEYS_BY_NAMAT.get(self.namat, []))
        if default_key and not values:
            self.key_combo.setCurrentText(default_key)
        elif not values:
            self.key_combo.setCurrentIndex(-1)
            self.key_combo.lineEdit().setPlaceholderText(
                "جارٍ توقع اسم الخاصية..."
            )

        self.value_edit = AutoCompletionTextEdit(self.db, self.key_combo, self.activity_title)
        self.value_edit.setPlaceholderText("اكتب قيمة الخاصية؛ ستظهر اقتراحات مشابهة من السجل السابق…")
        font_metrics = self.value_edit.fontMetrics()
        self.value_edit.setFixedHeight(font_metrics.lineSpacing() * 5 + 12)

        self.suggestions_panel = QFrame(
            self, Qt.Tool | Qt.FramelessWindowHint
        )
        self.suggestions_panel.setObjectName("smartSuggestionsPanel")
        self.suggestions_panel.setWindowTitle("اقتراحات ذكية")
        self.suggestions_panel.setFixedSize(400, 460)
        self.suggestions_panel.setStyleSheet(
            "#smartSuggestionsPanel {"
            "background: white; border: 1px solid #94A3B8;"
            "border-radius: 8px; }"
        )
        suggestions_layout = QVBoxLayout(self.suggestions_panel)
        suggestions_layout.setContentsMargins(8, 8, 8, 8)
        suggestions_layout.addWidget(QLabel("اقتراحات ذكية"))
        self.suggestions_hint = QLabel(
            "ستظهر الاقتراحات المناسبة هنا."
        )
        self.suggestions_hint.setWordWrap(True)
        self.suggestions_hint.setAlignment(Qt.AlignCenter)
        self.suggestions_list = QListWidget()
        self.suggestions_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.suggestions_list.setToolTip("اختر اقتراحاً لإدراجه في خانة القيمة")
        suggestions_layout.addWidget(self.suggestions_list)
        suggestions_layout.addWidget(self.suggestions_hint)
        self.suggestions_panel.hide()
        self.value_edit.textChanged.connect(self.refresh_smart_suggestions)
        self.value_edit.suggestions_ready.connect(self.show_smart_suggestions)
        self.suggestions_list.itemClicked.connect(self.apply_smart_suggestion)
        self.key_combo.currentTextChanged.connect(self.refresh_smart_suggestions)
        self.key_combo.currentTextChanged.connect(self.value_edit.refresh_for_key_change)
        self.key_combo.currentTextChanged.connect(
            self._update_contextual_completion
        )
        self.key_combo.currentTextChanged.connect(
            self._update_target_criteria_picker
        )
        form.addRow("اسم الخاصية", self.key_combo)
        form.addRow("القيمة", self.value_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if values:
            old_key, old_value = values
            self.key_combo.setCurrentText(str(old_key or ""))
            self.value_edit.setPlainText(str(old_value or ""))
        elif self.activity_title:
            self._prediction_worker = DetailKeyPredictionWorker(
                self.db, 0, self.activity_title, self.namat, current_count
            )
            self._prediction_worker.signals.predicted.connect(
                self._apply_predicted_key
            )
            self._prediction_worker.signals.failed.connect(
                self._prediction_failed
            )
            QThreadPool.globalInstance().start(self._prediction_worker)
        self._update_contextual_completion()

    def _is_target_criteria_property(self):
        return (
            self.namat.strip() == "دعم وعلاج"
            and self.key_combo.currentText().strip() == "المعايير المستهدفة"
        )

    def _update_target_criteria_picker(self, *_args):
        if not self._is_target_criteria_property():
            picker_was_visible = (
                self._target_criteria_picker is not None
                and self._target_criteria_picker.isVisible()
            )
            if self._target_criteria_picker is not None:
                self._target_criteria_picker.hide()
            if picker_was_visible and self.isVisible():
                self.refresh_smart_suggestions()
            return
        if not self.isVisible() or self.activity_id is None:
            return

        if not self._target_criteria_loaded:
            self._target_criteria_loaded = True
            try:
                records = self.db.target_criteria_for_activity(
                    self.activity_id
                )
            except sqlite3.Error as exc:
                QMessageBox.warning(
                    self, "تعذر تحميل المعايير والمؤشرات", str(exc)
                )
                return
            self._target_criteria_picker = TargetCriteriaPickerDialog(
                records, self
            )
            self._target_criteria_picker.selection_changed.connect(
                self._apply_target_criteria_selection
            )

        if self._target_criteria_picker is None:
            return
        self._target_criteria_picker.set_selected_values(
            self.value_edit.toPlainText()
        )
        self.suggestions_panel.hide()
        self._position_target_criteria_picker()
        self._target_criteria_picker.show()
        self._target_criteria_picker.raise_()

    def _position_target_criteria_picker(self):
        picker = self._target_criteria_picker
        picker.adjustSize()
        available = self.screen().availableGeometry()
        dialog_geometry = self.frameGeometry()
        x = dialog_geometry.right() + 8
        if x + picker.width() > available.right():
            x = dialog_geometry.left() - picker.width() - 8
        x = max(available.left(), min(x, available.right() - picker.width()))
        y = max(
            available.top(),
            min(dialog_geometry.top(), available.bottom() - picker.height()),
        )
        picker.move(x, y)

    def _apply_target_criteria_selection(self, value):
        if not self._is_target_criteria_property():
            return
        self._updating_target_criteria = True
        self.value_edit.is_completing = True
        try:
            self.value_edit.setPlainText(value)
            self.value_edit.moveCursor(QTextCursor.End)
        finally:
            self.value_edit.is_completing = False
            self._updating_target_criteria = False
        self.suggestions_panel.hide()

    def _apply_predicted_key(self, _request_id, key):
        self._prediction_worker = None
        if key and not self.key_combo.currentText().strip():
            self.key_combo.setCurrentText(key)
        if not self.key_combo.currentText().strip():
            self.key_combo.lineEdit().setPlaceholderText(
                "اختر أو اكتب اسم الخاصية"
            )

    def _prediction_failed(self, _request_id, message):
        self._prediction_worker = None
        self.key_combo.lineEdit().setPlaceholderText(
            "تعذر التوقع؛ اختر أو اكتب اسم الخاصية"
        )
        QMessageBox.warning(
            self, "تعذر توقع الخاصية",
            f"تعذر تحميل ترتيب الخصائص السابقة:\n{message}"
        )

    def _update_contextual_completion(self, *_args):
        if (
            self.key_combo.currentText().strip() != "هدف الحصة"
            or self.contextual_content is None
        ):
            self.value_edit.set_contextual_completion_words(None)
            return
        content_words = str(self.contextual_content).split()[1:]
        self.value_edit.set_contextual_completion_words(
            ("المتعلم", *content_words)
        )

    def refresh_smart_suggestions(self, *_args):
        if self._updating_target_criteria:
            return
        if self._is_target_criteria_property():
            self.suggestions_panel.hide()
            return
        if (
            self._target_criteria_picker is not None
            and self._target_criteria_picker.isVisible()
        ):
            self.suggestions_panel.hide()
            return
        self.suggestions_list.clear()
        self.suggestions_hint.setText(
            "جارٍ البحث في السجل السابق..."
            if self.value_edit.toPlainText().strip()
            else "اكتب في خانة القيمة لعرض الاقتراحات المناسبة."
        )
        self.suggestions_hint.show()
        if self.isVisible():
            self._show_suggestions_panel()

    def show_smart_suggestions(self, suggestions):
        if self._is_target_criteria_property():
            self.suggestions_panel.hide()
            return
        if (
            self._target_criteria_picker is not None
            and self._target_criteria_picker.isVisible()
        ):
            self.suggestions_panel.hide()
            return
        self.suggestions_list.clear()
        for value, score in suggestions:
            item = QListWidgetItem(value)
            item.setToolTip(f"درجة التشابه النصي: {score:.0%}")
            self.suggestions_list.addItem(item)
        has_suggestions = self.suggestions_list.count() > 0
        if not self.value_edit.toPlainText().strip():
            hint = "اكتب في خانة القيمة لعرض الاقتراحات المناسبة."
        elif self.value_edit.completion_failed:
            hint = "تعذّر تحميل سجل الاقتراحات."
        elif not self.value_edit.completion_history_available:
            hint = "لا توجد قيم محفوظة سابقاً لهذه الخاصية."
        else:
            hint = "لا توجد اقتراحات مشابهة لهذه القيمة."
        self.suggestions_hint.setText(hint)
        self.suggestions_hint.setVisible(not has_suggestions)
        if self.isVisible():
            self._show_suggestions_panel()

    def _show_suggestions_panel(self):
        panel_width = self.suggestions_panel.width()
        available = self.suggestions_panel.screen().availableGeometry()
        panel_height = self.suggestions_panel.height()
        dialog_geometry = self.frameGeometry()
        gap = 8
        x = dialog_geometry.right() + gap
        if x + panel_width - 1 > available.right():
            x = dialog_geometry.left() - panel_width - gap
        x = min(
            max(x, available.left()),
            available.right() - panel_width + 1,
        )
        y = min(
            max(dialog_geometry.top(), available.top()),
            available.bottom() - panel_height + 1,
        )
        self.suggestions_panel.move(x, y)
        self.suggestions_panel.show()
        self.suggestions_panel.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._is_target_criteria_property():
            self._show_suggestions_panel()
        self._update_target_criteria_picker()
        QTimer.singleShot(0, self.value_edit.setFocus)

    def apply_smart_suggestion(self, item):
        if item is None:
            return
        self.value_edit.setPlainText(item.text())
        self.value_edit.moveCursor(QTextCursor.End)
        self.value_edit.setFocus()
        self._show_suggestions_panel()

    def hideEvent(self, event):
        self.suggestions_panel.hide()
        if self._target_criteria_picker is not None:
            self._target_criteria_picker.hide()
        super().hideEvent(event)

    def values(self):
        return [self.key_combo.currentText().strip(), self.value_edit.toPlainText().strip()]


class BulkDetailSaveSignals(QObject):
    saved = Signal(int)
    failed = Signal(str)


class BulkDetailSaveWorker(QRunnable):
    def __init__(self, db, updates, inserts, deleted_ids):
        super().__init__()
        self.db = db
        self.updates = updates
        self.inserts = inserts
        self.deleted_ids = deleted_ids
        self.signals = BulkDetailSaveSignals()

    def run(self):
        try:
            saved_count = self.db.save_activity_details_bulk(
                self.updates, self.inserts, self.deleted_ids
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.saved.emit(saved_count)


class DetailKeyPredictionSignals(QObject):
    predicted = Signal(int, str)
    failed = Signal(int, str)


class DetailKeyPredictionWorker(QRunnable):
    def __init__(self, db, request_id, activity_title, namat, current_count):
        super().__init__()
        self.db = db
        self.request_id = request_id
        self.activity_title = activity_title
        self.namat = namat
        self.current_count = current_count
        self.signals = DetailKeyPredictionSignals()

    def run(self):
        try:
            key = self.db.predict_next_detail_key(
                self.activity_title, self.namat, self.current_count
            )
        except Exception as exc:
            self.signals.failed.emit(self.request_id, str(exc))
            return
        self.signals.predicted.emit(self.request_id, key)


class BulkActivityDetailsDialog(QDialog):
    def __init__(self, db, lesson_label, activities, namat, parent=None):
        super().__init__(parent)
        self.db = db
        self.namat = namat or ""
        self.setWindowTitle("إضافة جميع الخصائص لجميع الأنشطة")
        self.setObjectName("bulkActivityDetailsDialog")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(900, 650)
        self.resize(1100, 800)
        self._saving = False
        self._save_worker = None
        self._activity_rows = []
        self._prediction_workers = {}
        self._prediction_rows = {}
        self._next_prediction_request = 0
        self._expected_keys = DETAIL_KEYS_BY_NAMAT.get(self.namat, [])

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        lesson_label_widget = QLabel(lesson_label)
        lesson_label_widget.setWordWrap(True)
        lesson_label_widget.setStyleSheet("font-weight: bold;")
        self.back_button = QPushButton("رجوع للحصة")
        self.back_button.setProperty("actionType", "back")
        self.back_button.clicked.connect(self.reject)
        header.addWidget(lesson_label_widget, 1)
        header.addWidget(self.back_button)
        layout.addLayout(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.activities_container = QWidget()
        self.activities_layout = QVBoxLayout(self.activities_container)
        self.activities_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.activities_container)
        layout.addWidget(self.scroll_area, 1)

        for activity in activities:
            activity_details = self.db.details(activity[0])
            self._add_activity_section(
                activity[0], str(activity[1] or ""), activity_details
            )

        if not activities:
            layout.addWidget(QLabel("لا توجد أنشطة في هذه الحصة. أضف نشاطاً أولاً."))

        self.status_label = QLabel()
        self.status_label.hide()
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton(
            "حفظ جميع الخصائص", QDialogButtonBox.AcceptRole
        )
        self.save_button.setProperty("actionType", "save")
        cancel_button = buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        cancel_button.setProperty("actionType", "cancel")
        set_dialog_button_action_types(buttons)
        self.save_button.clicked.connect(self.save_details)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)
        self.save_button.setEnabled(bool(activities))

    def _add_activity_section(self, activity_id, activity_title, details):
        group = QGroupBox(f"النشاط: {activity_title}")
        group_layout = QVBoxLayout(group)
        rows_layout = QVBoxLayout()
        group_layout.addLayout(rows_layout)
        record = {
            "activity_id": activity_id,
            "title": activity_title,
            "layout": rows_layout,
            "rows": [],
            "deleted_ids": [],
            "next_prediction_index": len(details),
        }
        self._activity_rows.append(record)
        self.activities_layout.addWidget(group)

        for detail in details:
            self._add_property_row(record, detail=detail)

        self._add_property_row(
            record, prediction_index=record["next_prediction_index"]
        )
        record["next_prediction_index"] += 1
        self._refresh_contextual_completions(record)

    def _append_property_row(self, activity):
        prediction_index = activity["next_prediction_index"]
        activity["next_prediction_index"] += 1
        return self._add_property_row(
            activity, prediction_index=prediction_index
        )

    def _add_property_row(
        self, activity, detail=None, prediction_index=None
    ):
        row_widget = QWidget()
        row_layout = QVBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 6, 0, 6)
        key_layout = QHBoxLayout()
        key_combo = QComboBox()
        key_combo.setEditable(True)
        key_combo.addItems(self._expected_keys)
        if detail:
            key_combo.setCurrentText(str(detail[1] or ""))
        else:
            key_combo.clearEditText()
            key_combo.lineEdit().setPlaceholderText("جارٍ توقع اسم الخاصية...")
        remove_button = QPushButton("حذف الخاصية")
        remove_button.setProperty("actionType", "delete")
        key_layout.addWidget(QLabel("اسم الخاصية"))
        key_layout.addWidget(key_combo, 1)
        key_layout.addWidget(remove_button)
        row_layout.addLayout(key_layout)

        value_edit = AutoCompletionTextEdit(
            self.db, key_combo, activity["title"], row_widget
        )
        value_edit.setPlaceholderText(
            "اكتب قيمة الخاصية؛ ستظهر اقتراحات الإكمال الذكي من السجل السابق."
        )
        value_edit.setFixedHeight(value_edit.fontMetrics().lineSpacing() * 4 + 12)
        if detail:
            value_edit.setPlainText(str(detail[2] or ""))
        row_layout.addWidget(value_edit)

        suggestions_list = QListWidget()
        suggestions_list.setMaximumHeight(90)
        suggestions_list.setToolTip("اختر اقتراحاً لإدراجه في خانة القيمة")
        suggestions_list.hide()
        row_layout.addWidget(suggestions_list)
        value_edit.suggestions_ready.connect(
            lambda suggestions, widget=suggestions_list:
            self._show_suggestions(widget, suggestions)
        )
        suggestions_list.itemClicked.connect(
            lambda item, editor=value_edit, widget=suggestions_list:
            self._apply_suggestion(editor, widget, item)
        )
        key_combo.currentTextChanged.connect(value_edit.refresh_for_key_change)

        activity["layout"].addWidget(row_widget)
        row = {
            "widget": row_widget,
            "key_combo": key_combo,
            "value_edit": value_edit,
            "detail_id": detail[0] if detail else None,
            "original_key": str(detail[1] or "") if detail else None,
            "prediction_index": prediction_index,
            "spawned_next": False,
        }
        activity["rows"].append(row)
        remove_button.clicked.connect(
            lambda *args, target=activity, current_row=row:
            self._remove_property_row(target, current_row)
        )
        if prediction_index is not None:
            value_edit.textChanged.connect(
                lambda target=activity, current=row:
                self._on_new_property_started(target, current)
            )
            self._request_predicted_key(activity, row)
        value_edit.textChanged.connect(
            lambda target=activity:
            self._refresh_contextual_completions(target)
        )
        key_combo.currentTextChanged.connect(
            lambda _key, target=activity:
            self._refresh_contextual_completions(target)
        )
        self._refresh_contextual_completions(activity)
        return row_widget

    @staticmethod
    def _content_words(text):
        words = str(text or "").split()
        return words[1:] if words else []

    def _refresh_contextual_completions(self, activity):
        content_row = next(
            (
                row for row in activity["rows"]
                if row["key_combo"].currentText().strip() == "المحتوى"
            ),
            None,
        )
        goal_rows = [
            row for row in activity["rows"]
            if row["key_combo"].currentText().strip() == "هدف الحصة"
        ]
        if content_row is None:
            words = None
        else:
            words = (
                "المتعلم",
                *self._content_words(
                    content_row["value_edit"].toPlainText()
                ),
            )
        for row in goal_rows:
            row["value_edit"].set_contextual_completion_words(words)

    def _request_predicted_key(self, activity, row):
        self._next_prediction_request += 1
        request_id = self._next_prediction_request
        self._prediction_rows[request_id] = (activity, row)
        worker = DetailKeyPredictionWorker(
            self.db, request_id, activity["title"], self.namat,
            row["prediction_index"],
        )
        self._prediction_workers[request_id] = worker
        worker.signals.predicted.connect(self._apply_predicted_key)
        worker.signals.failed.connect(self._prediction_failed)
        QThreadPool.globalInstance().start(worker)

    def _apply_predicted_key(self, request_id, key):
        self._prediction_workers.pop(request_id, None)
        target = self._prediction_rows.pop(request_id, None)
        if target is None:
            return
        activity, row = target
        if row not in activity["rows"]:
            return
        combo = row["key_combo"]
        if key and not combo.currentText().strip():
            combo.setCurrentText(key)
        if not combo.currentText().strip():
            combo.lineEdit().setPlaceholderText("اختر أو اكتب اسم الخاصية")

    def _prediction_failed(self, request_id, message):
        self._prediction_workers.pop(request_id, None)
        target = self._prediction_rows.pop(request_id, None)
        if target is None:
            return
        activity, row = target
        if row in activity["rows"]:
            row["key_combo"].lineEdit().setPlaceholderText(
                "تعذر التوقع؛ اختر أو اكتب اسم الخاصية"
            )
        QMessageBox.warning(
            self, "تعذر توقع الخاصية",
            f"تعذر تحميل ترتيب الخصائص السابقة:\n{message}"
        )

    def _on_new_property_started(self, activity, row):
        if row["spawned_next"] or not row["value_edit"].toPlainText().strip():
            return
        row["spawned_next"] = True
        self._append_property_row(activity)

    @staticmethod
    def _show_suggestions(widget, suggestions):
        widget.clear()
        for value, score in suggestions:
            item = QListWidgetItem(value)
            item.setToolTip(f"درجة التشابه النصي: {score:.0%}")
            widget.addItem(item)
        widget.setVisible(widget.count() > 0)

    @staticmethod
    def _apply_suggestion(editor, suggestions_list, item):
        if item is None:
            return
        editor.setPlainText(item.text())
        editor.moveCursor(QTextCursor.End)
        editor.setFocus()
        suggestions_list.hide()

    @staticmethod
    def _remove_property_row(activity, row):
        if row["detail_id"] is not None:
            activity["deleted_ids"].append(row["detail_id"])
        activity["rows"].remove(row)
        row["widget"].deleteLater()

    def save_details(self):
        if self._saving:
            return
        updates = []
        inserts = []
        deleted_ids = []
        duplicate_keys = {}
        for activity in self._activity_rows:
            deleted_ids.extend(activity["deleted_ids"])
            for row in activity["rows"]:
                key_combo = row["key_combo"]
                value_edit = row["value_edit"]
                key = key_combo.currentText().strip()
                value = value_edit.toPlainText().strip()
                detail_id = row["detail_id"]
                if detail_id is None and not value:
                    continue
                if not key:
                    QMessageBox.warning(
                        self, "اسم الخاصية مطلوب",
                        "اختر أو أدخل اسم الخاصية لكل خاصية محفوظة أو قيمة مدخلة."
                    )
                    key_combo.setFocus()
                    return
                pair = (activity["activity_id"], key)
                previous_row = duplicate_keys.get(pair)
                if previous_row is not None:
                    unchanged_existing_duplicate = (
                        row["detail_id"] is not None
                        and previous_row["detail_id"] is not None
                        and row["original_key"] == key
                        and previous_row["original_key"] == key
                    )
                    if not unchanged_existing_duplicate:
                        QMessageBox.warning(
                            self, "خاصية مكررة",
                            f"أُدخلت الخاصية «{key}» أكثر من مرة للنشاط "
                            f"«{activity['title']}». احذف أو غيّر إحدى النسخ."
                        )
                        return
                else:
                    duplicate_keys[pair] = row
                if detail_id is not None:
                    updates.append((detail_id, key, value))
                else:
                    inserts.append((activity["activity_id"], key, value))

        if not updates and not inserts and not deleted_ids:
            QMessageBox.information(
                self, "لا توجد قيم للحفظ",
                "لم يتم إدخال أي قيمة أو تعديل أو حذف خاصية."
            )
            return

        self._saving = True
        self.save_button.setEnabled(False)
        self.back_button.setEnabled(False)
        self.status_label.setText("جارٍ حفظ الخصائص في الخلفية...")
        self.status_label.show()
        self._save_worker = BulkDetailSaveWorker(
            self.db, updates, inserts, deleted_ids
        )
        self._save_worker.signals.saved.connect(self._save_succeeded)
        self._save_worker.signals.failed.connect(self._save_failed)
        QThreadPool.globalInstance().start(self._save_worker)

    def _save_succeeded(self, count):
        self.status_label.setText(f"تم حفظ {count} خاصية بنجاح.")
        self.accept()

    def _save_failed(self, message):
        self._saving = False
        self.save_button.setEnabled(True)
        self.back_button.setEnabled(True)
        self.status_label.hide()
        QMessageBox.critical(
            self, "تعذر حفظ الخصائص",
            f"حدث خطأ أثناء حفظ الخصائص:\n{message}"
        )

    def reject(self):
        if self._saving:
            return
        super().reject()


class EvaluationCriterionDialog(QDialog):
    def __init__(
        self, subjects, subject_id=None, criterion="", indicators=(),
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("بيانات معيار التقييم")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.subject_combo = QComboBox()
        for material_id, label in subjects:
            self.subject_combo.addItem(label, material_id)
        if subject_id is not None:
            self.subject_combo.setCurrentIndex(
                self.subject_combo.findData(subject_id)
            )
            self.subject_combo.setEnabled(False)
        form.addRow("المادة:", self.subject_combo)

        self.criterion_edit = QLineEdit(criterion)
        form.addRow("المعيار:", self.criterion_edit)

        self.indicators_edit = QPlainTextEdit()
        self.indicators_edit.setPlaceholderText(
            "اكتب مؤشراً واحداً في كل سطر"
        )
        self.indicators_edit.setPlainText("\n".join(indicators))
        self.indicators_edit.setMinimumHeight(140)
        form.addRow("المؤشرات:", self.indicators_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole)
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        indicators = [
            line.strip()
            for line in self.indicators_edit.toPlainText().splitlines()
            if line.strip()
        ]
        return (
            self.subject_combo.currentData(),
            self.criterion_edit.text().strip(),
            indicators,
        )


class CompetenceManagerDialog(QDialog):
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة كفايات المجالات والمواد الدراسية")
        # ⬅️ زيادة عرض وارتفاع النافذة لتكون أوسع وأكثر راحة
        self.resize(1200, 750)
        self.setLayoutDirection(Qt.RightToLeft)
        
        self.db = db if db else Database(DB_PATH)
        
        self.selected_level_id = None
        self.selected_majal_id = None
        self.selected_competence_majal_id = None
        self.copied_majal_data = None
        self.copied_evaluation_criteria = None

        self.init_ui()
        self.load_levels_and_majals()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        title_label = QLabel("🎯 لوحة إدارة كفايات المجالات والمواد الدراسية")
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #1E40AF; padding: 5px;")
        main_layout.addWidget(title_label)

        filters_box = QGroupBox("فلترة واختيار المستوى والمجال")
        filters_layout = QHBoxLayout(filters_box)

        self.combo_level = QComboBox()
        self.combo_level.currentIndexChanged.connect(self.on_filter_changed)

        self.combo_majal = QComboBox()
        self.combo_majal.currentIndexChanged.connect(self.on_filter_changed)

        filters_layout.addWidget(QLabel("المستوى الدراسي:"))
        filters_layout.addWidget(self.combo_level, 1)
        filters_layout.addWidget(QLabel("المجال:"))
        filters_layout.addWidget(self.combo_majal, 1)

        main_layout.addWidget(filters_box)

        self.tabs = QTabWidget()
        splitter = QSplitter(Qt.Horizontal)

        # جدول كفاية المجال
        majal_widget = QWidget()
        majal_layout = QVBoxLayout(majal_widget)
        majal_layout.addWidget(QLabel("<b>1. كفاية المجال </b>"))
        
        majal_btns_layout = QHBoxLayout()
        for text, slot, act_type in [
            ("إضافة", self.add_competence_majal, "add"), 
            ("تعديل", self.edit_competence_majal, "edit"), 
            ("حذف", self.delete_competence_majal, "delete"),
            ("نسخ الكل", self.copy_majal_with_matieres, "copy_paste"),
            ("لصق وتحديث", self.paste_majal_with_matieres, "copy_paste")
        ]:
            b = QPushButton(text)
            b.setMinimumWidth(110)  # ⬅️ زيادة عرض الأزرار
            b.setProperty("actionType", act_type)
            b.clicked.connect(slot)
            majal_btns_layout.addWidget(b)
        majal_layout.addLayout(majal_btns_layout)

        self.tbl_competence_majal = self.create_clean_table(["كفاية المجال"])
        self.tbl_competence_majal.itemSelectionChanged.connect(self.on_competence_majal_selected)
        majal_layout.addWidget(self.tbl_competence_majal)
        splitter.addWidget(majal_widget)

        # جدول كفايات المواد
        matiere_widget = QWidget()
        matiere_layout = QVBoxLayout(matiere_widget)
        matiere_layout.addWidget(QLabel("<b>2. كفايات المواد المرتبطة بكفاية المجال المختارة</b>"))
        
        matiere_btns_layout = QHBoxLayout()
        for text, slot, act_type in [
            ("إضافة مادة/كفاية", self.add_competence_matiere, "add"), 
            ("تعديل", self.edit_competence_matiere, "edit"), 
            ("حذف", self.delete_competence_matiere, "delete")
        ]:
            b = QPushButton(text)
            b.setMinimumWidth(130)  # ⬅️ زيادة عرض الأزرار
            b.setProperty("actionType", act_type)
            b.clicked.connect(slot)
            matiere_btns_layout.addWidget(b)
        matiere_layout.addLayout(matiere_btns_layout)

        self.tbl_competence_matiere = self.create_clean_table(["المادة", "كفاية المادة"])
        matiere_layout.addWidget(self.tbl_competence_matiere)
        splitter.addWidget(matiere_widget)

        splitter.setSizes([520, 580])
        self.tabs.addTab(splitter, "كفايات المجالات")
        for title in (
            "الأداء المنتظر في نهاية السنة الدراسية",
            "جدول معايير التقييم",
        ):
            tab_page = QWidget()
            tab_layout = QVBoxLayout(tab_page)
            if title == "الأداء المنتظر في نهاية السنة الدراسية":
                toolbar = QHBoxLayout()
                toolbar.addWidget(QLabel("الأداء المنتظر (حتى 6 أسطر لكل مادة)"))
                toolbar.addStretch()
                add_row_button = QPushButton("إضافة مادة")
                add_row_button.setProperty("actionType", "add")
                add_row_button.clicked.connect(self.add_expected_performance_row)
                toolbar.addWidget(add_row_button)
                tab_layout.addLayout(toolbar)

                self.expected_performance_rows = []
                self.expected_performance_scroll = QScrollArea()
                self.expected_performance_scroll.setWidgetResizable(True)
                self.expected_performance_rows_container = QWidget()
                self.expected_performance_rows_layout = QVBoxLayout(
                    self.expected_performance_rows_container
                )
                self.expected_performance_rows_layout.setAlignment(
                    Qt.AlignTop
                )
                self.expected_performance_scroll.setWidget(
                    self.expected_performance_rows_container
                )
                tab_layout.addWidget(self.expected_performance_scroll, 1)
            else:
                criteria_toolbar = QHBoxLayout()
                criteria_toolbar.addWidget(QLabel(
                    "معايير مواد المستوى والمجال المحددين"
                ))
                criteria_toolbar.addStretch()
                for text, slot, action_type in (
                    ("استيراد JSON", self.import_evaluation_criteria_json, "browse"),
                    ("تصدير JSON", self.export_evaluation_criteria_json, "export"),
                    ("نسخ الجدول", self.copy_evaluation_criteria, "copy_paste"),
                    ("لصق الجدول", self.paste_evaluation_criteria, "copy_paste"),
                    ("إضافة معيار", self.add_evaluation_criterion, "add"),
                    ("تعديل المعيار", self.edit_evaluation_criterion, "edit"),
                    ("مسح المعيار", self.delete_evaluation_criterion, "delete"),
                ):
                    button = QPushButton(text)
                    button.setProperty("actionType", action_type)
                    button.clicked.connect(slot)
                    criteria_toolbar.addWidget(button)
                tab_layout.addLayout(criteria_toolbar)
                self.tbl_evaluation_criteria = self.create_clean_table(
                    ["المادة", "رقم المعيار", "المعيار", "بعض مؤشراته"]
                )
                self.tbl_evaluation_criteria.setWordWrap(True)
                self.tbl_evaluation_criteria.verticalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents
                )
                tab_layout.addWidget(self.tbl_evaluation_criteria)
            self.tabs.addTab(tab_page, title)
        main_layout.addWidget(self.tabs, 1)

        close_btn = QPushButton("إغلاق")
        close_btn.setProperty("actionType", "close")
        close_btn.clicked.connect(self.accept)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(close_btn)
        main_layout.addLayout(bottom_layout)

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

            self.on_filter_changed()
        except Exception as e:
            print(f"Error loading filters in manager: {e}")

    def on_filter_changed(self):
        self.selected_level_id = self.combo_level.currentData()
        self.selected_majal_id = self.combo_majal.currentData()
        self.load_competence_majal_data()
        self.load_expected_performance_subjects()
        self.load_evaluation_criteria()

    def load_evaluation_criteria(self):
        table = self.tbl_evaluation_criteria
        table.setRowCount(0)
        self.evaluation_subject_options = []
        if not self.selected_level_id or not self.selected_majal_id:
            return
        try:
            with self.db.connect() as con:
                subjects = con.execute(
                    """SELECT cm.id, cm.matiere, cm.competence
                       FROM competence_matiere AS cm
                       JOIN competence_majal AS cj
                         ON cj.id = cm.id_competence_majal
                       WHERE cj.id_level = ? AND cj.id_majal = ?
                       ORDER BY cm.matiere, cm.id""",
                    (self.selected_level_id, self.selected_majal_id),
                ).fetchall()
                subject_counts = {}
                for _, subject, _ in subjects:
                    subject_counts[subject] = subject_counts.get(subject, 0) + 1
                self.evaluation_subject_options = [
                    (
                        material_id,
                        (
                            f"{subject} — {competence}"
                            if subject_counts[subject] > 1
                            else subject
                        ),
                    )
                    for material_id, subject, competence in subjects
                ]
                rows = con.execute(
                    """SELECT cm.matiere, c.criterion_order, c.criterion,
                              cm.id, c.id,
                              COALESCE((
                                  SELECT group_concat(indicator, char(10))
                                  FROM (
                                      SELECT indicator
                                      FROM subject_evaluation_indicator
                                      WHERE criterion_id = c.id
                                      ORDER BY indicator_order
                                  )
                              ), '')
                       FROM subject_evaluation_criterion AS c
                       JOIN competence_matiere AS cm
                         ON cm.id = c.competence_matiere_id
                       JOIN competence_majal AS cj
                         ON cj.id = cm.id_competence_majal
                       WHERE cj.id_level = ? AND cj.id_majal = ?
                       ORDER BY cm.matiere, c.criterion_order""",
                    (self.selected_level_id, self.selected_majal_id),
                ).fetchall()
            for record in rows:
                row_index = table.rowCount()
                table.insertRow(row_index)
                material_item = QTableWidgetItem(str(record[0]))
                material_item.setData(Qt.UserRole, record[3])
                table.setItem(row_index, 0, material_item)
                table.setItem(row_index, 1, QTableWidgetItem(str(record[1])))
                criterion_item = QTableWidgetItem(str(record[2]))
                criterion_item.setData(Qt.UserRole, record[4])
                table.setItem(row_index, 2, criterion_item)
                table.setItem(row_index, 3, QTableWidgetItem(str(record[5])))
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر تحميل جدول معايير التقييم: {exc}"
            )

    def copy_evaluation_criteria(self):
        if not self.selected_level_id or not self.selected_majal_id:
            QMessageBox.warning(
                self, "تنبيه", "يرجى اختيار المستوى والمجال أولاً."
            )
            return
        try:
            copied_subjects = self.copy_evaluation_criteria_data()
            if not any(item["criteria"] for item in copied_subjects):
                QMessageBox.warning(
                    self, "لا توجد بيانات",
                    "لا توجد معايير في الجدول الحالي لنسخها.",
                )
                return
            self.copied_evaluation_criteria = copied_subjects
            QMessageBox.information(
                self, "تم النسخ",
                "تم نسخ معايير المواد ومؤشراتها كاملة.",
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر نسخ جدول المعايير: {exc}"
            )

    def copy_evaluation_criteria_data(self):
        with self.db.connect() as con:
            subjects = con.execute(
                """SELECT cm.id, cm.matiere, cm.competence
                   FROM competence_matiere AS cm
                   JOIN competence_majal AS cj
                     ON cj.id = cm.id_competence_majal
                   WHERE cj.id_level = ? AND cj.id_majal = ?
                   ORDER BY cm.matiere, cm.competence, cm.id""",
                (self.selected_level_id, self.selected_majal_id),
            ).fetchall()
            copied_subjects = []
            for subject_id, subject, competence in subjects:
                criteria = con.execute(
                    """SELECT id, criterion_order, criterion
                       FROM subject_evaluation_criterion
                       WHERE competence_matiere_id = ?
                       ORDER BY criterion_order, id""",
                    (subject_id,),
                ).fetchall()
                copied_criteria = []
                for criterion_id, order, criterion in criteria:
                    indicators = con.execute(
                        """SELECT indicator_order, indicator
                           FROM subject_evaluation_indicator
                           WHERE criterion_id = ?
                           ORDER BY indicator_order, id""",
                        (criterion_id,),
                    ).fetchall()
                    copied_criteria.append({
                        "order": order,
                        "criterion": criterion,
                        "indicators": indicators,
                    })
                copied_subjects.append({
                    "matiere": subject,
                    "competence": competence,
                    "criteria": copied_criteria,
                })
        return copied_subjects

    def _map_evaluation_subjects(self, copied_subjects):
        with self.db.connect() as con:
            target_subjects = con.execute(
                """SELECT cm.id, cm.matiere, cm.competence
                   FROM competence_matiere AS cm
                   JOIN competence_majal AS cj
                     ON cj.id = cm.id_competence_majal
                   WHERE cj.id_level = ? AND cj.id_majal = ?
                   ORDER BY cm.matiere, cm.competence, cm.id""",
                (self.selected_level_id, self.selected_majal_id),
            ).fetchall()

        target_by_name = {}
        for subject_id, subject, competence in target_subjects:
            target_by_name.setdefault(subject, []).append(
                (subject_id, competence)
            )
        subject_mapping = []
        unmatched_subjects = []
        used_target_ids = set()
        for copied_subject in copied_subjects:
            candidates = target_by_name.get(copied_subject["matiere"], [])
            exact_competence = [
                item for item in candidates
                if item[1] == copied_subject["competence"]
            ]
            if len(exact_competence) == 1:
                target_id = exact_competence[0][0]
            elif len(candidates) == 1:
                target_id = candidates[0][0]
            else:
                unmatched_subjects.append(copied_subject["matiere"])
                continue
            if target_id in used_target_ids:
                unmatched_subjects.append(copied_subject["matiere"])
                continue
            used_target_ids.add(target_id)
            subject_mapping.append((target_id, copied_subject))
        return subject_mapping, unmatched_subjects

    def _replace_evaluation_criteria(self, subject_mapping):
        with self.db.connect() as con:
            for target_id, copied_subject in subject_mapping:
                existing_criteria = con.execute(
                    """SELECT id FROM subject_evaluation_criterion
                       WHERE competence_matiere_id = ?""",
                    (target_id,),
                ).fetchall()
                if existing_criteria:
                    con.executemany(
                        """DELETE FROM subject_evaluation_indicator
                           WHERE criterion_id = ?""",
                        [(row[0],) for row in existing_criteria],
                    )
                    con.execute(
                        """DELETE FROM subject_evaluation_criterion
                           WHERE competence_matiere_id = ?""",
                        (target_id,),
                    )
                for criterion in copied_subject["criteria"]:
                    criterion_id = con.execute("""
                        INSERT INTO subject_evaluation_criterion(
                            competence_matiere_id, criterion_order, criterion
                        ) VALUES (?, ?, ?)
                    """, (
                        target_id,
                        criterion["order"],
                        criterion["criterion"],
                    )).lastrowid
                    con.executemany("""
                        INSERT INTO subject_evaluation_indicator(
                            criterion_id, indicator_order, indicator
                        ) VALUES (?, ?, ?)
                    """, [
                        (criterion_id, order, indicator)
                        for order, indicator in criterion["indicators"]
                    ])

    def export_evaluation_criteria_json(self):
        if not self.selected_level_id or not self.selected_majal_id:
            QMessageBox.warning(
                self, "تنبيه", "يرجى اختيار المستوى والمجال أولاً."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "تصدير جدول المعايير", "معايير_التقييم.json",
            "JSON (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            copied_subjects = self.copy_evaluation_criteria_data()
            document = {
                "schema_version": 1,
                "source": {
                    "level": self.combo_level.currentText(),
                    "domain": self.combo_majal.currentText(),
                },
                "subjects": [
                    {
                        "matiere": subject["matiere"],
                        "competence": subject["competence"],
                        "criteria": [
                            {
                                "order": criterion["order"],
                                "criterion": criterion["criterion"],
                                "indicators": [
                                    indicator
                                    for _, indicator
                                    in criterion["indicators"]
                                ],
                            }
                            for criterion in subject["criteria"]
                        ],
                    }
                    for subject in copied_subjects
                ],
            }
            if not any(subject["criteria"] for subject in document["subjects"]):
                QMessageBox.warning(
                    self, "لا توجد بيانات",
                    "لا توجد معايير في الجدول الحالي لتصديرها.",
                )
                return
            with open(path, "w", encoding="utf-8") as output:
                json.dump(document, output, ensure_ascii=False, indent=2)
            QMessageBox.information(
                self, "تم التصدير", "تم تصدير جدول المعايير بنجاح."
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر تصدير جدول المعايير: {exc}"
            )

    @staticmethod
    def _load_evaluation_criteria_json(path):
        with open(path, "r", encoding="utf-8-sig") as source:
            document = json.load(source)
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("إصدار ملف JSON غير مدعوم.")
        subjects = document.get("subjects")
        if not isinstance(subjects, list) or not subjects:
            raise ValueError("الملف لا يحتوي على قائمة مواد صالحة.")

        normalized_subjects = []
        subject_keys = set()
        for subject in subjects:
            if not isinstance(subject, dict):
                raise ValueError("بيانات المادة في الملف غير صالحة.")
            name = subject.get("matiere")
            competence = subject.get("competence")
            criteria = subject.get("criteria")
            if (
                not isinstance(name, str) or not name.strip()
                or not isinstance(competence, str)
                or not isinstance(criteria, list)
            ):
                raise ValueError("بيانات المادة أو معاييرها غير مكتملة.")
            subject_key = (name.strip(), competence.strip())
            if subject_key in subject_keys:
                raise ValueError(f"المادة مكررة في الملف: {name}")
            subject_keys.add(subject_key)

            normalized_criteria = []
            criterion_orders = set()
            for criterion in criteria:
                if not isinstance(criterion, dict):
                    raise ValueError("بيانات المعيار في الملف غير صالحة.")
                order = criterion.get("order")
                text = criterion.get("criterion")
                indicators = criterion.get("indicators")
                if (
                    not isinstance(order, int) or isinstance(order, bool)
                    or order < 1 or order in criterion_orders
                    or not isinstance(text, str) or not text.strip()
                    or not isinstance(indicators, list)
                    or any(
                        not isinstance(indicator, str)
                        or not indicator.strip()
                        for indicator in indicators
                    )
                ):
                    raise ValueError("المعيار أو مؤشراته غير صالحة.")
                criterion_orders.add(order)
                normalized_criteria.append({
                    "order": order,
                    "criterion": text.strip(),
                    "indicators": [
                        (index, indicator.strip())
                        for index, indicator in enumerate(indicators, 1)
                    ],
                })
            normalized_subjects.append({
                "matiere": name.strip(),
                "competence": competence.strip(),
                "criteria": sorted(
                    normalized_criteria, key=lambda item: item["order"]
                ),
            })
        return normalized_subjects

    def import_evaluation_criteria_json(self):
        if not self.selected_level_id or not self.selected_majal_id:
            QMessageBox.warning(
                self, "تنبيه", "يرجى اختيار المستوى والمجال المستهدفين."
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "استيراد جدول المعايير", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            imported_subjects = self._load_evaluation_criteria_json(path)
            subject_mapping, unmatched_subjects = (
                self._map_evaluation_subjects(imported_subjects)
            )
            if unmatched_subjects:
                QMessageBox.warning(
                    self, "تعذر الاستيراد",
                    "تعذر مطابقة المواد التالية مع المستوى والمجال "
                    "المحددين:\n"
                    + "\n".join(sorted(set(unmatched_subjects))),
                )
                return
            if not subject_mapping:
                QMessageBox.warning(
                    self, "لا توجد مواد مطابقة",
                    "لا توجد مواد مطابقة في المستوى والمجال المحددين.",
                )
                return
            if QMessageBox.question(
                self, "تأكيد الاستيراد",
                "سيتم استبدال معايير ومؤشرات المواد المطابقة في المستوى "
                "والمجال المحددين. هل تريد المتابعة؟",
                QMessageBox.Yes | QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            self._replace_evaluation_criteria(subject_mapping)
            self.load_evaluation_criteria()
            QMessageBox.information(
                self, "تم الاستيراد",
                f"تم استيراد معايير ومؤشرات {len(subject_mapping)} مادة.",
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            QMessageBox.critical(
                self, "ملف غير صالح",
                f"تعذر استيراد جدول المعايير:\n{exc}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر استيراد جدول المعايير: {exc}"
            )

    def paste_evaluation_criteria(self):
        if not self.copied_evaluation_criteria:
            QMessageBox.warning(
                self, "لا توجد بيانات منسوخة",
                "انسخ جدول المعايير أولاً.",
            )
            return
        if not self.selected_level_id or not self.selected_majal_id:
            QMessageBox.warning(
                self, "تنبيه", "يرجى اختيار المستوى والمجال المستهدفين."
            )
            return
        try:
            with self.db.connect() as con:
                target_subjects = con.execute(
                    """SELECT cm.id, cm.matiere, cm.competence
                       FROM competence_matiere AS cm
                       JOIN competence_majal AS cj
                         ON cj.id = cm.id_competence_majal
                       WHERE cj.id_level = ? AND cj.id_majal = ?
                       ORDER BY cm.matiere, cm.competence, cm.id""",
                    (self.selected_level_id, self.selected_majal_id),
                ).fetchall()

            target_by_name = {}
            for subject_id, subject, competence in target_subjects:
                target_by_name.setdefault(subject, []).append(
                    (subject_id, competence)
                )
            subject_mapping = []
            unmatched_subjects = []
            used_target_ids = set()
            for copied_subject in self.copied_evaluation_criteria:
                candidates = target_by_name.get(
                    copied_subject["matiere"], []
                )
                exact_competence = [
                    item for item in candidates
                    if item[1] == copied_subject["competence"]
                ]
                if len(exact_competence) == 1:
                    target_id = exact_competence[0][0]
                elif len(candidates) == 1:
                    target_id = candidates[0][0]
                else:
                    unmatched_subjects.append(copied_subject["matiere"])
                    continue
                if target_id in used_target_ids:
                    unmatched_subjects.append(copied_subject["matiere"])
                    continue
                used_target_ids.add(target_id)
                subject_mapping.append((target_id, copied_subject))

            if unmatched_subjects:
                QMessageBox.warning(
                    self, "تعذر اللصق",
                    "تعذر تحديد مادة مطابقة دون لبس لهذه المواد:\n"
                    + "\n".join(sorted(set(unmatched_subjects))),
                )
                return
            if not subject_mapping:
                QMessageBox.warning(
                    self, "لا توجد مواد مطابقة",
                    "لا توجد مواد مطابقة في المستوى والمجال المحددين.",
                )
                return
            if QMessageBox.question(
                self, "تأكيد اللصق",
                "سيتم استبدال معايير ومؤشرات المواد المطابقة في المستوى "
                "والمجال المحددين. هل تريد المتابعة؟",
                QMessageBox.Yes | QMessageBox.No,
            ) != QMessageBox.Yes:
                return

            with self.db.connect() as con:
                for target_id, copied_subject in subject_mapping:
                    existing_criteria = con.execute(
                        """SELECT id FROM subject_evaluation_criterion
                           WHERE competence_matiere_id = ?""",
                        (target_id,),
                    ).fetchall()
                    if existing_criteria:
                        con.executemany(
                            """DELETE FROM subject_evaluation_indicator
                               WHERE criterion_id = ?""",
                            [(row[0],) for row in existing_criteria],
                        )
                        con.execute(
                            """DELETE FROM subject_evaluation_criterion
                               WHERE competence_matiere_id = ?""",
                            (target_id,),
                        )
                    for criterion in copied_subject["criteria"]:
                        criterion_id = con.execute("""
                            INSERT INTO subject_evaluation_criterion(
                                competence_matiere_id, criterion_order,
                                criterion
                            ) VALUES (?, ?, ?)
                        """, (
                            target_id,
                            criterion["order"],
                            criterion["criterion"],
                        )).lastrowid
                        con.executemany("""
                            INSERT INTO subject_evaluation_indicator(
                                criterion_id, indicator_order, indicator
                            ) VALUES (?, ?, ?)
                        """, [
                            (criterion_id, order, indicator)
                            for order, indicator in criterion["indicators"]
                        ])
            self.load_evaluation_criteria()
            QMessageBox.information(
                self, "تم اللصق",
                f"تم لصق معايير ومؤشرات {len(subject_mapping)} مادة.",
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر لصق جدول المعايير: {exc}"
            )

    def add_evaluation_criterion(self):
        if not self.evaluation_subject_options:
            QMessageBox.warning(
                self, "تنبيه", "لا توجد مواد مسجلة لهذا المستوى والمجال."
            )
            return
        dialog = EvaluationCriterionDialog(
            self.evaluation_subject_options, parent=self
        )
        if not dialog.exec():
            return
        material_id, criterion, indicators = dialog.values()
        if not material_id or not criterion:
            QMessageBox.warning(
                self, "بيانات ناقصة", "يرجى اختيار المادة وكتابة المعيار."
            )
            return
        try:
            with self.db.connect() as con:
                criterion_order = con.execute(
                    """SELECT COALESCE(MAX(criterion_order), 0) + 1
                       FROM subject_evaluation_criterion
                       WHERE competence_matiere_id = ?""",
                    (material_id,),
                ).fetchone()[0]
                criterion_id = con.execute("""
                    INSERT INTO subject_evaluation_criterion(
                        competence_matiere_id, criterion_order, criterion
                    ) VALUES (?, ?, ?)
                """, (material_id, criterion_order, criterion)).lastrowid
                con.executemany("""
                    INSERT INTO subject_evaluation_indicator(
                        criterion_id, indicator_order, indicator
                    ) VALUES (?, ?, ?)
                """, [
                    (criterion_id, index, indicator)
                    for index, indicator in enumerate(indicators, start=1)
                ])
            self.load_evaluation_criteria()
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر إضافة معيار التقييم: {exc}"
            )

    def _selected_evaluation_criterion(self):
        row = self.tbl_evaluation_criteria.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "تنبيه", "يرجى تحديد معيار من الجدول أولاً."
            )
            return None
        return (
            self.tbl_evaluation_criteria.item(row, 0).data(Qt.UserRole),
            self.tbl_evaluation_criteria.item(row, 2).data(Qt.UserRole),
            self.tbl_evaluation_criteria.item(row, 2).text(),
            self.tbl_evaluation_criteria.item(row, 3).text().splitlines(),
        )

    def edit_evaluation_criterion(self):
        selected = self._selected_evaluation_criterion()
        if selected is None:
            return
        material_id, criterion_id, criterion, indicators = selected
        dialog = EvaluationCriterionDialog(
            self.evaluation_subject_options,
            subject_id=material_id,
            criterion=criterion,
            indicators=indicators,
            parent=self,
        )
        if not dialog.exec():
            return
        _, updated_criterion, updated_indicators = dialog.values()
        if not updated_criterion:
            QMessageBox.warning(
                self, "بيانات ناقصة", "يرجى كتابة نص المعيار."
            )
            return
        try:
            with self.db.connect() as con:
                con.execute(
                    """UPDATE subject_evaluation_criterion
                       SET criterion = ? WHERE id = ?""",
                    (updated_criterion, criterion_id),
                )
                con.execute(
                    "DELETE FROM subject_evaluation_indicator "
                    "WHERE criterion_id = ?",
                    (criterion_id,),
                )
                con.executemany("""
                    INSERT INTO subject_evaluation_indicator(
                        criterion_id, indicator_order, indicator
                    ) VALUES (?, ?, ?)
                """, [
                    (criterion_id, index, indicator)
                    for index, indicator in enumerate(
                        updated_indicators, start=1
                    )
                ])
            self.load_evaluation_criteria()
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر تعديل معيار التقييم: {exc}"
            )

    def delete_evaluation_criterion(self):
        selected = self._selected_evaluation_criterion()
        if selected is None:
            return
        _, criterion_id, criterion, _ = selected
        if QMessageBox.question(
            self, "تأكيد المسح",
            f"هل تريد مسح المعيار «{criterion}» ومؤشراته؟",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            with self.db.connect() as con:
                con.execute(
                    """DELETE FROM subject_evaluation_indicator
                       WHERE criterion_id = ?""",
                    (criterion_id,),
                )
                con.execute(
                    """DELETE FROM subject_evaluation_criterion
                       WHERE id = ?""",
                    (criterion_id,),
                )
            self.load_evaluation_criteria()
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر مسح معيار التقييم: {exc}"
            )

    def load_expected_performance_subjects(self):
        self.clear_expected_performance_rows()
        self.expected_performance_subject_options = []
        if not self.selected_level_id or not self.selected_majal_id:
            return

        try:
            with self.db.connect() as con:
                subjects = con.execute(
                    """SELECT cm.id, cm.matiere, cm.competence
                       FROM competence_matiere AS cm
                       JOIN competence_majal AS cj
                         ON cj.id = cm.id_competence_majal
                       WHERE cj.id_level = ? AND cj.id_majal = ?
                       ORDER BY cm.matiere, cm.id""",
                    (self.selected_level_id, self.selected_majal_id),
                ).fetchall()
                performances = con.execute(
                    """SELECT p.competence_matiere_id, p.performance
                       FROM competence_year_end_performance AS p
                       JOIN competence_matiere AS cm
                         ON cm.id = p.competence_matiere_id
                       JOIN competence_majal AS cj
                         ON cj.id = cm.id_competence_majal
                       WHERE cj.id_level = ? AND cj.id_majal = ?
                       ORDER BY cm.matiere, cm.id""",
                    (self.selected_level_id, self.selected_majal_id),
                ).fetchall()
            subject_counts = {}
            for _, subject, _ in subjects:
                subject_counts[subject] = subject_counts.get(subject, 0) + 1
            subject_options = []
            for subject_id, subject, competence in subjects:
                label = subject
                if subject_counts[subject] > 1:
                    label = f"{subject} — {competence}"
                subject_options.append((subject_id, label))
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر تحميل مواد الأداء المنتظر: {exc}"
            )
            return

        self.expected_performance_subject_options = subject_options
        for subject_id, performance in performances:
            self.add_expected_performance_row(subject_id, performance)
        if not self.expected_performance_rows:
            self.add_expected_performance_row()

    def clear_expected_performance_rows(self):
        while self.expected_performance_rows_layout.count():
            item = self.expected_performance_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.expected_performance_rows.clear()

    def add_expected_performance_row(
        self, subject_id=None, performance=""
    ):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        subject_combo = QComboBox()
        subject_combo.setMinimumWidth(180)
        subject_combo.addItem("اختر المادة", None)
        for option_id, label in getattr(
            self, "expected_performance_subject_options", []
        ):
            subject_combo.addItem(label, option_id)
        row_layout.addWidget(subject_combo, 1)

        performance_edit = QPlainTextEdit()
        performance_edit.setPlaceholderText("اكتب الأداء المنتظر هنا")
        performance_edit.setFixedHeight(
            performance_edit.fontMetrics().lineSpacing() * 6 + 20
        )
        performance_edit.setPlainText(performance)
        row_layout.addWidget(performance_edit, 3)

        save_button = QPushButton("حفظ")
        save_button.setProperty("actionType", "edit")
        row_layout.addWidget(save_button)
        clear_button = QPushButton("مسح")
        clear_button.setProperty("actionType", "delete")
        row_layout.addWidget(clear_button)

        row = {
            "widget": row_widget,
            "combo": subject_combo,
            "edit": performance_edit,
        }
        self.expected_performance_rows.append(row)
        self.expected_performance_rows_layout.addWidget(row_widget)
        save_button.clicked.connect(
            lambda _checked=False, current_row=row:
                self.save_expected_performance_row(current_row)
        )
        clear_button.clicked.connect(
            lambda _checked=False, current_row=row:
                self.delete_expected_performance_row(current_row)
        )

        if subject_id is not None:
            subject_combo.setCurrentIndex(subject_combo.findData(subject_id))
        return row

    def save_expected_performance_row(self, row):
        subject_id = row["combo"].currentData()
        performance = row["edit"].toPlainText().strip()
        if not subject_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار المادة أولاً.")
            return
        if not performance:
            QMessageBox.warning(self, "بيانات ناقصة", "يرجى كتابة الأداء المنتظر.")
            return
        if len(performance.splitlines()) > 6:
            QMessageBox.warning(
                self, "عدد الأسطر غير صالح",
                "يجب ألا يتجاوز الأداء المنتظر ستة أسطر.",
            )
            return
        if any(
            other is not row and other["combo"].currentData() == subject_id
            for other in self.expected_performance_rows
        ):
            QMessageBox.warning(
                self, "المادة مكررة",
                "المادة مختارة في صف آخر؛ اختر مادة مختلفة.",
            )
            return
        try:
            with self.db.connect() as con:
                con.execute(
                    """INSERT INTO competence_year_end_performance(
                           competence_matiere_id, performance
                       ) VALUES (?, ?)
                       ON CONFLICT(competence_matiere_id)
                       DO UPDATE SET performance = excluded.performance""",
                    (subject_id, performance),
                )
        except Exception as exc:
            QMessageBox.critical(
                self, "خطأ", f"تعذر حفظ الأداء المنتظر: {exc}"
            )

    def delete_expected_performance_row(self, row):
        subject_id = row["combo"].currentData()
        if subject_id and QMessageBox.question(
            self, "تأكيد المسح",
            "هل تريد مسح الأداء المنتظر لهذه المادة؟",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            if subject_id:
                with self.db.connect() as con:
                    con.execute(
                        """DELETE FROM competence_year_end_performance
                           WHERE competence_matiere_id = ?""",
                        (subject_id,),
                    )
            self.expected_performance_rows.remove(row)
            row["widget"].deleteLater()
            if not self.expected_performance_rows:
                self.add_expected_performance_row()
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر مسح الأداء المنتظر: {exc}")

    def load_competence_majal_data(self):
        self.tbl_competence_majal.setUpdatesEnabled(False)
        self.tbl_competence_matiere.setUpdatesEnabled(False)
        try:
            self.tbl_competence_majal.setRowCount(0)
            self.tbl_competence_matiere.setRowCount(0)
            if not self.selected_level_id or not self.selected_majal_id:
                return

            with self.db.connect() as con:
                rows = con.execute(
                    """SELECT id, competence FROM competence_majal
                       WHERE id_majal = ? AND id_level = ? ORDER BY id""",
                    (self.selected_majal_id, self.selected_level_id),
                ).fetchall()

            for rec_id, competence in rows:
                row_index = self.tbl_competence_majal.rowCount()
                self.tbl_competence_majal.insertRow(row_index)
                item = QTableWidgetItem(competence)
                item.setData(Qt.UserRole, rec_id)
                self.tbl_competence_majal.setItem(row_index, 0, item)

            if self.tbl_competence_majal.rowCount() > 0:
                self.tbl_competence_majal.selectRow(0)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر تحميل كفايات المجال: {exc}")
        finally:
            self.tbl_competence_majal.setUpdatesEnabled(True)
            self.tbl_competence_matiere.setUpdatesEnabled(True)

    def on_competence_majal_selected(self):
        row = self.tbl_competence_majal.currentRow()
        if row < 0:
            self.selected_competence_majal_id = None
            self.tbl_competence_matiere.setRowCount(0)
            return
        
        item = self.tbl_competence_majal.item(row, 0)
        self.selected_competence_majal_id = item.data(Qt.UserRole)
        self.load_competence_matiere_data()

    def load_competence_matiere_data(self):
        self.tbl_competence_matiere.setRowCount(0)
        if not self.selected_competence_majal_id:
            return

        try:
            with self.db.connect() as con:
                for row in con.execute("""
                    SELECT id, matiere, competence FROM competence_matiere 
                    WHERE id_competence_majal = ?
                """, (self.selected_competence_majal_id,)).fetchall():
                    r = self.tbl_competence_matiere.rowCount()
                    self.tbl_competence_matiere.insertRow(r)
                    
                    item_matiere = QTableWidgetItem(row[1])
                    item_matiere.setData(Qt.UserRole, row[0])
                    item_comp = QTableWidgetItem(row[2])
                    
                    self.tbl_competence_matiere.setItem(r, 0, item_matiere)
                    self.tbl_competence_matiere.setItem(r, 1, item_comp)
        except Exception as e:
            print(f"Error loading competence_matiere: {e}")

    def copy_majal_with_matieres(self):
        if not self.selected_competence_majal_id:
            if self.tbl_competence_majal.rowCount() > 0:
                self.tbl_competence_majal.selectRow(0)
            else:
                QMessageBox.warning(self, "تنبيه", "لا توجد كفاية مجال مسجلة في هذا المستوى والمجال لنسخها.")
                return

        row = self.tbl_competence_majal.currentRow()
        item = self.tbl_competence_majal.item(row, 0)
        majal_competence_text = item.text()

        matieres_list = []
        try:
            with self.db.connect() as con:
                for r in con.execute("""
                    SELECT matiere, competence FROM competence_matiere 
                    WHERE id_competence_majal = ?
                """, (self.selected_competence_majal_id,)).fetchall():
                    matieres_list.append({"matiere": r[0], "competence": r[1]})

            self.copied_majal_data = {
                "competence": majal_competence_text,
                "matieres": matieres_list
            }
            QMessageBox.information(self, "نجاح النسخ", f"تم نسخ كفاية المجال مع {len(matieres_list)} من كفايات المواد التابعة لها بنجاح.")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء نسخ البيانات:\n{e}")

    def paste_majal_with_matieres(self):
        if not self.copied_majal_data:
            QMessageBox.warning(self, "تنبيه", "لا توجد بيانات منسوخة حالياً في الذاكرة.")
            return
        if not self.selected_level_id or not self.selected_majal_id:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار المستوى والمجال المستهدف للصق فيه.")
            return

        try:
            with self.db.connect() as con:
                cursor = con.cursor()
                cursor.execute("""
                    SELECT id FROM competence_majal 
                    WHERE id_majal = ? AND id_level = ?
                """, (self.selected_majal_id, self.selected_level_id))
                existing_row = cursor.fetchone()

                if existing_row:
                    majal_id = existing_row[0]
                    cursor.execute("""
                        UPDATE competence_majal 
                        SET competence = ? 
                        WHERE id = ?
                    """, (self.copied_majal_data["competence"], majal_id))
                    
                    cursor.execute("""
                        DELETE FROM competence_matiere 
                        WHERE id_competence_majal = ?
                    """, (majal_id,))
                else:
                    cursor.execute("""
                        INSERT INTO competence_majal (competence, id_majal, id_level) 
                        VALUES (?, ?, ?)
                    """, (self.copied_majal_data["competence"], self.selected_majal_id, self.selected_level_id))
                    majal_id = cursor.lastrowid

                for mat in self.copied_majal_data["matieres"]:
                    cursor.execute("""
                        INSERT INTO competence_matiere (matiere, competence, id_competence_majal) 
                        VALUES (?, ?, ?)
                    """, (mat["matiere"], mat["competence"], majal_id))

                con.commit()

            self.load_competence_majal_data()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء عملية اللصق:\n{e}")

    def add_competence_majal(self):
        if not self.selected_level_id or not self.selected_majal_id:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد المستوى والمجال أولاً.")
            return

        # ⬅️ استخدام الحقل المتعدد الأسطر (multiline)
        fields = [("نص كفاية المجال:", "multiline", "")]
        dlg = EntryDialog("إضافة كفاية مجال جديدة", fields, parent=self)
        if dlg.exec():
            vals = dlg.values()
            if not vals[0]:
                return
            try:
                with self.db.connect() as con:
                    con.execute("""
                        INSERT INTO competence_majal (competence, id_majal, id_level) 
                        VALUES (?, ?, ?)
                    """, (vals[0], self.selected_majal_id, self.selected_level_id))
                    con.commit()
                self.load_competence_majal_data()
                # تم إزالة رسالة النجاح المنبثقة بناءً على طلبك
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الإضافة (قد تكون موجودة مسبقاً):\n{e}")

    def edit_competence_majal(self):
        row = self.tbl_competence_majal.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد كفاية المجال للتعديل.")
            return
        
        item = self.tbl_competence_majal.item(row, 0)
        rec_id = item.data(Qt.UserRole)
        current_text = item.text()

        # ⬅️ استخدام الحقل المتعدد الأسطر (multiline)
        fields = [("تعديل نص كفاية المجال:", "multiline", current_text)]
        dlg = EntryDialog("تعديل كفاية المجال", fields, parent=self)
        if dlg.exec():
            vals = dlg.values()
            if not vals[0]:
                return
            try:
                with self.db.connect() as con:
                    con.execute("UPDATE competence_majal SET competence = ? WHERE id = ?", (vals[0], rec_id))
                    con.commit()
                self.load_competence_majal_data()
                # تم إزالة رسالة النجاح المنبثقة
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء التحديث:\n{e}")

    def delete_competence_majal(self):
        row = self.tbl_competence_majal.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد كفاية المجال للحذف.")
            return
        
        item = self.tbl_competence_majal.item(row, 0)
        rec_id = item.data(Qt.UserRole)

        if QMessageBox.question(self, "تأكيد الحذف", "حذف كفاية المجال سيؤدي لحذف كافة كفايات المواد والمكونات التابعة لها. هل أنت متأكد؟", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                with self.db.connect() as con:
                    con.execute("DELETE FROM competence_majal WHERE id = ?", (rec_id,))
                    con.commit()
                self.load_competence_majal_data()
                self.tbl_competence_matiere.setRowCount(0)
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الحذف:\n{e}")

    def add_competence_matiere(self):
        if not self.selected_competence_majal_id:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد كفاية المجال أولاً.")
            return

        # ⬅️ استخدام الحقل المتعدد الأسطر (multiline) لكفاية المادة
        fields = [
            ("اسم المادة:", "line", ""),
            ("نص كفاية المادة:", "multiline", "")
        ]
        dlg = EntryDialog("إضافة كفاية ومادة جديدة", fields, parent=self)
        if dlg.exec():
            vals = dlg.values()
            matiere, competence = vals[0], vals[1]
            if not matiere or not competence:
                QMessageBox.warning(self, "بيانات ناقصة", "اسم المادة وكفاية المادة حقلان أساسيان.")
                return
            try:
                with self.db.connect() as con:
                    con.execute("""
                        INSERT INTO competence_matiere (matiere, competence, id_competence_majal) 
                        VALUES (?, ?, ?)
                    """, (matiere, competence, self.selected_competence_majal_id))
                    con.commit()
                self.load_competence_matiere_data()
                # تم إزالة رسالة النجاح المنبثقة
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الإضافة (قد تكون المادة مسجلة مسبقاً بنفس السياق):\n{e}")

    def edit_competence_matiere(self):
        row = self.tbl_competence_matiere.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد السطر المراد تعديله.")
            return
        
        item_matiere = self.tbl_competence_matiere.item(row, 0)
        item_comp = self.tbl_competence_matiere.item(row, 1)
        rec_id = item_matiere.data(Qt.UserRole)
        
        # ⬅️ استخدام الحقل المتعدد الأسطر (multiline) لكفاية المادة
        fields = [
            ("اسم المادة:", "line", item_matiere.text()),
            ("نص كفاية المادة:", "multiline", item_comp.text())
        ]
        dlg = EntryDialog("تعديل المادة وكفايتها", fields, parent=self)
        if dlg.exec():
            vals = dlg.values()
            matiere, competence = vals[0], vals[1]
            if not matiere or not competence:
                QMessageBox.warning(self, "بيانات ناقصة", "جميع الحقول مطلوبة.")
                return
            try:
                with self.db.connect() as con:
                    con.execute("""
                        UPDATE competence_matiere 
                        SET matiere = ?, competence = ? 
                        WHERE id = ?
                    """, (matiere, competence, rec_id))
                    con.commit()
                self.load_competence_matiere_data()
                # تم إزالة رسالة النجاح المنبثقة
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء التحديث:\n{e}")

    def delete_competence_matiere(self):
        row = self.tbl_competence_matiere.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد المادة المراد حذفها.")
            return
        
        item = self.tbl_competence_matiere.item(row, 0)
        rec_id = item.data(Qt.UserRole)

        if QMessageBox.question(self, "تأكيد الحذف", "هل أنت متأكد من حذف هذه المادة وكفايتها؟", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                with self.db.connect() as con:
                    con.execute("DELETE FROM competence_matiere WHERE id = ?", (rec_id,))
                    con.commit()
                self.load_competence_matiere_data()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر الحذف:\n{e}")


class TimetableDialog(QDialog):
    """جدول الأوقات الأسبوعي: يُملأ آليًا بأكثر حصة تكرّرت في كل يوم وساعة (باستعمال pandas)."""

    DAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
    FIRST_HOUR = 8
    LAST_HOUR = 17          # نهاية آخر خانة 16:00 - 17:00
    _AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

    def __init__(self, df_history, parent=None, schedule=None):
        super().__init__(parent)
        self.setWindowTitle("جدول الأوقات")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1280, 520)
        self.n_slots = self.LAST_HOUR - self.FIRST_HOUR

        layout = QVBoxLayout(self)
        title = QLabel("🗓 جدول الأوقات")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1E40AF; padding: 4px;")
        layout.addWidget(title)

        self.table = QTableWidget(len(self.DAYS), self.n_slots)
        self.table.setHorizontalHeaderLabels(
            [f"{h:02d}:00 - {h + 1:02d}:00" for h in range(self.FIRST_HOUR, self.LAST_HOUR)]
        )
        self.table.setVerticalHeaderLabels(self.DAYS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setMinimumWidth(80)
        layout.addWidget(self.table, 1)

        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #555;")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox()
        buttons.addButton("إغلاق", QDialogButtonBox.RejectRole)
        set_dialog_button_action_types(buttons)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        schedule = (
            schedule if schedule is not None else self.build_schedule(df_history)
        )
        self.fill_table(schedule)

    # ---------- التحليل ----------
    @classmethod
    def _parse_heure(cls, text):
        """يرجع (بداية، نهاية) بالدقائق من نص مثل '08:00-09:00'، والنهاية None إن غابت."""
        text = str(text or "").translate(cls._AR_DIGITS)
        found = re.findall(r"(\d{1,2})\s*[:hH.]\s*(\d{2})", text)
        if not found:
            return None, None
        start = int(found[0][0]) * 60 + int(found[0][1])
        end = int(found[1][0]) * 60 + int(found[1][1]) if len(found) > 1 else None
        return start, end

    @classmethod
    def _duration_minutes(cls, heure, time_text):
        start, end = cls._parse_heure(heure)
        if start is not None and end is not None and end > start:
            return end - start
        m = re.search(r"\d+", str(time_text or "").translate(cls._AR_DIGITS))
        return int(m.group()) if m else 60

    @classmethod
    def schedule_time_bounds(cls, df):
        if df is None or df.empty:
            return cls.FIRST_HOUR, cls.LAST_HOUR
        import pandas as pd

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        df = df[df["date"].dt.dayofweek <= 5]
        starts = []
        ends = []
        for row in df.itertuples(index=False):
            classe = str(row.classe or "").strip()
            majal = str(row.majal or "").strip()
            if not classe and not majal:
                continue
            start, _end = cls._parse_heure(row.heure)
            if start is None or not 0 <= start < 24 * 60:
                continue
            duration = max(
                60, cls._duration_minutes(row.heure, row.time)
            )
            starts.append(start // 60)
            ends.append(min(24, (start + duration + 59) // 60))
        if not starts:
            return cls.FIRST_HOUR, cls.LAST_HOUR
        first_hour = min(starts)
        last_hour = max(ends)
        return first_hour, max(first_hour + 1, last_hour)

    @classmethod
    def build_schedule(cls, df, first_hour=None, last_hour=None):
        """يرجع {صف_اليوم: [(عمود، امتداد، نص، تكرار)]} بعد اختيار الأكثر تكرارًا دون تداخل."""
        if df is None or df.empty:
            return {}
        import pandas as pd

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        df["wd"] = df["date"].dt.dayofweek
        df = df[df["wd"] <= 5]          # من الإثنين إلى السبت فقط

        first_hour = (
            cls.FIRST_HOUR if first_hour is None else first_hour
        )
        last_hour = cls.LAST_HOUR if last_hour is None else last_hour
        n_slots = last_hour - first_hour
        counter = {}
        for r in df.itertuples(index=False):
            classe = str(r.classe or "").strip()
            raw_club_name = getattr(r, "cultural_club_name", "")
            club_name = (
                str(raw_club_name).strip()
                if pd.notna(raw_club_name) else ""
            )
            if club_name.casefold() in {"nan", "none"}:
                club_name = ""
            if club_name:
                classe = f"ناد: {club_name}"
            majal = str(r.majal or "").strip()
            if not classe and not majal:
                continue
            start, _end = cls._parse_heure(r.heure)
            if start is None:
                continue
            col = start // 60 - first_hour
            if not 0 <= col < n_slots:
                continue
            minutes = cls._duration_minutes(r.heure, r.time)
            span = max(
                1,
                min((minutes + 59) // 60, n_slots - col),
            )
            key = (int(r.wd), col, span, classe, majal)
            counter[key] = counter.get(key, 0) + 1

        schedule = {}
        for wd in range(len(cls.DAYS)):
            candidates = [(cnt, k) for k, cnt in counter.items() if k[0] == wd]
            # الأكثر تكرارًا أولًا، وعند التساوي الأبكر ثم الأطول
            candidates.sort(key=lambda x: (-x[0], x[1][1], -x[1][2]))
            occupied, cells = set(), []
            for cnt, (_wd, col, span, classe, majal) in candidates:
                cols = set(range(col, col + span))
                if cols & occupied:
                    continue
                occupied |= cols
                text = f"{classe}:{majal}" if classe and majal else (classe or majal)
                cells.append((col, span, text, cnt))
            schedule[wd] = cells
        return schedule

    # ---------- العرض ----------
    def fill_table(self, schedule):
        palette = ["#DBEAFE", "#DCFCE7", "#FEF3C7", "#FCE7F3", "#E0E7FF", "#CCFBF1", "#FFEDD5"]
        colors, total = {}, 0
        for wd, cells in schedule.items():
            for col, span, text, cnt in cells:
                _class_name, separator, majal = text.rpartition(":")
                if not separator:
                    majal = text
                color = colors.setdefault(majal, palette[len(colors) % len(palette)])
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(color))
                item.setForeground(QColor("#111827"))
                item.setToolTip(f"{text}\nتكرّرت {cnt} مرة" + (" (حصة مدتها 120 دقيقة)" if span > 1 else ""))
                self.table.setItem(wd, col, item)
                if span > 1:
                    self.table.setSpan(wd, col, 1, span)
                total += 1
        if total:
            self.info_label.setText(
                "يُملأ الجدول بأكثر حصة تكرّرت في كل يوم وساعة بحسب السجل. "
                "الحصص ذات 120 دقيقة تُدمج خليتاها."
            )
        else:
            self.info_label.setText("لا توجد حصص مسجلة بعد لبناء جدول الأوقات.")





class ConceptManagerDialog(QDialog):
    """حوار إدارة المفاهيم (CRUD كامل لجدول concept).

    يُفتح بالاختصار Ctrl+Shift+R. عمود name فريد (UNIQUE) ولا يُسمح بالتكرار.
    """

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة المفاهيم المتصلة بالمقاربة بالكفايات")
        self.resize(720, 520)
        self.setLayoutDirection(Qt.RightToLeft)
        self.db = db if db else Database(DB_PATH)
        self.selected_concept_id = None
        self.init_ui()
        self.load_concepts()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        title_label = QLabel("🧠 إدارة المفاهيم (اسم العنصر + محتوى العنصر)")
        title_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #1E40AF; padding: 5px;"
        )
        main_layout.addWidget(title_label)

        btns_layout = QHBoxLayout()
        for text, slot, act_type in [
            ("إضافة", self.add_concept, "add"),
            ("تعديل", self.edit_concept, "edit"),
            ("حذف", self.delete_concept, "delete"),
        ]:
            b = QPushButton(text)
            b.setMinimumWidth(110)
            b.setProperty("actionType", act_type)
            b.clicked.connect(slot)
            btns_layout.addWidget(b)
        btns_layout.addStretch()
        main_layout.addLayout(btns_layout)

        self.tbl_concepts = QTableWidget(0, 2)
        self.tbl_concepts.setHorizontalHeaderLabels(["اسم العنصر", "محتوى العنصر"])
        self.tbl_concepts.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_concepts.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_concepts.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_concepts.setAlternatingRowColors(True)
        self.tbl_concepts.verticalHeader().setVisible(False)
        self.tbl_concepts.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_concepts.itemSelectionChanged.connect(self.on_concept_selected)
        main_layout.addWidget(self.tbl_concepts, 1)

        self.lbl_status = QLabel("0 مفهوم")
        self.lbl_status.setStyleSheet("color: #6B7280; padding: 3px;")
        main_layout.addWidget(self.lbl_status)

        close_btn = QPushButton("إغلاق")
        close_btn.setProperty("actionType", "close")
        close_btn.clicked.connect(self.accept)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(close_btn)
        main_layout.addLayout(bottom_layout)

    def load_concepts(self):
        self.tbl_concepts.setUpdatesEnabled(False)
        try:
            self.tbl_concepts.setRowCount(0)
            with self.db.connect() as con:
                rows = con.execute(
                    "SELECT id, name, content FROM concept ORDER BY name COLLATE NOCASE"
                ).fetchall()
            for rec_id, name, content in rows:
                r = self.tbl_concepts.rowCount()
                self.tbl_concepts.insertRow(r)
                item_name = QTableWidgetItem(name)
                item_name.setData(Qt.UserRole, rec_id)
                self.tbl_concepts.setItem(r, 0, item_name)
                self.tbl_concepts.setItem(r, 1, QTableWidgetItem(content or ""))
            self.lbl_status.setText(f"{self.tbl_concepts.rowCount()} مفهوم")
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر تحميل المفاهيم:\n{exc}")
        finally:
            self.tbl_concepts.setUpdatesEnabled(True)

    def on_concept_selected(self):
        row = self.tbl_concepts.currentRow()
        if row < 0:
            self.selected_concept_id = None
            return
        item = self.tbl_concepts.item(row, 0)
        self.selected_concept_id = item.data(Qt.UserRole) if item else None

    def add_concept(self):
        dlg = EntryDialog(
            "إضافة مفهوم جديد",
            [("اسم العنصر:", "line", ""), ("محتوى العنصر:", "multiline", "")],
            parent=self,
        )
        if not dlg.exec():
            return
        vals = dlg.values()
        name = vals[0]
        content = vals[1]
        try:
            self.db.save_concept(name, content)
            self.load_concepts()
        except ValueError as exc:
            QMessageBox.warning(self, "اسم مكرر", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر إضافة المفهوم:\n{exc}")

    def edit_concept(self):
        if not self.selected_concept_id:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد مفهوم للتعديل.")
            return
        row = self.tbl_concepts.currentRow()
        current_name = self.tbl_concepts.item(row, 0).text()
        current_content = self.tbl_concepts.item(row, 1).text()
        dlg = EntryDialog(
            "تعديل المفهوم",
            [("اسم العنصر:", "line", ""), ("محتوى العنصر:", "multiline", "")],
            values=[current_name, current_content],
            parent=self,
        )
        if not dlg.exec():
            return
        vals = dlg.values()
        try:
            self.db.save_concept(vals[0], vals[1], concept_id=self.selected_concept_id)
            self.load_concepts()
        except ValueError as exc:
            QMessageBox.warning(self, "اسم مكرر", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر تعديل المفهوم:\n{exc}")

    def delete_concept(self):
        if not self.selected_concept_id:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد مفهوم للحذف.")
            return
        row = self.tbl_concepts.currentRow()
        name = self.tbl_concepts.item(row, 0).text()
        confirm = QMessageBox.question(
            self, "تأكيد الحذف",
            f"هل تريد حذف المفهوم '{name}'؟",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.db.delete_concept(self.selected_concept_id)
            self.selected_concept_id = None
            self.load_concepts()
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر حذف المفهوم:\n{exc}")
