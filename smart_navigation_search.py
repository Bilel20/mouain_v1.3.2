import base64
import json
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    Signal,
    QSize,
    QPoint,
    QRect,
    QObject,
    QRunnable,
)
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizeGrip,
    QHBoxLayout,
    QVBoxLayout,
)
_ARABIC_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")
_CODE_KEYWORD_PATTERN = re.compile(
    r"(?im)^\s*(?:def|class|import|from|return|function|const|let|var|"
    r"SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b"
)
_CODE_OPERATOR_PATTERN = re.compile(
    r"(?:=>|==|!=|:=|</|/>|::|->|&&|\|\||\{\s*['\"]?\w+['\"]?\s*:)"
)
_MIN_SEARCH_MATCH_RATIO = 0.6


def _database_table_label(table_name):
    return {
        "ann_scolaire": "بيانات المعلم والمؤسسة",
        "day_data": "يوم دراسي",
        "hessa": "حصة دراسية",
        "nachat": "نشاط",
        "nachat_detail": "تفاصيل نشاط",
        "majal": "مجال",
        "learning_mode": "نمط تعلم",
        "competence_majal": "كفاية في مجال",
        "competence_matiere": "مادة وكفاية",
        "moukawan_kifaya": "كفاية مستهدفة",
        "objectif_specifique": "هدف خاص",
        "content": "محتوى برنامج رسمي",
        "concept": "مفهوم",
        "official_holiday": "عطلة",
        "assessment_file": "ملف تقييم ومتابعة",
        "assessment_file_activity": "نشاط تقييم",
        "cultural_club": "نادي ثقافي",
        "cultural_club_monthly_plan": "مخطط شهري لناد",
        "cultural_club_monthly_session": "جلسة ناد شهرية",
        "cultural_club_monthly_property": "خاصية جلسة ناد",
        "cultural_club_daily_session": "جلسة ناد يومية",
        "cultural_club_daily_property": "خاصية جلسة ناد",
        "teaching_plan": "مخطط تعليمي",
        "teaching_plan_activity": "نشاط في مخطط تعليمي",
        "teaching_plan_item": "عنصر مخطط تعليمي",
        "teaching_plan_item_detail": "تفاصيل مخطط تعليمي",
        "teaching_plan_activity_property": "خاصية نشاط مخطط",
        "teaching_plan_personal_content": "محتوى شخصي في مخطط",
        "lesson_repeat_request": "طلب إعادة حصة",
    }.get(table_name, "بيانات التطبيق")


def _looks_like_programming_code(text):
    value = str(text or "").strip()
    if not value:
        return False
    if "```" in value or _CODE_KEYWORD_PATTERN.search(value):
        return True
    if _CODE_OPERATOR_PATTERN.search(value):
        return True
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) >= 2:
        code_lines = sum(
            bool(
                re.match(
                    r"(?:[\w.$]+\s*=\s*|[{}();]\s*$|"
                    r"(?:if|for|while|try|except)\b)",
                    line,
                )
            )
            for line in lines
        )
        return code_lines >= 2
    return False


class _NavigationSearchSignals(QObject):
    completed = Signal(int, str, object)
    failed = Signal(int, str, str)


class NavigationSearchTask(QRunnable):
    def __init__(self, search_index, revision, query):
        super().__init__()
        self._search_index = search_index
        self._revision = revision
        self._query = query
        self.signals = _NavigationSearchSignals()

    def run(self):
        try:
            results = self._search_index.search(self._query)
        except Exception as error:
            self.signals.failed.emit(
                self._revision, self._query, str(error)
            )
            return
        self.signals.completed.emit(
            self._revision, self._query, results
        )


def _normalize_search_text(text):
    normalized = unicodedata.normalize("NFKC", str(text or "").lower())
    normalized = _ARABIC_DIACRITICS.sub("", normalized).replace("ـ", "")
    return (
        normalized.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )


def _search_term_match_ratio(query, text):
    terms = re.findall(r"\w+", _normalize_search_text(query))
    if not terms:
        return 0.0
    normalized_text = _normalize_search_text(text)
    return sum(term in normalized_text for term in terms) / len(terms)


