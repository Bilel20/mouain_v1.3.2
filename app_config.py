# -*- coding: utf-8 -*-
"""Extracted module app_config."""
from pathlib import Path
import sys

import qtawesome as qta

from PySide6.QtCore import QEvent, QObject, QSize, QTranslator
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QMainWindow,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QStyleOptionToolButton,
    QToolButton,
    QWidget,
)

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR
ICON_PATH = BASE_DIR / "icons" / "icon.ico"
TEACHER_AVATAR_ICONS = {
    "ذكر": BASE_DIR / "icons" / "teacher_male.svg",
    "أنثى": BASE_DIR / "icons" / "teacher_female.svg",
}
FONTS_DIR = BASE_DIR / "fonts"
TEMPLATE_PATH = BASE_DIR / "template.odt"
SMALL_WINDOW_MAX_WIDTH = 1100


def is_small_window(widget):
    """Use the top-level window width as the shared small-profile measure."""
    return widget.window().width() <= SMALL_WINDOW_MAX_WIDTH


def get_db_path():
    """Return the database path beside the application, independent of cwd."""
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = BASE_DIR
    return str(base_dir / "school_data.db")

DB_PATH = get_db_path()

ACTION_CONFIG = {
    "close": {"icon": "fa-times", "keywords": ("إغلاق", "اغلاق", "close")},
    "back": {"icon": "fa-arrow-left", "keywords": ("تراجع", "رجوع", "عودة", "back")},
    "cancel": {"icon": "fa-ban", "keywords": ("إلغاء", "الغاء", "cancel")},
    "delete": {"icon": "fa-trash", "keywords": ("حذف", "delete")},
    "clear": {"icon": "fa-eraser", "keywords": ("مسح", "clear")},
    "export": {"icon": "fa-file-export", "keywords": ("تصدير", "export")},
    "print": {"icon": "fa-print", "keywords": ("طباعة", "print")},
    "browse": {
        "icon": "fa-eye",
        "keywords": ("معاينة", "استعراض", "عرض", "فتح", "browse", "open", "show"),
    },
    "menu": {"icon": "fa-bars", "keywords": ()},
    "copy_paste": {
        "icon": "fa-copy",
        "keywords": ("نسخ", "لصق", "copy", "paste"),
    },
    "edit": {"icon": "fa-edit", "keywords": ("تعديل", "edit")},
    "save": {
        "icon": "fa-save",
        "keywords": ("إضافة الحصص", "حفظ", "موافق", "نعم", "متابعة الاستيراد", "save"),
    },
    "add": {"icon": "fa-plus", "keywords": ("إضافة", "اضافة", "add")},
    "time": {"icon": "fa-clock", "keywords": ()},
    "card_edit": {"icon": "fa-edit", "keywords": ()},
    "card_delete": {"icon": "fa-trash", "keywords": ()},
    "card_copy_paste": {"icon": "fa-copy", "keywords": ()},
    "card_export": {"icon": "fa-file-export", "keywords": ()},
    "card_print": {"icon": "fa-print", "keywords": ()},
    "card_browse": {"icon": "fa-eye", "keywords": ()},
    "card_configure": {"icon": "fa-edit", "keywords": ()},
    "card_distribute": {"icon": "fa-arrow-right", "keywords": ()},
    "integration_undo": {"icon": "fa-undo", "keywords": ()},
    "integration_redo": {"icon": "fa-redo", "keywords": ()},
    "evaluation_undo": {"icon": "fa-undo", "keywords": ()},
    "evaluation_redo": {"icon": "fa-redo", "keywords": ()},
}

