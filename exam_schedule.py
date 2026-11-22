"""Exam scheduling page."""
import sqlite3

from PySide6.QtCore import QDate, QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


_MONTH_NAMES = (
    "جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان",
    "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)
_WEEKDAY_LABELS = ("اثـ", "ثلا", "أر", "خ", "ج", "سـ", "أح")


class ExamMonthCard(QFrame):
    dateSelected = Signal(object)

    def __init__(self, year, month, exam_days, selected_date, parent=None):
        super().__init__(parent)
        self.setObjectName("examScheduleMonthCard")
        colors = (
            ("#2563EB", "#EFF6FF"),
            ("#059669", "#ECFDF5"),
            ("#D97706", "#FFFBEB"),
            ("#7C3AED", "#F5F3FF"),
            ("#DB2777", "#FDF2F8"),
        )
        accent, background = colors[(month - 1) % len(colors)]
        self.setStyleSheet(
            "QFrame#examScheduleMonthCard {"
            f"background-color: {background}; border: 1px solid {accent}; "
            f"border-top: 3px solid {accent}; border-radius: 9px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 9)
        layout.setSpacing(5)

        title = QLabel(f"{_MONTH_NAMES[month - 1]} {year}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 11pt; font-weight: bold; color: #1E3A8A; "
            "border: none; background: transparent;"
        )
        layout.addWidget(title)

        days_grid = QGridLayout()
        days_grid.setContentsMargins(0, 0, 0, 0)
        days_grid.setHorizontalSpacing(2)
        days_grid.setVerticalSpacing(2)
        for column, weekday in enumerate(_WEEKDAY_LABELS):
            label = QLabel(weekday)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                "font-size: 9pt; font-weight: bold; color: #475569; "
                "border: none; background: transparent;"
            )
            days_grid.addWidget(label, 0, column)

        first_day = QDate(year, month, 1)
        for day in range(1, first_day.daysInMonth() + 1):
            current_date = QDate(year, month, day)
            date_key = current_date.toString("yyyy-MM-dd")
            day_exams = exam_days.get(date_key, ())
            button = QPushButton(str(day))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(24)
            button.setMaximumHeight(28)
            button.pressed.connect(
                lambda value=current_date: self.dateSelected.emit(value)
            )
            if day_exams:
                tooltip = "\n".join(
                    f"{exam[2]} — {exam[6]} ({exam[5]})"
                    for exam in day_exams
                )
                button.setToolTip(
                    f"{tooltip}\n{current_date.toString('dd/MM/yyyy')}"
                )
                button.setStyleSheet(
                    "QPushButton {font-weight: bold; color: #1D4ED8; "
                    "background-color: #DBEAFE; border: 1px solid #60A5FA; "
                    "border-radius: 5px; padding: 0; min-height: 24px;}"
                    "QPushButton:hover {background-color: #BFDBFE;}"
                )
            else:
                button.setStyleSheet(
                    "QPushButton {color: #334155; background-color: #FFFFFF; "
                    "border: 1px solid #DBEAFE; border-radius: 5px; "
                    "padding: 0; min-height: 24px;}"
                    "QPushButton:hover {background-color: #DBEAFE;}"
                )
            if current_date == selected_date:
                button.setStyleSheet(
                    button.styleSheet()
                    + "QPushButton {border: 2px solid #0F172A;}"
                )
            day_offset = first_day.dayOfWeek() - 1 + day - 1
            days_grid.addWidget(
                button, day_offset // 7 + 1, day_offset % 7
            )
        layout.addLayout(days_grid)


class ExamSchedulePage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._editing_exam_id = None
        self._read_only = False
        self._daily_options = []
        self._exam_rows = []
        self.month_cards = []
        self.setObjectName("examSchedulePage")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        body = QHBoxLayout(self)
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)

        months_panel = QWidget()
        months_panel_layout = QVBoxLayout(months_panel)
        months_panel_layout.setContentsMargins(0, 0, 0, 0)
        months_panel_layout.setSpacing(6)
        months_header = QHBoxLayout()
        self.school_year_label = QLabel()
        self.school_year_label.setStyleSheet(
            "font-size: 11pt; font-weight: bold; color: #1E3A8A;"
        )
        months_header.addWidget(self.school_year_label)
        months_header.addStretch(1)
        months_header.addWidget(QLabel("الأيام المميزة تتضمن امتحانات"))
        months_panel_layout.addLayout(months_header)

        self.months_scroll = QScrollArea()
        self.months_scroll.setObjectName("examScheduleMonthsScroll")
        self.months_scroll.setWidgetResizable(True)
        self.months_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.months_container = QWidget()
        self.months_container.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.months_grid = QGridLayout(self.months_container)
        self.months_grid.setContentsMargins(4, 4, 8, 4)
        self.months_grid.setSpacing(8)
        self.months_scroll.setWidget(self.months_container)
        months_panel_layout.addWidget(self.months_scroll, 1)
        body.addWidget(months_panel, 4)

        management_panel = QWidget()
        management_panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        management_panel.setMinimumWidth(430)
        management_panel.setMaximumWidth(590)
        management_layout = QVBoxLayout(management_panel)
        management_layout.setContentsMargins(0, 0, 0, 0)
        management_layout.setSpacing(8)

        self.selected_date_label = QLabel()
        self.selected_date_label.setObjectName("examSelectedDateLabel")
        self.selected_date_label.setStyleSheet(
            "font-size: 11pt; font-weight: bold; color: #1E3A8A;"
        )
        management_layout.addWidget(self.selected_date_label)

        self.exam_table = QTableWidget(0, 5)
        self.exam_table.setObjectName("examScheduleTable")
        self.exam_table.setHorizontalHeaderLabels([
            "المعرّف", "وقت البدء", "المدة", "القسم", "النشاط",
        ])
        self.exam_table.setColumnHidden(0, True)
        self.exam_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.exam_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.exam_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.exam_table.setAlternatingRowColors(True)
        self.exam_table.verticalHeader().setVisible(False)
        self.exam_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.exam_table.setMinimumHeight(170)
        self.exam_table.itemSelectionChanged.connect(
            self._update_action_state
        )
        self.exam_table.cellDoubleClicked.connect(self._edit_exam_row)
        management_layout.addWidget(self.exam_table, 2)

        self.during_regular_lessons_check = QCheckBox(
            "أثناء السير العادي للدروس"
        )
        self.during_regular_lessons_check.setObjectName(
            "examDuringRegularLessonsCheck"
        )
        self.during_regular_lessons_check.setChecked(True)
        management_layout.addWidget(self.during_regular_lessons_check)

        self.exam_date_edit = QDateEdit(QDate.currentDate())
        self.exam_date_edit.setObjectName("examDateEdit")
        self.exam_date_edit.setCalendarPopup(True)
        self.exam_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.exam_date_edit.setLocale(
            QLocale(QLocale.Language.Arabic, QLocale.Country.Tunisia)
        )

        self.start_time_combo = QComboBox()
        self.start_time_combo.setObjectName("examStartTimeCombo")
        self.start_time_combo.addItem("يُحدد من جدول الأوقات", "")

        self.class_combo = QComboBox()
        self.class_combo.setObjectName("examClassCombo")
        self.class_combo.addItem("اختر القسم", None)
        self.class_combo.currentIndexChanged.connect(
            self._refresh_subject_options
        )

        self.subject_combo = QComboBox()
        self.subject_combo.setObjectName("examSubjectCombo")
        self.subject_combo.addItem("اختر المادة", "")
        self.subject_combo.currentIndexChanged.connect(
            self._refresh_subject_details
        )

        self.activities_list = QListWidget()
        self.activities_list.setObjectName("examActivitiesList")
        self.activities_list.setMaximumHeight(130)

        self.duration_spin = QSpinBox()
        self.duration_spin.setObjectName("examDurationMinutesSpin")
        self.duration_spin.setRange(1, 600)
        self.duration_spin.setValue(60)
        self.duration_spin.setSuffix(" دقيقة")

        form = QFormLayout()
        form.setVerticalSpacing(4)
        form.addRow("التاريخ:", self.exam_date_edit)
        form.addRow("القسم:", self.class_combo)
        form.addRow("مادة التدريس:", self.subject_combo)
        form.addRow("أنشطة الامتحان:", self.activities_list)
        form.addRow("وقت البدء حسب جدول الأوقات:", self.start_time_combo)
        form.addRow("مدة الامتحان:", self.duration_spin)
        management_layout.addLayout(form)

        self.assignments_hint = QLabel()
        self.assignments_hint.setWordWrap(True)
        self.assignments_hint.setStyleSheet("color: #64748B;")
        management_layout.addWidget(self.assignments_hint)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("إضافة امتحان")
        self.save_button.setObjectName("saveExamScheduleButton")
        self.save_button.setProperty("actionType", "add")
        self.save_button.clicked.connect(self.save_exam)
        buttons.addWidget(self.save_button)

        self.cancel_edit_button = QPushButton("إلغاء التعديل")
        self.cancel_edit_button.setObjectName("cancelExamEditButton")
        self.cancel_edit_button.setProperty("actionType", "browse")
        self.cancel_edit_button.clicked.connect(self.reset_form)
        self.cancel_edit_button.hide()
        buttons.addWidget(self.cancel_edit_button)

        self.edit_button = QPushButton("تعديل المحدد")
        self.edit_button.setObjectName("editExamScheduleButton")
        self.edit_button.setProperty("actionType", "edit")
        self.edit_button.clicked.connect(self.edit_selected_exam)
        buttons.addWidget(self.edit_button)

        self.delete_button = QPushButton("حذف المحدد")
        self.delete_button.setObjectName("deleteExamScheduleButton")
        self.delete_button.setProperty("actionType", "delete")
        self.delete_button.clicked.connect(self.delete_selected_exam)
        buttons.addWidget(self.delete_button)
        management_layout.addLayout(buttons)
        body.addWidget(management_panel, 1)

        self._set_school_year_range()
        self.exam_date_edit.dateChanged.connect(self._date_changed)
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_month_cards()

    def layout_month_cards(self):
        while self.months_grid.count():
            self.months_grid.takeAt(0)
        available_width = self.months_scroll.viewport().width()
        column_count = max(1, min(5, (available_width + 8) // 228))
        for column in range(5):
            self.months_grid.setColumnStretch(column, 0)
        for index, card in enumerate(self.month_cards):
            row, column = divmod(index, column_count)
            self.months_grid.addWidget(card, row, column)
        for column in range(column_count):
            self.months_grid.setColumnStretch(column, 1)

    def _set_school_year_range(self):
        years = self.db.school_years()
        year_name = next(
            (
                name for year_id, name in years
                if year_id == self.db.year_id
            ),
            self.db.school_year_name_for_date(),
        )
        try:
            first_year = int(str(year_name).split("-", 1)[0])
        except ValueError as error:
            raise ValueError(
                f"اسم السنة الدراسية غير صالح: {year_name}"
            ) from error
        self._first_school_year = first_year
        first_day = QDate(first_year, 9, 1)
        last_day = QDate(first_year + 1, 6, 30)
        self.exam_date_edit.setMinimumDate(first_day)
        self.exam_date_edit.setMaximumDate(last_day)
        selected_date = self.exam_date_edit.date()
        if selected_date < first_day or selected_date > last_day:
            self.exam_date_edit.setDate(first_day)
        self.school_year_label.setText(f"السنة الدراسية {year_name}")

    def _refresh_assigned_classes(self):
        exam_date = self.exam_date_edit.date().toString("yyyy-MM-dd")
        self._daily_options = self.db.exam_schedule_options(exam_date)
        classes = {}
        for option in self._daily_options:
            classes.setdefault(
                option["class_id"], option["class_name"]
            )
        selected_class_id = self.class_combo.currentData()
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        self.class_combo.addItem("اختر القسم", None)
        for class_id, class_name in classes.items():
            self.class_combo.addItem(class_name, class_id)
        selected_index = self.class_combo.findData(selected_class_id)
        if selected_index > 0:
            self.class_combo.setCurrentIndex(selected_index)
        self.class_combo.blockSignals(False)
        self._refresh_subject_options()
        if self._daily_options:
            self.assignments_hint.setText(
                "تظهر الأقسام والمواد وأوقات البدء المسجلة في جدول الأوقات "
                "لليوم المحدد."
            )
        else:
            self.assignments_hint.setText(
                "لا توجد حصص مسجلة لهذا اليوم في جدول الأوقات."
            )

    def _refresh_subject_options(self):
        selected_subject = self.subject_combo.currentData()
        class_id = self.class_combo.currentData()
        subjects = list(dict.fromkeys(
            option["subject"] for option in self._daily_options
            if option["class_id"] == class_id
        ))
        self.subject_combo.blockSignals(True)
        self.subject_combo.clear()
        self.subject_combo.addItem("اختر المادة", "")
        for subject in subjects:
            self.subject_combo.addItem(subject, subject)
        selected_index = self.subject_combo.findData(selected_subject)
        if selected_index > 0:
            self.subject_combo.setCurrentIndex(selected_index)
        self.subject_combo.blockSignals(False)
        self._refresh_subject_details()

    def _refresh_subject_details(self):
        class_id = self.class_combo.currentData()
        subject = self.subject_combo.currentData()
        matching_options = [
            option for option in self._daily_options
            if option["class_id"] == class_id
            and option["subject"] == subject
        ]
        selected_time = self.start_time_combo.currentData()
        times = list(dict.fromkeys(
            option["start_time"] for option in matching_options
        ))
        self.start_time_combo.blockSignals(True)
        self.start_time_combo.clear()
        if not times:
            self.start_time_combo.addItem(
                "يُحدد وقت البدء من جدول الأوقات", ""
            )
        else:
            for start_time in times:
                self.start_time_combo.addItem(start_time, start_time)
            selected_index = self.start_time_combo.findData(selected_time)
            self.start_time_combo.setCurrentIndex(
                selected_index if selected_index >= 0 else 0
            )
        self.start_time_combo.blockSignals(False)

        selected_activities = {
            self.activities_list.item(index).text()
            for index in range(self.activities_list.count())
            if self.activities_list.item(index).checkState()
            == Qt.CheckState.Checked
        }
        self.activities_list.clear()
        available_activities = (
            matching_options[0]["activities"] if matching_options else []
        )
        for activity in available_activities:
            item = QListWidgetItem(activity)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if activity in selected_activities
                else Qt.CheckState.Unchecked
            )
            self.activities_list.addItem(item)

    def refresh(self):
        try:
            self._refresh_assigned_classes()
            self._exam_rows = self.db.exam_schedules()
        except (sqlite3.Error, ValueError) as error:
            QMessageBox.critical(
                self, "تعذر تحميل مواعيد الامتحانات", str(error)
            )
            return
        exams_by_date = {}
        for row in self._exam_rows:
            exams_by_date.setdefault(row[1], []).append(row)
        self._refresh_month_cards(exams_by_date)
        selected_date = self.exam_date_edit.date()
        weekday_name = QLocale(
            QLocale.Language.Arabic, QLocale.Country.Tunisia
        ).toString(selected_date, "dddd")
        self.selected_date_label.setText(
            f"امتحانات يوم {weekday_name}، "
            f"{selected_date.toString('dd/MM/yyyy')}"
        )
        date_key = selected_date.toString("yyyy-MM-dd")
        daily_exams = [
            row for row in self._exam_rows if row[1] == date_key
        ]
        self.exam_table.setRowCount(len(daily_exams))
        for row_index, record in enumerate(daily_exams):
            exam_id = record[0]
            start_time = record[2]
            class_id = record[4]
            class_name = record[5]
            activities = record[8]
            duration = record[7]
            values = (
                str(exam_id),
                start_time,
                f"{duration} دقيقة",
                class_name,
                "، ".join(activities) if activities else record[6],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, exam_id)
                elif column == 2:
                    item.setData(Qt.ItemDataRole.UserRole, duration)
                elif column == 3:
                    item.setData(Qt.ItemDataRole.UserRole, class_id)
                self.exam_table.setItem(row_index, column, item)
        self.exam_table.setColumnHidden(0, True)
        self._update_action_state()

    def _refresh_month_cards(self, exams_by_date):
        while self.months_grid.count():
            item = self.months_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.month_cards = []
        selected_date = self.exam_date_edit.date()
        for offset in range(10):
            month_number = 9 + offset
            year = self._first_school_year
            if month_number > 12:
                month_number -= 12
                year += 1
            self.month_cards.append(ExamMonthCard(
                year,
                month_number,
                exams_by_date,
                selected_date,
                self.months_container,
            ))
            self.month_cards[-1].dateSelected.connect(
                self.select_month_date
            )
        self.layout_month_cards()

    def select_month_date(self, date_value):
        self.reset_form()
        self.exam_date_edit.blockSignals(True)
        self.exam_date_edit.setDate(date_value)
        self.exam_date_edit.blockSignals(False)
        self.refresh()

    def _date_changed(self, selected_date):
        if selected_date.isValid():
            self.reset_form()
            self.refresh()

    def _selected_exam_id(self):
        selected_rows = self.exam_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(
                self, "مواعيد الامتحانات", "يرجى تحديد امتحان أولاً."
            )
            return None
        item = self.exam_table.item(selected_rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _edit_exam_row(self, row):
        self.exam_table.selectRow(row)
        self.edit_selected_exam()

    def _update_action_state(self):
        has_selection = bool(
            self.exam_table.selectionModel().selectedRows()
        )
        can_edit = not self._read_only
        self.save_button.setEnabled(
            can_edit and bool(self._daily_options)
        )
        self.edit_button.setEnabled(can_edit and has_selection)
        self.delete_button.setEnabled(can_edit and has_selection)
        self.cancel_edit_button.setEnabled(can_edit)

    def set_read_only(self, read_only):
        self._read_only = bool(read_only)
        self._update_action_state()

    def save_exam(self):
        if self._read_only:
            return
        class_id = self.class_combo.currentData()
        subject = self.subject_combo.currentData()
        start_time = self.start_time_combo.currentData()
        activities = [
            self.activities_list.item(index).text()
            for index in range(self.activities_list.count())
            if self.activities_list.item(index).checkState()
            == Qt.CheckState.Checked
        ]
        if class_id is None or not subject or not start_time or not activities:
            QMessageBox.warning(
                self,
                "بيانات ناقصة",
                "اختر قسمًا ومادة ووقتًا من جدول الأوقات ونشاطًا واحدًا على الأقل.",
            )
            return
        data = {
            "exam_date": self.exam_date_edit.date().toString("yyyy-MM-dd"),
            "start_time": start_time,
            "classe_id": class_id,
            "subject": subject,
            "activities": activities,
            "duration_minutes": self.duration_spin.value(),
            "during_regular_lessons": (
                self.during_regular_lessons_check.isChecked()
            ),
        }
        try:
            self.db.save_exam_schedule(data, self._editing_exam_id)
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(
                self, "تعذر حفظ الامتحان", str(error)
            )
            return
        self.reset_form()
        self.refresh()

    def edit_selected_exam(self):
        if self._read_only:
            return
        exam_id = self._selected_exam_id()
        if exam_id is None:
            return
        row = self.exam_table.selectionModel().selectedRows()[0].row()
        self._editing_exam_id = exam_id
        class_id = self.exam_table.item(row, 3).data(
            Qt.ItemDataRole.UserRole
        )
        self.class_combo.setCurrentIndex(
            self.class_combo.findData(class_id)
        )
        exam_record = next(
            record for record in self._exam_rows
            if record[0] == exam_id
        )
        subject = exam_record[6]
        self.subject_combo.setCurrentIndex(
            self.subject_combo.findData(subject)
        )
        start_time = self.exam_table.item(row, 1).text()
        self.start_time_combo.setCurrentIndex(
            self.start_time_combo.findData(start_time)
        )
        duration = self.exam_table.item(row, 2).data(
            Qt.ItemDataRole.UserRole
        )
        self.duration_spin.setValue(duration)
        activities = exam_record[8]
        self.during_regular_lessons_check.setChecked(
            bool(exam_record[9])
        )
        for index in range(self.activities_list.count()):
            item = self.activities_list.item(index)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.text() in activities
                else Qt.CheckState.Unchecked
            )
        self.save_button.setText("حفظ التعديل")
        self.save_button.setProperty("actionType", "edit")
        self.cancel_edit_button.show()

    def delete_selected_exam(self):
        if self._read_only:
            return
        exam_id = self._selected_exam_id()
        if exam_id is None:
            return
        answer = QMessageBox.question(
            self,
            "حذف الامتحان",
            "هل تريد حذف موعد الامتحان المحدد؟",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.delete_exam_schedule(exam_id)
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(
                self, "تعذر حذف الامتحان", str(error)
            )
            return
        self.reset_form()
        self.refresh()

    def reset_form(self):
        self._editing_exam_id = None
        self.save_button.setText("إضافة امتحان")
        self.save_button.setProperty("actionType", "add")
        self.cancel_edit_button.hide()
        self.class_combo.setCurrentIndex(0)
        self.subject_combo.setCurrentIndex(0)
        self.start_time_combo.setCurrentIndex(0)
        for index in range(self.activities_list.count()):
            self.activities_list.item(index).setCheckState(
                Qt.CheckState.Unchecked
            )
        self.duration_spin.setValue(60)
        self.during_regular_lessons_check.setChecked(True)
        self._update_action_state()