def _database_result_day(connection, table_name, values):
    day_queries = {
        "hessa": (
            "SELECT d.date FROM day_data d "
            "JOIN hessa h ON h.day_data_id = d.id WHERE h.id = ?",
            values.get("id"),
        ),
        "nachat": (
            "SELECT d.date FROM day_data d "
            "JOIN hessa h ON h.day_data_id = d.id "
            "JOIN nachat n ON n.hessa_id = h.id WHERE n.id = ?",
            values.get("id"),
        ),
        "nachat_detail": (
            "SELECT d.date FROM day_data d "
            "JOIN hessa h ON h.day_data_id = d.id "
            "JOIN nachat n ON n.hessa_id = h.id "
            "JOIN nachat_detail nd ON nd.nachat_id = n.id "
            "WHERE nd.id = ?",
            values.get("id"),
        ),
        "lesson_repeat_request": (
            "SELECT d.date FROM day_data d "
            "JOIN hessa h ON h.day_data_id = d.id "
            "JOIN lesson_repeat_request r ON r.lesson_id = h.id "
            "WHERE r.id = ?",
            values.get("id"),
        ),
        "lesson_repeat_activity": (
            "SELECT d.date FROM day_data d "
            "JOIN hessa h ON h.day_data_id = d.id "
            "JOIN nachat n ON n.hessa_id = h.id "
            "JOIN lesson_repeat_activity ra "
            "ON ra.source_activity_id = n.id "
            "WHERE ra.request_id = ? AND ra.source_activity_id = ?",
            (values.get("request_id"), values.get("source_activity_id")),
        ),
        "cultural_club_daily_session": (
            "SELECT session_date FROM cultural_club_daily_session WHERE id = ?",
            values.get("id"),
        ),
        "cultural_club_daily_property": (
            "SELECT s.session_date FROM cultural_club_daily_session s "
            "JOIN cultural_club_daily_property p "
            "ON p.daily_session_id = s.id WHERE p.id = ?",
            values.get("id"),
        ),
        "cultural_club_daily_repeat_request": (
            "SELECT s.session_date FROM cultural_club_daily_session s "
            "JOIN cultural_club_daily_repeat_request r "
            "ON r.source_daily_session_id = s.id WHERE r.id = ?",
            values.get("id"),
        ),
    }
    if table_name == "day_data":
        day_text = values.get("date")
    elif table_name in day_queries:
        query, row_parameters = day_queries[table_name]
        if not isinstance(row_parameters, tuple):
            row_parameters = (row_parameters,)
        row = connection.execute(query, row_parameters).fetchone()
        day_text = row[0] if row else None
    else:
        return None

    day_text = str(day_text or "")
    return day_text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_text) else None


def _database_result_context(connection, table_name, values):
    if table_name == "teaching_plan_activity":
        row = connection.execute(
            "SELECT id, plan_id, lesson_number, learning_mode "
            "FROM teaching_plan_activity WHERE id = ?",
            (values.get("id"),),
        ).fetchone()
    elif table_name == "teaching_plan_activity_property":
        row = connection.execute(
            "SELECT a.id, a.plan_id, a.lesson_number, a.learning_mode "
            "FROM teaching_plan_activity a "
            "WHERE a.id = ?",
            (values.get("activity_id"),),
        ).fetchone()
    else:
        return None
    if row is None:
        return None
    return {
        "type": "teaching_plan_activity",
        "activity_id": row[0],
        "plan_id": row[1],
        "lesson_number": row[2],
        "learning_mode": row[3],
    }