SCHOOL_INFO_COLUMNS = (
    "nom_annee",
    "nom_ecole",
    "nom_enseignant",
    "nom_inspecteur",
    "grade",
    "nom_assistant_pedagogique",
    "diplomes_scientifiques",
    "date_recrutement",
    "date_titularisation",
    "date_derniere_visite",
    "note_pedagogique",
    "resume_rapport_visite",
    "langue",
    "telephone",
    "email",
    "situation_familiale",
    "nombre_enfants",
    "delegation_regional_education",
    "inspection_district",
    "school_code",
    "school_phone",
    "school_principal",
    "date_promotion",
    "inspecteur_rapport_pedagogique",
    "identifiant_unique",
    "email_inspecteur",
    "email_school_principal",
    "email_assistant_pedagogique",
    "school_address",
    "training_certificates",
    "teacher_gender",
)

TEACHER_GENDER_OPTIONS = ("", "ذكر", "أنثى")

ACTIVITIES_BY_MAJAL = {
    "اللغة العربية": ["تواصل شفوي", "قراءة", "إنتاج كتابي", "استعمال قواعد اللغة",
                      "محفوظات", "وحدة اللغة العربية", "رسم وإملاء", "إملاء", "رسم", "مطالعة", "حوار منظم"],
    "العلوم والتكنولوجيا": ["رياضيات", "إيقاظ علمي", "تربية تكنولوجية"],
    "التنشئة الفنية": ["تربية تشكيلية", "تربية موسيقية"],
    "التنشئة الاجتماعية": ["تربية إسلامية", "هدي قرآني", "عقيدة", "أخلاق", "عبادات", "تاريخ", "جغرافيا", "تربية مدنية"],
    "التنشئة البدنية": ["رياضة"],
}
DETAIL_KEYS_BY_NAMAT = {
    "منهجي": ["المحتوى", "هدف الحصة", "السند الرئيسي", "مفهوم صحي أو سكاني", "المهارة الحياتية", "القصيدة"],
    "إدماج": ["الكفايات المستهدفة", "مفهوم صحي أو سكاني", "المهارة الحياتية"],
    "تقييم": ["الأداء المنتظر", "مفهوم صحي أو سكاني", "المهارة الحياتية"],
    "دعم وعلاج": ["المعايير المستهدفة", "مفهوم صحي أو سكاني", "المهارة الحياتية"],
}

PLANS_NAMES = {
    "وحدة اللغة العربية": {"المجال":"اللغة العربية", "الأنشطة":["تواصل شفوي", "قراءة", "إنتاج كتابي", "استعمال قواعد اللغة",
                      "محفوظات", "وحدة اللغة العربية", "رسم وإملاء", "إملاء", "رسم", "مطالعة", "حوار منظم"], "الرمز":"لغة ع"},
    "رياضيات": {"المجال":"العلوم والتكنولوجيا", "الأنشطة":["رياضيات"], "الرمز":"رياضيات"},
    "إيقاظ علمي": {"المجال":"العلوم والتكنولوجيا", "الأنشطة":["إيقاظ علمي"], "الرمز":"إ. علمي"},
    "تربية تكنولوجية": {"المجال":"العلوم والتكنولوجيا", "الأنشطة":["تربية تكنولوجية"], "الرمز":"تر تك"},
    "تربية تشكيلية": {"المجال":"التنشئة الفنية", "الأنشطة":["تربية تشكيلية"], "الرمز":"تر تشك"},
    "تربية موسيقية": {"المجال":"التنشئة الفنية", "الأنشطة":["تربية موسيقية"], "الرمز":"تر موسيـ"},
    "تربية إسلامية": {"المجال":"التنشئة الاجتماعية", "الأنشطة":["تربية إسلامية", "هدي قرآني", "عقيدة", "أخلاق", "عبادات"], "الرمز":"تر إسلا"},
    "تاريخ": {"المجال":"التنشئة الاجتماعية", "الأنشطة":["تاريخ"], "الرمز":"تاريخ"},
    "جغرافيا": {"المجال":"التنشئة الاجتماعية", "الأنشطة":["جغرافيا"], "الرمز":"جغرافيا"},
    "تربية مدنية": {"المجال":"التنشئة الاجتماعية", "الأنشطة":["تربية مدنية"], "الرمز":"تر مدن"},
    "مواد الاجتماعية": {"المجال":"التنشئة الاجتماعية", "الأنشطة":["مواد الاجتماعية"], "الرمز":"مواد اجتماع"},
    "تنشئة فنية": {"المجال":"التنشئة الفنية", "الأنشطة":["تنشئة فنية", "تربية تشكيلية", "تربية موسيقية"]},
    "رياضة": {"المجال":"التنشئة البدنية", "الأنشطة":["رياضة"], "الرمز":"رياضة"},
}