def _database_result_details(connection, table_name, values, text_columns):
    column_labels = {
        "nom_annee": "السنة الدراسية",
        "nom_ecole": "المؤسسة",
        "nom_enseignant": "المعلم",
        "nom_inspecteur": "المتفقد",
        "grade": "الرتبة",
        "nom_assistant_pedagogique": "المساعد البيداغوجي",
        "diplomes_scientifiques": "الشهادات العلمية",
        "date_recrutement": "تاريخ الانتداب",
        "date_titularisation": "تاريخ الترسيم",
        "date_derniere_visite": "تاريخ آخر زيارة",
        "note_pedagogique": "العدد البيداغوجي",
        "resume_rapport_visite": "ملخص تقرير الزيارة",
        "langue": "اللغة",
        "telephone": "الهاتف",
        "email": "البريد الإلكتروني",
        "situation_familiale": "الحالة العائلية",
        "nombre_enfants": "عدد الأبناء",
        "teacher_gender": "جنس المعلم",
        "delegation_regional_education": "المندوبية الجهوية للتربية",
        "inspection_district": "مركز التفقد",
        "school_code": "رمز المؤسسة",
        "school_phone": "هاتف المؤسسة",
        "school_principal": "مدير المؤسسة",
        "date_promotion": "تاريخ الترقية",
        "inspecteur_rapport_pedagogique": "تقرير المتفقد البيداغوجي",
        "identifiant_unique": "المعرّف الوحيد",
        "email_inspecteur": "بريد المتفقد الإلكتروني",
        "email_school_principal": "بريد مدير المؤسسة الإلكتروني",
        "email_assistant_pedagogique": "بريد المساعد البيداغوجي الإلكتروني",
        "school_address": "عنوان المؤسسة",
        "training_certificates": "الشهادات التكوينية",
        "name": "الاسم",
        "title": "العنوان",
        "content": "المحتوى",
        "description": "الوصف",
        "key_name": "اسم الخاصية",
        "value_text": "قيمة الخاصية",
        "activity_name": "النشاط",
        "lesson_goal": "هدف الحصة",
        "specific_objective": "الهدف الخاص",
        "target_competencies": "الكفايات المستهدفة",
        "evaluation": "التقييم",
        "expected_performance": "الأداء المنتظر",
        "target_criteria": "المعايير المستهدفة",
        "demographic_concept": "المفهوم الديمغرافي",
        "health_concept": "المفهوم الصحي",
        "life_skills": "المهارات الحياتية",
    }
    details = {}

    def add_detail(label, value):
        value = " ".join(str(value or "").split())
        if value:
            details.setdefault(label, value)

    for column in text_columns:
        add_detail(
            column_labels.get(column, "معلومات إضافية"),
            values.get(column),
        )

    if table_name in (
        "teaching_plan_activity",
        "teaching_plan_activity_property",
    ):
        activity_id = (
            values.get("id")
            if table_name == "teaching_plan_activity"
            else values.get("activity_id")
        )
        try:
            activity = connection.execute(
                "SELECT a.plan_id, a.lesson_number, a.learning_mode, "
                "a.activity_name, a.content, a.lesson_goal, "
                "a.specific_objective, a.target_competencies, a.evaluation, "
                "a.expected_performance, a.target_criteria, "
                "a.demographic_concept, a.health_concept, a.life_skills, "
                "a.duration_minutes, p.title "
                "FROM teaching_plan_activity a "
                "LEFT JOIN teaching_plan p ON p.id=a.plan_id "
                "WHERE a.id = ?",
                (activity_id,),
            ).fetchone()
        except sqlite3.Error:
            activity = None
        if activity is not None:
            activity_labels = (
                "رقم المخطط",
                "رقم الحصة",
                "النمط",
                "النشاط",
                "المحتوى",
                "هدف الحصة",
                "الهدف الخاص",
                "الكفايات المستهدفة",
                "التقييم",
                "الأداء المنتظر",
                "المعايير المستهدفة",
                "المفهوم الديمغرافي",
                "المفهوم الصحي",
                "المهارات الحياتية",
                "المدة بالدقائق",
                "المخطط",
            )
            for label, value in zip(activity_labels, activity):
                add_detail(label, value)

    elif table_name == "nachat_detail":
        try:
            activity = connection.execute(
                "SELECT n.title, n.time, h.hessa_number, h.wehda_number, "
                "d.date FROM nachat_detail nd "
                "JOIN nachat n ON n.id=nd.nachat_id "
                "JOIN hessa h ON h.id=n.hessa_id "
                "JOIN day_data d ON d.id=h.day_data_id "
                "WHERE nd.id = ?",
                (values.get("id"),),
            ).fetchone()
        except sqlite3.Error:
            activity = None
        if activity is not None:
            for label, value in zip(
                ("النشاط", "وقت النشاط", "رقم الحصة", "رقم الوحدة", "التاريخ"),
                activity,
            ):
                add_detail(label, value)

    return [f"{label}: {value}" for label, value in details.items()]


def encode_database_result_key(
    target, query, day_text, result_title, context=None
):
    payload = {
        "target": target,
        "query": query,
        "day": day_text,
        "result": result_title,
    }
    if context is not None:
        payload["context"] = context
    payload = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"database-result:{token}"


def decode_database_result_key(key):
    prefix = "database-result:"
    if not str(key).startswith(prefix):
        return None
    token = str(key)[len(prefix):]
    try:
        payload = base64.urlsafe_b64decode(
            token + "=" * (-len(token) % 4)
        )
        result = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(result, dict) or not isinstance(
        result.get("target"), str
    ):
        return None
    return result