LEVEL_FIRAKS = {
    "س1+2":{"الدرجة":"الأولى",
            "المستويات":["السنة الأولى", "السنة الثانية"],
            "الأقسام":[
                {"القسم":"س1","المستوى":"السنة الأولى"},
                {"القسم":"س2","المستوى":"السنة الثانية"}
            ]
        },
    "س3+4":{"الدرجة":"الثانية",
            "المستويات":["السنة الثالثة", "السنة الرابعة"], 
            "الأقسام":[
                {"القسم":"س3","المستوى":"السنة الثالثة"},
                {"القسم":"س4","المستوى":"السنة الرابعة"}
            ]
        },
    "س5+6":{"الدرجة":"الثالثة",
            "المستويات":["السنة الخامسة", "السنة السادسة"], 
            "الأقسام":[
                {"القسم":"س5","المستوى":"السنة الخامسة"},
                {"القسم":"س6","المستوى":"السنة السادسة"}
            ]
        }
}


def level_firak_label(firak_key):
    """Return the combined levels followed by the multi-grade label."""
    firak = LEVEL_FIRAKS.get(str(firak_key or "").strip())
    if firak is None:
        raise ValueError(f"فوج الأقسام المتعددة غير مسجل: {firak_key}")
    levels = list(dict.fromkeys(
        str(section["المستوى"]).strip()
        for section in firak["الأقسام"]
        if str(section.get("المستوى") or "").strip()
    ))
    if len(levels) < 2:
        raise ValueError(
            f"يجب أن يضم الفوج مستويين دراسيين على الأقل: {firak_key}"
        )
    return f"{' + '.join(levels)} فرق"


def level_firak_selection_label(firak_key):
    """Return a concise label for a multi-grade level selection."""
    firak = LEVEL_FIRAKS.get(str(firak_key or "").strip())
    if firak is None:
        raise ValueError(f"فوج الأقسام المتعددة غير مسجل: {firak_key}")
    levels = list(dict.fromkeys(
        str(section["المستوى"]).strip()
        for section in firak["الأقسام"]
        if str(section.get("المستوى") or "").strip()
    ))
    if len(levels) < 2:
        raise ValueError(
            f"يجب أن يضم الفوج مستويين دراسيين على الأقل: {firak_key}"
        )
    return " - ".join(levels)


def _apply_action_button_icon(button):
    style = button.style()
    style.unpolish(button)
    style.polish(button)
    button.update()

    action_type = button.property("actionType")
    config = ACTION_CONFIG.get(action_type)
    if config is None:
        if button.property("actionIconManaged"):
            button.setIcon(QIcon())
            button.setProperty("actionIconManaged", False)
        return
    is_card_action = str(action_type).startswith("card_")
    is_floating_menu = action_type == "menu"
    is_floating_action = str(action_type).startswith((
        "integration_", "evaluation_",
    ))
    if (
        not is_card_action
        and not is_floating_action
        and not is_floating_menu
        and not button.icon().isNull()
        and not button.property("actionIconManaged")
    ):
        return
    icon_name = config["icon"].replace("fa-", "fa5s.", 1)
    object_name = button.objectName()
    if is_card_action or is_floating_action or is_floating_menu:
        icon_color = "#1F3155" if is_floating_menu else "#475569"
        padding = "0px" if is_floating_menu else "3px"
        button.setStyleSheet(
            "QToolButton, QPushButton { "
            "background: transparent; background-color: transparent; "
            f"border: none; padding: {padding}; }} "
            "QToolButton:hover, QPushButton:hover, "
            "QToolButton:pressed, QPushButton:pressed, "
            "QToolButton:checked, QPushButton:checked, "
            "QToolButton:disabled, QPushButton:disabled { "
            "background: transparent; background-color: transparent; "
            "border: none; }"
        )
        if isinstance(button, QToolButton):
            button.setAutoRaise(True)
        button.setIconSize(
            QSize(14, 14)
            if is_floating_menu
            else QSize(18, 18)
            if is_floating_action
            else QSize(16, 16)
        )
    elif (
        "transparent" in button.styleSheet().casefold()
        or object_name in {
            "teachingAssignmentRemoveButton",
            "teachingAssignmentSubjectRemoveButton",
        }
    ):
        icon_color = "#B91C1C" if action_type == "delete" else "#475569"
    elif object_name in {
        "centeredNavigationMenuItem",
        "cardActionButton",
        "officialTreeCopyButton",
        "timetableEntryRemoveButton",
    }:
        icon_color = "#334155"
    elif object_name in {
        "editTeacherTimetableButton",
        "editTeacherTimetableHoursButton",
        "showTeacherTimetablePaletteButton",
    }:
        icon_color = "#1D4ED8"
    else:
        icon_color = "#FFFFFF"
    button.setIcon(qta.icon(icon_name, color=icon_color))
    button.setProperty("actionIconManaged", True)
    _update_responsive_button_content(button)


def set_card_action_type(button, action):
    """Apply the shared icon-only, transparent style for a card action."""
    action_type = str(action or "").strip()
    if not action_type.startswith("card_"):
        action_aliases = {
            "copy": "copy_paste",
            "export_json": "export",
            "export_pdf": "export",
            "preview": "browse",
            "preview_pdf": "browse",
        }
        action_type = f"card_{action_aliases.get(action_type, action_type)}"
    if action_type not in ACTION_CONFIG:
        raise ValueError(f"Unknown card action type: {action_type}")
    button.setProperty("actionType", action_type)
    _apply_action_button_icon(button)


def set_action_button_type(button, action_type):
    """Apply a configured application action type and its icon."""
    action_type = str(action_type or "").strip()
    if action_type not in ACTION_CONFIG:
        raise ValueError(f"Unknown action type: {action_type}")
    button.setProperty("actionType", action_type)
    _apply_action_button_icon(button)


def _update_responsive_button_content(button):
    if not isinstance(button, QAbstractButton):
        return
    if button.property("responsiveTextRequired"):
        return

    compact = bool(button.property("responsiveIconOnly"))
    visible_text = button.text()
    full_text = button.property("responsiveFullText")

    if visible_text and not compact:
        full_text = visible_text
        button.setProperty("responsiveFullText", full_text)
        button.setProperty("responsiveFullToolTip", button.toolTip())
    elif full_text is None:
        return
    elif compact and visible_text:
        full_text = visible_text
        button.setProperty("responsiveFullText", full_text)

    full_text = str(full_text or "")
    if not full_text:
        return

    if button.icon().isNull():
        should_compact = False
    else:
        if isinstance(button, QToolButton):
            option = QStyleOptionToolButton()
            control = QStyle.ContentsType.CT_ToolButton
        elif isinstance(button, QPushButton):
            option = QStyleOptionButton()
            control = QStyle.ContentsType.CT_PushButton
        else:
            return
        option.initFrom(button)
        option.text = full_text
        option.icon = button.icon()
        option.iconSize = button.iconSize()
        if isinstance(button, QToolButton):
            option.toolButtonStyle = button.toolButtonStyle()
        content_size = QSize(
            button.fontMetrics().horizontalAdvance(full_text)
            + button.iconSize().width()
            + 8,
            max(button.fontMetrics().height(), button.iconSize().height()),
        )
        required_width = button.style().sizeFromContents(
            control, option, content_size, button
        ).width()
        if isinstance(button, QToolButton):
            horizontal_margin = max(
                34,
                2
                * button.style().pixelMetric(
                    QStyle.PixelMetric.PM_ButtonMargin, None, button
                ),
            )
            required_width = max(
                required_width, content_size.width() + horizontal_margin
            )
        should_compact = button.width() < required_width

    if should_compact == compact:
        return

    if should_compact:
        original_tooltip = str(
            button.property("responsiveFullToolTip") or ""
        )
        tooltip = original_tooltip
        if full_text not in tooltip:
            tooltip = f"{tooltip}\n{full_text}".strip()
        button.setProperty("responsiveButtonUpdating", True)
        try:
            button.setText("")
            button.setToolTip(tooltip)
            button.setProperty("responsiveIconOnly", True)
        finally:
            button.setProperty("responsiveButtonUpdating", False)
    else:
        button.setProperty("responsiveButtonUpdating", True)
        try:
            button.setText(full_text)
            button.setToolTip(
                str(button.property("responsiveFullToolTip") or "")
            )
            button.setProperty("responsiveIconOnly", False)
        finally:
            button.setProperty("responsiveButtonUpdating", False)