class SmartNavigationSearchIndex:
    def __init__(
        self,
        search_actions,
        page_descriptions,
        extra_entries=(),
        database_path=None,
        database_targets=None,
        year_id=None,
    ):
        self._database_path = database_path
        self._database_targets = database_targets or {}
        self._year_id = year_id
        grouped_actions = []
        for label, action in search_actions.items():
            group = next(
                (entry for entry in grouped_actions if entry["action"] is action),
                None,
            )
            if group is None:
                group = {"action": action, "labels": []}
                grouped_actions.append(group)
            group["labels"].append(label)

        self._entries = []
        for group in grouped_actions:
            action = group["action"]
            page_title = ""
            description = ""
            for page, page_data in page_descriptions.items():
                title, page_description = page_data
                if search_actions.get(title) is action:
                    page_title = title
                    description = page_description
                    break

            title = page_title or action.text().replace("&", "").strip()
            labels = group["labels"]
            searchable_text = " ".join(
                [*labels, action.text(), page_title, description]
            )
            self._entries.append(
                {
                    "title": title,
                    "key": title,
                    "action": action,
                    "description": description,
                    "searchable_text": searchable_text,
                    "normalized_title": _normalize_search_text(title),
                    "normalized_text": _normalize_search_text(searchable_text),
                }
            )
        entries_by_key = {
            entry["key"]: entry
            for entry in self._entries
        }
        for extra_entry in extra_entries:
            title = str(extra_entry["title"])
            description = str(extra_entry.get("description", ""))
            key = extra_entry.get("key", title)
            searchable_text = " ".join(
                (title, description, str(extra_entry.get("keywords", "")))
            )
            existing_entry = entries_by_key.get(key)
            if existing_entry is not None:
                existing_entry["searchable_text"] += f" {searchable_text}"
                existing_entry["normalized_text"] = _normalize_search_text(
                    existing_entry["searchable_text"]
                )
                continue
            self._entries.append(
                {
                    "title": title,
                    "key": key,
                    "description": description,
                    "searchable_text": searchable_text,
                    "normalized_title": _normalize_search_text(title),
                    "normalized_text": _normalize_search_text(searchable_text),
                }
            )
            entries_by_key[key] = self._entries[-1]

        self._char_vectorizer = None
        self._word_vectorizer = None
        self._char_matrix = None
        self._word_matrix = None
        self._vectorizers_lock = threading.Lock()

    def _ensure_search_vectors(self):
        if self._char_vectorizer is not None:
            return
        with self._vectorizers_lock:
            if self._char_vectorizer is not None:
                return
            from sklearn.feature_extraction.text import TfidfVectorizer

            documents = [
                entry["searchable_text"] for entry in self._entries
            ]
            char_vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(1, 4),
                preprocessor=_normalize_search_text,
                lowercase=False,
                sublinear_tf=True,
            )
            word_vectorizer = TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),
                token_pattern=r"(?u)\b\w+\b",
                preprocessor=_normalize_search_text,
                lowercase=False,
                sublinear_tf=True,
            )
            char_matrix = char_vectorizer.fit_transform(documents)
            word_matrix = word_vectorizer.fit_transform(documents)
            self._char_vectorizer = char_vectorizer
            self._word_vectorizer = word_vectorizer
            self._char_matrix = char_matrix
            self._word_matrix = word_matrix

    def search(self, query, limit=10):
        query_phrase = str(query).strip()
        normalized_query = _normalize_search_text(query).strip()
        if not normalized_query:
            return []

        ranked = []
        if self._entries:
            self._ensure_search_vectors()
            char_query = self._char_vectorizer.transform([normalized_query])
            word_query = self._word_vectorizer.transform([normalized_query])
            char_scores = (
                self._char_matrix @ char_query.T
            ).toarray().ravel()
            word_scores = (
                self._word_matrix @ word_query.T
            ).toarray().ravel()

            for index, entry in enumerate(self._entries):
                score = 0.6 * char_scores[index] + 0.4 * word_scores[index]
                title = entry["normalized_title"]
                searchable_text = entry["normalized_text"]
                if (
                    _search_term_match_ratio(
                        normalized_query, searchable_text
                    )
                    <= _MIN_SEARCH_MATCH_RATIO
                ):
                    continue
                if title.startswith(normalized_query):
                    score += 1.0
                elif normalized_query in title:
                    score += 0.75
                elif normalized_query in searchable_text:
                    score += 0.3
                if score > 0.008:
                    ranked.append((score, entry))

        ranked.sort(key=lambda result: result[0], reverse=True)
        results = [
            (entry["title"], entry["description"], entry["key"], score)
            for score, entry in ranked[:max(0, limit)]
        ]
        db_results = self._search_database(
            normalized_query, limit, query_phrase
        )
        results.extend(db_results)
        results.sort(key=lambda result: result[3], reverse=True)
        return [
            (title, description, key)
            for title, description, key, _score in results[:max(0, limit)]
        ]

    def _search_database(self, query, limit, query_phrase=None):
        if not self._database_path or self._database_path == ":memory:":
            return []

        query_terms = [
            term for term in re.findall(r"\w+", query) if len(term) >= 2
        ]
        terms = query_terms[:4]
        if not terms:
            return []
        patterns = []
        for term in terms:
            term_patterns = [term]
            character_variants = {
                "ا": ("أ", "إ", "آ"),
                "ه": ("ة",),
                "ي": ("ى",),
            }
            for index, character in enumerate(term):
                term_patterns.extend(
                    term[:index] + variant + term[index + 1:]
                    for variant in character_variants.get(character, ())
                )
                if len(term) >= 5 and index < 3:
                    term_patterns.append(
                        term[:index] + term[index + 1:]
                    )
            patterns.extend(dict.fromkeys(term_patterns))

        database_uri = (
            Path(self._database_path).resolve().as_uri() + "?mode=ro"
        )
        results = []
        seen_rows = set()
        with sqlite3.connect(
            database_uri, uri=True, timeout=1.0
        ) as connection:
            tables = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
            for (table_name,) in tables:
                if (
                    table_name == "app_migration"
                    or table_name.endswith("_notification_state")
                ):
                    continue
                quoted_table = '"' + table_name.replace('"', '""') + '"'
                columns = connection.execute(
                    f"PRAGMA table_info({quoted_table})"
                ).fetchall()
                text_columns = [
                    str(column[1])
                    for column in columns
                    if "TEXT" in str(column[2] or "").upper()
                ]
                if not text_columns:
                    continue

                quoted_columns = [
                    '"' + column.replace('"', '""') + '"'
                    for column in text_columns
                ]
                where_clause = " OR ".join(
                    f'(CAST({column} AS TEXT) LIKE ? ESCAPE \'\\\')'
                    for _pattern in patterns
                    for column in quoted_columns
                )
                parameters = []
                for pattern in patterns:
                    escaped_term = pattern.replace("%", "\\%").replace("_", "\\_")
                    parameters.extend(
                        f"%{escaped_term}%" for _column in text_columns
                    )
                year_column = next(
                    (
                        str(column[1])
                        for column in columns
                        if str(column[1]) == "ann_scolaire_id"
                    ),
                    None,
                )
                if year_column is not None and self._year_id is not None:
                    where_clause = (
                        f'("{year_column}" = ? AND ({where_clause}))'
                    )
                    parameters.insert(0, self._year_id)

                rows = connection.execute(
                    f"SELECT rowid, * FROM {quoted_table} "
                    f"WHERE {where_clause} LIMIT ?",
                    (*parameters, 12),
                ).fetchall()
                column_names = [str(column[1]) for column in columns]
                for row in rows:
                    row_id = row[0]
                    row_key = (table_name, row_id)
                    if row_key in seen_rows:
                        continue
                    seen_rows.add(row_key)
                    values = {
                        column_names[index]: value
                        for index, value in enumerate(row[1:])
                        if index < len(column_names)
                    }
                    matching_text = " ".join(
                        str(values.get(column, "") or "")
                        for column in text_columns
                    )
                    normalized_text = _normalize_search_text(matching_text)
                    matched_terms = sum(
                        term in normalized_text for term in query_terms
                    )
                    match_ratio = matched_terms / len(query_terms)
                    if match_ratio <= _MIN_SEARCH_MATCH_RATIO:
                        continue
                    matched_patterns = sum(
                        pattern in normalized_text for pattern in patterns
                    )
                    if not matched_patterns:
                        continue
                    snippet = next(
                        (
                            str(values.get(column, "")).strip()
                            for column in text_columns
                            if any(
                                term in _normalize_search_text(
                                    values.get(column, "")
                                )
                                for term in terms
                            )
                        ),
                        "",
                    )
                    snippet = " ".join(snippet.split())[:180]
                    if _looks_like_programming_code(snippet):
                        continue
                    title = f"{_database_table_label(table_name)}: {snippet}"
                    key = self._database_targets.get(
                        table_name
                    )
                    if not key:
                        continue
                    day_text = _database_result_day(
                        connection, table_name, values
                    )
                    phrase = query_phrase or query
                    result_details = _database_result_details(
                        connection,
                        table_name,
                        values,
                        text_columns,
                    )
                    description = (
                        f"الصفحة: {key}\n"
                        + "\n".join(result_details)
                    )
                    key = encode_database_result_key(
                        key,
                        phrase,
                        day_text,
                        title,
                        context=_database_result_context(
                            connection, table_name, values
                        ),
                    )
                    score = (
                        0.8
                        + matched_terms / len(terms) * 0.35
                        + min(matched_patterns - matched_terms, 1) * 0.12
                    )
                    if query in normalized_text:
                        score += 1.0
                    if any(
                        pattern in normalized_text
                        for pattern in patterns[len(terms):]
                    ):
                        score += 0.15
                    results.append((title, description, key, score))
        results.sort(key=lambda result: result[3], reverse=True)
        return results[:limit * 2]