class ActionButtonIconFilter(QObject):
    def __init__(self, application):
        super().__init__(application)
        self._application = application
        self._button_scale = 1.0

    def set_button_scale(self, scale):
        self._button_scale = float(scale)
        for widget in self._application.allWidgets():
            if isinstance(widget, QAbstractButton):
                self._apply_button_scale(widget)

    @staticmethod
    def _scaled_size(size, scale):
        def scaled_dimension(value):
            if value >= 1_000_000:
                return value
            return max(0, round(value * scale))

        return QSize(
            scaled_dimension(size.width()),
            scaled_dimension(size.height()),
        )

    def _apply_button_scale(self, button):
        if button.property("responsiveScaleApplying"):
            return

        if button.property("responsiveScaleBaseFont") is None:
            button.setProperty("responsiveScaleBaseFont", QFont(button.font()))
            button.setProperty(
                "responsiveScaleBaseIconSize", QSize(button.iconSize())
            )
            button.setProperty(
                "responsiveScaleBaseMinimumSize", QSize(button.minimumSize())
            )
            button.setProperty(
                "responsiveScaleBaseMaximumSize", QSize(button.maximumSize())
            )
            button.setProperty(
                "responsiveScaleBaseSizeHint", QSize(button.sizeHint())
            )

        scale = self._button_scale
        button.setProperty("responsiveScaleApplying", True)
        try:
            font = QFont(button.property("responsiveScaleBaseFont"))
            if font.pointSizeF() > 0:
                font.setPointSizeF(font.pointSizeF() * scale)
            elif font.pixelSize() > 0:
                font.setPixelSize(max(1, round(font.pixelSize() * scale)))
            button.setFont(font)

            base_icon_size = button.property("responsiveScaleBaseIconSize")
            if base_icon_size.width() > 0 and base_icon_size.height() > 0:
                button.setIconSize(self._scaled_size(base_icon_size, scale))

            responsive_fixed_size = button.property(
                "responsiveScaleFixedSize"
            )
            if isinstance(responsive_fixed_size, QSize):
                button.setFixedSize(
                    self._scaled_size(responsive_fixed_size, scale)
                )
            else:
                base_minimum = button.property(
                    "responsiveScaleBaseMinimumSize"
                )
                base_maximum = button.property(
                    "responsiveScaleBaseMaximumSize"
                )
                minimum = self._scaled_size(base_minimum, scale)
                if button.property("responsiveScalePreserveWidth"):
                    minimum.setWidth(base_minimum.width())
                button.setMinimumSize(minimum)
                base_size_hint = button.property(
                    "responsiveScaleBaseSizeHint"
                )
                if scale < 1.0:
                    maximum = QSize(
                        self._scaled_maximum_dimension(
                            base_minimum.width(),
                            base_maximum.width(),
                            base_size_hint.width(),
                            scale,
                        ),
                        self._scaled_maximum_dimension(
                            base_minimum.height(),
                            base_maximum.height(),
                            base_size_hint.height(),
                            scale,
                        ),
                    )
                else:
                    maximum = base_maximum
                if button.property("responsiveScalePreserveWidth"):
                    maximum.setWidth(base_maximum.width())
                button.setMaximumSize(maximum)
        finally:
            button.setProperty("responsiveScaleApplying", False)

    @staticmethod
    def _scaled_maximum_dimension(minimum, maximum, size_hint, scale):
        scaled_minimum = max(0, round(minimum * scale))
        dimension = maximum
        if maximum >= 1_000_000:
            dimension = max(minimum, size_hint)
            if dimension <= 0:
                return maximum
        return max(scaled_minimum, round(dimension * scale))

    def eventFilter(self, watched, event):
        if isinstance(watched, QAbstractButton):
            event_type = event.type()
            if event_type == QEvent.Type.Show:
                self._apply_button_scale(watched)
            if event_type in {
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.FontChange,
                QEvent.Type.StyleChange,
                QEvent.Type.LayoutDirectionChange,
            }:
                _update_responsive_button_content(watched)
            elif (
                event_type == QEvent.Type.ToolTipChange
                and not watched.property("responsiveButtonUpdating")
                and not watched.property("responsiveIconOnly")
            ):
                watched.setProperty(
                    "responsiveFullToolTip", watched.toolTip()
                )
        if (
            event.type() == QEvent.Type.DynamicPropertyChange
            and bytes(event.propertyName()) == b"actionType"
            and isinstance(watched, QAbstractButton)
        ):
            _apply_action_button_icon(watched)
            _update_responsive_button_content(watched)
        return False


class DialogSizeFilter(QObject):
    def __init__(self, application):
        super().__init__(application)
        self._application = application

    @staticmethod
    def _parent_window(dialog, application):
        parent = dialog.parentWidget()
        if parent is not None:
            return parent.window()

        for window in application.topLevelWidgets():
            if (
                isinstance(window, QMainWindow)
                and window is not dialog
                and window.isVisible()
            ):
                return window
        return None

    def _fit_dialog(self, dialog):
        parent_window = self._parent_window(dialog, self._application)
        if parent_window is None:
            return

        width = parent_window.width()
        height = parent_window.height()
        if width <= 0 or height <= 0:
            return

        if not hasattr(dialog, "_responsive_base_minimum_size"):
            dialog._responsive_base_minimum_size = QSize(dialog.minimumSize())
            dialog._responsive_base_maximum_size = QSize(dialog.maximumSize())

        base_minimum = dialog._responsive_base_minimum_size
        base_maximum = dialog._responsive_base_maximum_size
        maximum_width = min(width, base_maximum.width())
        maximum_height = min(height, base_maximum.height())
        dialog.setMinimumSize(
            min(base_minimum.width(), maximum_width),
            min(base_minimum.height(), maximum_height),
        )
        dialog.setMaximumSize(maximum_width, maximum_height)
        dialog.resize(
            min(dialog.width(), maximum_width),
            min(dialog.height(), maximum_height),
        )

    def eventFilter(self, watched, event):
        event_type = event.type()
        if isinstance(watched, QDialog) and event_type == QEvent.Type.Show:
            self._fit_dialog(watched)
        elif isinstance(watched, QWidget) and event_type == QEvent.Type.Resize:
            for dialog in self._application.topLevelWidgets():
                if (
                    isinstance(dialog, QDialog)
                    and dialog.isVisible()
                    and self._parent_window(
                        dialog, self._application
                    ) is watched
                ):
                    self._fit_dialog(dialog)
        return False