class NavigationSearchHistory:
    def __init__(self, database_path, limit=20):
        database_path = str(database_path or "")
        self._history_path = (
            None
            if not database_path or database_path == ":memory:"
            else f"{database_path}.analytics.sqlite3"
        )
        self._limit = max(1, int(limit))
        self._memory_history = []

    @staticmethod
    def _ensure_table(connection):
        connection.execute(
            "CREATE TABLE IF NOT EXISTS navigation_search_history ("
            "phrase TEXT PRIMARY KEY, searched_at TEXT NOT NULL)"
        )

    def record(self, phrase, searched_at=None):
        phrase = str(phrase or "").strip()
        if not phrase:
            return
        searched_at = searched_at or datetime.now(
            timezone.utc
        ).isoformat(timespec="microseconds")
        if self._history_path is None:
            self._record_in_memory(phrase, searched_at)
            return
        try:
            with sqlite3.connect(
                self._history_path, timeout=2
            ) as connection:
                self._ensure_table(connection)
                connection.execute(
                    "INSERT INTO navigation_search_history "
                    "(phrase, searched_at) VALUES (?, ?) "
                    "ON CONFLICT(phrase) DO UPDATE SET "
                    "searched_at=excluded.searched_at",
                    (phrase, searched_at),
                )
                connection.execute(
                    "DELETE FROM navigation_search_history WHERE phrase NOT IN ("
                    "SELECT phrase FROM navigation_search_history "
                    "ORDER BY searched_at DESC LIMIT ?)",
                    (self._limit,),
                )
        except sqlite3.Error:
            self._record_in_memory(phrase, searched_at)

    def _record_in_memory(self, phrase, searched_at):
        self._memory_history = [
            entry for entry in self._memory_history
            if entry[0] != phrase
        ]
        self._memory_history.append((phrase, searched_at))
        self._memory_history.sort(key=lambda entry: entry[1], reverse=True)
        self._memory_history = self._memory_history[:self._limit]

    def recent(self):
        if self._history_path is None:
            return list(self._memory_history)
        try:
            with sqlite3.connect(
                self._history_path, timeout=2
            ) as connection:
                self._ensure_table(connection)
                entries = connection.execute(
                    "SELECT phrase, searched_at "
                    "FROM navigation_search_history "
                    "ORDER BY searched_at DESC LIMIT ?",
                    (self._limit,),
                ).fetchall()
            return [(str(phrase), str(searched_at)) for phrase, searched_at in entries]
        except sqlite3.Error:
            return list(self._memory_history)


class NavigationSearchPopup(QFrame):
    resultActivated = Signal(str)
    historySelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("navigationSearchPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(360)
        self.setMaximumWidth(900)
        self.setMaximumHeight(700)
        self._showing_history = False
        self._has_been_shown = False
        self.setStyleSheet(
            "QFrame#navigationSearchPopup {"
            "background: #FFFFFF; border: 1px solid #CBD5E1;"
            "border-radius: 10px;}"
            "QLabel#navigationSearchPopupTitle {"
            "color: #334155; font-size: 10pt; font-weight: 700;"
            "border: none; padding: 8px 10px 6px;}"
            "QListWidget {border: none; background: transparent;"
            "outline: none; padding: 3px 4px;}"
            "QListWidget::item {border: none; padding: 2px 1px;}"
            "QListWidget::item:selected {background: transparent;}"
            "QScrollBar:vertical {width: 10px; margin: 2px;"
            "background: #F1F5F9; border: none; border-radius: 5px;}"
            "QScrollBar::handle:vertical {min-height: 28px;"
            "background: #94A3B8; border-radius: 5px;}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "height: 0;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        self.title_label = QLabel("نتائج البحث", self)
        self.title_label.setObjectName("navigationSearchPopupTitle")
        layout.addWidget(self.title_label)
        self.results = QListWidget(self)
        self.results.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results.setWordWrap(True)
        self.results.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.results.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.results.setSpacing(3)
        self.results.setMaximumHeight(650)
        layout.addWidget(self.results)
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        footer.addWidget(
            QLabel("اسحب المقبض لتغيير الأبعاد", self)
        )
        footer.addStretch(1)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setObjectName("navigationSearchPopupSizeGrip")
        self.size_grip.setFixedSize(18, 18)
        self.size_grip.setToolTip("اسحب لتغيير أبعاد نافذة النتائج")
        self.size_grip.setAccessibleName("تغيير أبعاد نافذة النتائج")
        footer.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(footer)
        self.results.itemClicked.connect(self._activate_selected_item)
        self.hide()

    def set_history(self, entries):
        formatted_entries = []
        for phrase, searched_at in entries:
            try:
                searched_date = datetime.fromisoformat(str(searched_at))
                if searched_date.tzinfo is not None:
                    searched_date = searched_date.astimezone()
                formatted_date = searched_date.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                formatted_date = str(searched_at)
            formatted_entries.append(
                (phrase, f"تاريخ البحث: {formatted_date}", phrase)
            )
        self.set_results(formatted_entries, history=True)

    def set_results(self, results, history=False):
        self._showing_history = bool(history)
        self.setMinimumSize(360, 0)
        self.results.clear()
        for result in results:
            title, description = result[:2]
            result_key = result[2] if len(result) > 2 else title
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, result_key)
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
            item.setData(Qt.ItemDataRole.UserRole + 2, description)
            item.setToolTip(description or title)
            item.setSizeHint(QSize(0, 54))
            self.results.addItem(item)
            result_button = QPushButton(self.results)
            result_button.setObjectName("navigationSearchResult")
            result_button.setCursor(Qt.CursorShape.PointingHandCursor)
            result_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            result_button.setAccessibleName(f"فتح نتيجة: {title}")
            result_button.setToolTip(description or title)
            result_button.setStyleSheet(
                "QPushButton#navigationSearchResult {"
                "background: #F8FAFC; border: 1px solid #D8E0E8;"
                "border-radius: 6px; text-align: right; padding: 7px 10px;}"
                "QPushButton#navigationSearchResult:hover {"
                "background: #EFF6FF; border-color: #93C5FD;}"
                "QPushButton#navigationSearchResult:pressed {"
                "background: #DBEAFE; border-color: #60A5FA;}"
            )
            result_layout = QVBoxLayout(result_button)
            result_layout.setContentsMargins(2, 1, 2, 1)
            result_layout.setSpacing(3)
            title_label = QLabel(
                title if history else f"{title}  ←", result_button
            )
            title_label.setObjectName("navigationSearchResultTitle")
            title_label.setWordWrap(True)
            title_label.setStyleSheet(
                "color: #1D4ED8; font-weight: 700;"
                "text-decoration: underline; background: transparent;"
            )
            title_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            result_layout.addWidget(title_label)
            if description:
                description_label = QLabel(description, result_button)
                description_label.setObjectName(
                    "navigationSearchResultDescription"
                )
                description_label.setWordWrap(True)
                description_label.setTextFormat(Qt.TextFormat.PlainText)
                description_label.setStyleSheet(
                    "color: #475569; font-size: 9pt; line-height: 1.25;"
                    "background: transparent; border: none;"
                )
                description_label.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
                result_layout.addWidget(description_label)
            result_button.clicked.connect(
                lambda _checked=False, key=result_key:
                self._activate_title(key)
            )
            self.results.setItemWidget(item, result_button)

        if not results:
            item = QListWidgetItem(
                "لا توجد عبارات سابقة" if history else "لا توجد صفحات مطابقة"
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setSizeHint(QSize(440, 54))
            self.results.addItem(item)
        else:
            self.results.setCurrentRow(0)

        self.results.setMinimumHeight(54)
        if history:
            title = "سجل البحث"
            if results:
                title += f" ({len(results)})"
        else:
            title = (
                f"نتائج البحث ({len(results)})"
                if results
                else "نتائج البحث"
            )
        self.title_label.setText(title)

    def show_below(self, search_field):
        screen = search_field.screen().availableGeometry()
        maximum_width = min(900, max(1, screen.width() - 12))
        maximum_height = min(700, max(1, screen.height() - 12))
        minimum_width = min(360, maximum_width)
        minimum_height = min(120, maximum_height)
        self.setMinimumSize(minimum_width, minimum_height)
        self.setMaximumSize(maximum_width, maximum_height)
        if self._has_been_shown:
            width = min(max(self.width(), minimum_width), maximum_width)
        else:
            width = min(
                max(search_field.width(), minimum_width), maximum_width
            )
        self.resize(width, max(minimum_height, self.height()))
        content_height = self._update_result_row_heights()
        if self._has_been_shown:
            height = min(
                max(self.height(), minimum_height), maximum_height
            )
        else:
            chrome_height = (
                self.title_label.sizeHint().height()
                + self.size_grip.height()
                + 28
            )
            height = min(
                max(minimum_height, content_height + chrome_height),
                maximum_height,
            )
        self.resize(width, height)
        self._update_result_row_heights()
        anchor = search_field.mapToGlobal(
            QPoint(search_field.width(), search_field.height())
        )
        x = min(anchor.x() - width, screen.right() - width + 1)
        x = max(x, screen.left())
        popup_height = self.height()
        below_y = anchor.y()
        above_y = search_field.mapToGlobal(QPoint(0, 0)).y() - popup_height
        if below_y + popup_height <= screen.bottom() + 1:
            y = below_y
        elif above_y >= screen.top():
            y = above_y
        else:
            y = max(
                screen.top(),
                min(below_y, screen.bottom() - popup_height + 1),
            )
        self.move(x, y)
        self._has_been_shown = True
        if not self.isVisible():
            self.show()

    def _update_result_row_heights(self):
        content_width = max(120, self.results.viewport().width() - 28)
        total_height = 0
        for row in range(self.results.count()):
            item = self.results.item(row)
            title = str(item.data(Qt.ItemDataRole.UserRole + 1) or item.text())
            description = str(
                item.data(Qt.ItemDataRole.UserRole + 2) or ""
            )
            result_button = self.results.itemWidget(item)
            if result_button is None:
                row_height = 54
            else:
                text_width = max(80, content_width - 28)
                title_label = result_button.findChild(
                    QLabel, "navigationSearchResultTitle"
                )
                if title_label is not None:
                    title_metrics = QFontMetrics(title_label.font())
                    title_height = title_metrics.boundingRect(
                        QRect(0, 0, text_width, 1000),
                        Qt.TextFlag.TextWordWrap,
                        title_label.text(),
                    ).height()
                else:
                    title_height = QFontMetrics(
                        result_button.font()
                    ).height()
                description_height = 0
                description_label = result_button.findChild(
                    QLabel, "navigationSearchResultDescription"
                )
                if description_label is not None and description:
                    description_metrics = QFontMetrics(
                        description_label.font()
                    )
                    description_height = description_metrics.boundingRect(
                        QRect(0, 0, text_width, 1000),
                        Qt.TextFlag.TextWordWrap,
                        description,
                    ).height() + 3
                row_height = max(
                    54, title_height + description_height + 20
                )
            item.setSizeHint(QSize(content_width, row_height))
            total_height += row_height

        return max(54, total_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "results"):
            self._update_result_row_heights()

    def select_next(self):
        if self.results.count():
            self.results.setCurrentRow(
                min(self.results.currentRow() + 1, self.results.count() - 1)
            )

    def select_previous(self):
        if self.results.count():
            self.results.setCurrentRow(max(self.results.currentRow() - 1, 0))

    def activate_current(self):
        item = self.results.currentItem()
        if item is not None and item.flags() != Qt.ItemFlag.NoItemFlags:
            self._activate_item(item)

    def _activate_item(self, item):
        title = item.data(Qt.ItemDataRole.UserRole)
        if title:
            self._activate_title(title)

    def _activate_selected_item(self, item):
        self._activate_item(item)

    def _activate_title(self, title):
        self.hide()
        if self._showing_history:
            self.historySelected.emit(title)
        else:
            self.resultActivated.emit(title)