_action_button_icon_filter = None
_dialog_size_filter = None


def install_action_button_icon_filter(application):
    global _action_button_icon_filter
    if _action_button_icon_filter is not None:
        application.removeEventFilter(_action_button_icon_filter)
    _action_button_icon_filter = ActionButtonIconFilter(application)
    application.installEventFilter(_action_button_icon_filter)
    return _action_button_icon_filter


def install_dialog_size_filter(application):
    global _dialog_size_filter
    if _dialog_size_filter is not None:
        application.removeEventFilter(_dialog_size_filter)
    _dialog_size_filter = DialogSizeFilter(application)
    application.installEventFilter(_dialog_size_filter)
    return _dialog_size_filter


def set_application_button_scale(application, scale):
    button_filter = _action_button_icon_filter
    if button_filter is None:
        button_filter = install_action_button_icon_filter(application)
    button_filter.set_button_scale(scale)


def set_dialog_button_action_types(button_box):
    for button in button_box.buttons():
        if button.property("actionType"):
            _apply_action_button_icon(button)
            continue
        text = button.text().replace("&", "").strip().casefold()
        for action_type, config in ACTION_CONFIG.items():
            if any(
                keyword.casefold() in text
                for keyword in config["keywords"]
            ):
                button.setProperty("actionType", action_type)
                _apply_action_button_icon(button)
                break
        if button.property("actionType"):
            continue

        role_getter = getattr(button_box, "buttonRole", None)
        if not callable(role_getter):
            continue
        role = role_getter(button)
        role_name = getattr(role, "name", "")
        role_actions = {
            "AcceptRole": "save",
            "YesRole": "save",
            "RejectRole": "cancel",
            "NoRole": "cancel",
            "DestructiveRole": "delete",
            "HelpRole": "browse",
            "ApplyRole": "save",
        }
        action_type = role_actions.get(role_name)
        if action_type:
            button.setProperty("actionType", action_type)
            _apply_action_button_icon(button)


def load_custom_font():
    if FONTS_DIR.exists() and FONTS_DIR.is_dir():
        font_files = list(FONTS_DIR.glob("*.ttf")) + list(FONTS_DIR.glob("*.otf"))
        if font_files:
            font_path = str(font_files[0])
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                font_families = QFontDatabase.applicationFontFamilies(font_id)
                if font_families:
                    return font_families[0]
    return "Noto Naskh Arabic"


class ArabicDialogTranslator(QTranslator):
    BUTTON_TRANSLATIONS = {
        "&Yes": "&نعم",
        "Yes": "نعم",
        "&No": "&لا",
        "No": "لا",
        "&OK": "&حسناً",
        "OK": "حسناً",
        "&Cancel": "&إلغاء",
        "Cancel": "إلغاء",
        "&Close": "&إغلاق",
        "Close": "إغلاق",
        "&Save": "&حفظ",
        "Save": "حفظ",
        "Save All": "حفظ الكل",
        "Don't Save": "عدم الحفظ",
        "&Open": "&فتح",
        "Open": "فتح",
        "&Apply": "&تطبيق",
        "Apply": "تطبيق",
        "&Discard": "&تجاهل",
        "Discard": "تجاهل",
        "&Retry": "&إعادة المحاولة",
        "Retry": "إعادة المحاولة",
        "&Abort": "&إيقاف",
        "Abort": "إيقاف",
        "&Ignore": "&تجاهل",
        "Ignore": "تجاهل",
        "Yes to All": "نعم للكل",
        "No to All": "لا للكل",
        "Restore Defaults": "استعادة الافتراضي",
        "&Help": "&مساعدة",
        "Help": "مساعدة",
        "&Reset": "&إعادة التعيين",
        "Reset": "إعادة التعيين",
    }

    def translate(self, context, source_text, disambiguation=None, n=-1):
        return self.BUTTON_TRANSLATIONS.get(source_text, source_text)
