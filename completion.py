# -*- coding: utf-8 -*-
"""Extracted module completion."""
import atexit
import logging
import re
import threading
from collections import OrderedDict
from contextlib import closing

from PySide6.QtCore import (
    Qt, QObject, QRunnable, QTimer, Signal, QThreadPool, QThread,
)
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit
from database_connection import connect_database


logger = logging.getLogger(__name__)


class CompletionWorkerSignals(QObject):
    finished = Signal(object)


class CompletionWorker(QRunnable):
    _values_cache = OrderedDict()
    _values_cache_limit = 64
    _values_cache_lock = threading.Lock()
    _database_connections = {}
    _database_connection_locks = {}
    _database_connections_lock = threading.Lock()
    _smart_models = OrderedDict()
    _smart_models_limit = 8
    _smart_models_lock = threading.Lock()

    def __init__(self, request_id, db_path, key_name, activity_title, text,
                 position, allow_completion,
                 contextual_words=None, completion_source=None,
                 completion_scope_id=None):
        super().__init__()
        self.signals = CompletionWorkerSignals()
        self.request_id = request_id
        self.db_path = db_path
        self.key_name = key_name
        self.activity_title = activity_title
        self.text = text
        self.position = position
        self.allow_completion = allow_completion
        self.contextual_words = contextual_words
        self.completion_source = completion_source
        self.completion_scope_id = completion_scope_id

    def run(self):
        values = None
        error = None
        try:
            values = self._get_values()
            suffix = self._contextual_completion_suffix()
            if suffix is None:
                suffix = (
                    self._completion_suffix(values)
                    if self.allow_completion else ""
                )
            suggested_text = (
                self.text[:self.position] + suffix + self.text[self.position:]
            )
            suggestions, suggestion_error = self._smart_suggestions(
                suggested_text.strip(), values
            )
            error = suggestion_error
        except Exception as exc:
            suffix = ""
            suggestions = []
            error = f"Autocomplete failed: {exc}"
        self.signals.finished.emit((
            self.request_id, self.text, self.position, self.key_name,
            self.activity_title, suffix, suggestions, values, error,
            self.completion_source, self.completion_scope_id,
        ))

    def _contextual_completion_suffix(self):
        if self.contextual_words is None:
            return None
        if self.position != len(self.text):
            return ""

        before_cursor = self.text[:self.position]
        tokens = re.findall(r"\S+", before_cursor)
        if not tokens:
            return ""

        words = list(self.contextual_words)
        if len(tokens) > len(words) + 1:
            return None
        if len(tokens) == len(words) + 1:
            return ""

        trailing_space = bool(before_cursor and before_cursor[-1].isspace())
        if len(tokens) == 1:
            return (" " if not trailing_space else "") + " ".join(words)
        if trailing_space:
            next_word_index = len(tokens) - 1
            return " ".join(words[next_word_index:])

        word_index = len(tokens) - 2
        typed_word = tokens[-1]
        expected_word = words[word_index]
        if expected_word.startswith(typed_word):
            return expected_word[len(typed_word):] + (
                " " + " ".join(words[word_index + 1:])
                if word_index + 1 < len(words) else ""
            )
        return ""

    def _cache_key(self):
        return (
            self.db_path,
            self.completion_source,
            self.completion_scope_id,
            self.key_name,
            self.activity_title,
        )

    @classmethod
    def _database_connection(cls, db_path):
        path = str(db_path)
        with cls._database_connections_lock:
            connection = cls._database_connections.get(path)
            if connection is None:
                connection = connect_database(
                    path, timeout=10, cached_statements=256,
                    check_same_thread=False,
                )
                cls._database_connections[path] = connection
                cls._database_connection_locks[path] = threading.Lock()
            return connection, cls._database_connection_locks[path]

    @classmethod
    def close_cached_connections(cls):
        with cls._database_connections_lock:
            connections = [
                (path, connection, cls._database_connection_locks[path])
                for path, connection in cls._database_connections.items()
            ]
            cls._database_connections.clear()
            cls._database_connection_locks.clear()
        for _path, connection, connection_lock in connections:
            with connection_lock:
                connection.close()

    @classmethod
    def _get_cached_values(
        cls, db_path, key_name, activity_title, completion_source=None,
        completion_scope_id=None,
    ):
        cache_key = (
            str(db_path),
            completion_source,
            completion_scope_id,
            key_name,
            activity_title,
        )
        con, connection_lock = cls._database_connection(db_path)
        with connection_lock:
            data_version = con.execute("PRAGMA data_version").fetchone()[0]
            with cls._values_cache_lock:
                cached = cls._values_cache.get(cache_key)
                if cached is not None and cached[0] == data_version:
                    cls._values_cache.move_to_end(cache_key)
                    return cached[1]

            if completion_source == "monthly_club":
                rows = con.execute(
                    """SELECT DISTINCT prop.value_text
                       FROM cultural_club_monthly_property prop
                       JOIN cultural_club_monthly_session s
                         ON s.id=prop.session_id
                       JOIN cultural_club_monthly_plan p ON p.id=s.plan_id
                       WHERE p.club_id=? AND prop.key_name=?
                         AND trim(COALESCE(prop.value_text, ''))<>''
                       ORDER BY p.month DESC, s.session_date DESC,
                         prop.position""",
                    (completion_scope_id, key_name),
                ).fetchall()
            else:
                rows = con.execute(
                    """SELECT DISTINCT d.value_text
                       FROM nachat_detail d
                       JOIN nachat n ON n.id = d.nachat_id
                       WHERE d.key_name = ? AND n.title = ?
                         AND trim(COALESCE(d.value_text, '')) <> ''""",
                    (key_name, activity_title),
                ).fetchall()
                if not rows:
                    rows = con.execute(
                        """SELECT DISTINCT value_text
                           FROM nachat_detail
                           WHERE key_name = ?
                             AND trim(COALESCE(value_text, '')) <> ''""",
                        (key_name,),
                    ).fetchall()

            values = tuple(dict.fromkeys(
                str(row[0]).strip()
                for row in rows
                if row[0] is not None and str(row[0]).strip()
            ))
            with cls._values_cache_lock:
                cls._values_cache[cache_key] = (data_version, values)
                cls._values_cache.move_to_end(cache_key)
                while len(cls._values_cache) > cls._values_cache_limit:
                    cls._values_cache.popitem(last=False)
            return values

    def _get_values(self):
        return self._get_cached_values(
            self.db_path,
            self.key_name,
            self.activity_title,
            self.completion_source,
            self.completion_scope_id,
        )

    def _completion_suffix(self, values):
        before_cursor = self.text[:self.position]
        if not before_cursor or not values:
            return ""

        from collections import Counter

        if before_cursor[-1].isspace():
            words = before_cursor.strip().split()
            if not words:
                return ""
            last_word = words[-1]
            next_word_counts = Counter()
            for value in values:
                words = [w.strip(".,،؛:!?؟()[]{}\"'«»") for w in value.split()]
                for index in range(len(words) - 1):
                    if words[index] == last_word and words[index + 1]:
                        next_word_counts[words[index + 1]] += 1
            candidates = next_word_counts.most_common(1)
            return candidates[0][0] + " " if candidates else ""

        word_match = re.search(r"[^\s]+$", before_cursor)
        if not word_match:
            return ""
        typed_word = word_match.group(0)
        if len(typed_word) < 2:
            return ""

        word_counts = Counter()
        for value in values:
            for word in value.split():
                clean_word = word.strip(".,،؛:!?؟()[]{}\"'«»")
                if clean_word:
                    word_counts[clean_word] += 1
        matches = [
            word for word in word_counts
            if word.startswith(typed_word) and word != typed_word
        ]
        if not matches:
            return ""
        matches.sort(key=lambda word: (-word_counts[word], len(word), word))
        return matches[0][len(typed_word):]

    @classmethod
    def _prepare_smart_model(cls, cache_key, values):
        with cls._smart_models_lock:
            cached = cls._smart_models.get(cache_key)
            if cached is None or cached[0] is not values:
                try:
                    from sklearn.feature_extraction.text import TfidfVectorizer
                    vectorizer = TfidfVectorizer(
                        analyzer="char_wb", ngram_range=(2, 5),
                        lowercase=False, sublinear_tf=True
                    )
                    matrix = vectorizer.fit_transform(values)
                    cached = (values, vectorizer, matrix)
                    cls._smart_models[cache_key] = cached
                    while len(cls._smart_models) > cls._smart_models_limit:
                        cls._smart_models.popitem(last=False)
                except (ImportError, ValueError):
                    return None
            else:
                cls._smart_models.move_to_end(cache_key)
        return cached

    def _smart_suggestions(self, query, values, limit=6):
        if len(query) < 2 or not values:
            return [], None

        cached = self._prepare_smart_model(self._cache_key(), values)
        if cached is None:
            return self._fallback_suggestions(query, values, limit), None

        try:
            from sklearn.metrics.pairwise import cosine_similarity
            vectorizer, matrix = cached[1], cached[2]
            scores = cosine_similarity(vectorizer.transform([query]), matrix).ravel()
            ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
            return ([(values[i], float(score)) for i, score in ranked
                     if score > 0 and values[i] != query][:limit], None)
        except Exception as exc:
            return self._fallback_suggestions(query, values, limit), (
                f"Smart autocomplete ranking failed: {exc}"
            )

    @staticmethod
    def _fallback_suggestions(query, values, limit):
        from difflib import SequenceMatcher
        ranked = sorted(
            ((value, SequenceMatcher(None, query, value).ratio()) for value in values),
            key=lambda item: item[1], reverse=True
        )
        return [(value, score) for value, score in ranked
                if score > 0.12 and value != query][:limit]


class AutoCompletionTextEdit(QTextEdit):
    """إكمال واقتراح ذكي دون تنفيذ عمليات قاعدة البيانات على خيط الواجهة."""
    suggestions_ready = Signal(object)

    def __init__(
        self, db, key_combo, activity_title, parent=None,
        completion_source=None, completion_scope_id=None,
        allow_inline_completion=True,
    ):
        super().__init__(parent)
        self.db = db
        self.key_combo = key_combo
        self.activity_title = activity_title
        self.completion_source = completion_source
        self.completion_scope_id = completion_scope_id
        self.allow_inline_completion = allow_inline_completion
        self.is_completing = False
        self.skip_next_completion = False
        self.completion_history_available = None
        self.completion_failed = False
        self._request_id = 0
        self._completion_timer = QTimer(self)
        self._completion_timer.setSingleShot(True)
        self._completion_timer.setInterval(120)
        self._completion_timer.timeout.connect(self._start_completion)
        self._worker_running = False
        self._pending_request = False
        self._contextual_words = None
        self.setAcceptRichText(False)
        self.textChanged.connect(self.on_text_changed)

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self.skip_next_completion = True
            if cursor.hasSelection():
                cursor.clearSelection()
                self.setTextCursor(cursor)
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key_Tab, Qt.Key_Right) and cursor.hasSelection():
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)
            event.accept()
            return
        if event.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End):
            self.skip_next_completion = True
            super().keyPressEvent(event)
            return
        self.skip_next_completion = False
        super().keyPressEvent(event)

    def on_text_changed(self):
        if self.is_completing or self.skip_next_completion:
            return
        self.schedule_completion()

    def schedule_completion(self, allow_completion=True):
        self._request_id += 1
        self._allow_completion = (
            allow_completion and self.allow_inline_completion
        )
        self._completion_timer.start()

    def refresh_for_key_change(self, *_args):
        self.schedule_completion(allow_completion=False)

    def set_contextual_completion_words(self, words):
        contextual_words = tuple(words) if words is not None else None
        if contextual_words == self._contextual_words:
            return
        self._contextual_words = contextual_words
        self.schedule_completion()

    def set_completion_scope(self, source, scope_id=None):
        if (
            source == self.completion_source
            and scope_id == self.completion_scope_id
        ):
            return
        self.completion_source = source
        self.completion_scope_id = scope_id
        self.schedule_completion()

    def _start_completion(self):
        if self._worker_running:
            self._pending_request = True
            return
        text = self.toPlainText()
        position = self.textCursor().position()
        key_name = self.key_combo.currentText().strip()
        self._worker_running = True
        worker = CompletionWorker(
            self._request_id, self.db.path, key_name, self.activity_title,
            text, position, self._allow_completion, self._contextual_words,
            self.completion_source, self.completion_scope_id,
        )
        worker.signals.finished.connect(self._apply_completion_result)
        QThreadPool.globalInstance().start(worker)

    def _apply_completion_result(self, result):
        self._worker_running = False
        (request_id, text, position, key_name, activity_title, suffix,
         suggestions, values, error, completion_source,
         completion_scope_id) = result
        if error:
            logger.error("%s", error)
        if (
            request_id != self._request_id
            or text != self.toPlainText()
            or position != self.textCursor().position()
            or key_name != self.key_combo.currentText().strip()
            or activity_title != self.activity_title
            or completion_source != self.completion_source
            or completion_scope_id != self.completion_scope_id
        ):
            self._start_pending_request()
            return
        self.completion_history_available = (
            bool(values) if values is not None else None
        )
        self.completion_failed = values is None
        if suffix:
            self.is_completing = True
            try:
                cursor = self.textCursor()
                cursor.insertText(suffix)
                cursor.setPosition(position)
                cursor.setPosition(position + len(suffix), QTextCursor.KeepAnchor)
                self.setTextCursor(cursor)
            finally:
                self.is_completing = False
        self.suggestions_ready.emit(suggestions)

        self._start_pending_request()

    def _start_pending_request(self):
        if self._pending_request:
            self._pending_request = False
            self._completion_timer.stop()
            self._start_completion()


class CompletionWarmupWorker(QRunnable):
    def __init__(self, db_path, year_id=None):
        super().__init__()
        self.db_path = str(db_path)
        self.year_id = year_id

    def run(self):
        try:
            with closing(connect_database(self.db_path)) as con:
                con.execute(
                    """CREATE INDEX IF NOT EXISTS
                       idx_nachat_detail_key_value
                       ON nachat_detail(key_name, value_text)"""
                )
                con.execute("PRAGMA optimize")

                year_filter = ""
                params = []
                if self.year_id is not None:
                    year_filter = "AND dd2.ann_scolaire_id = ?"
                    params.append(self.year_id)
                pairs = con.execute(f"""
                    SELECT n.title, d.key_name, MAX(d.id) AS latest_id
                    FROM nachat_detail d
                    JOIN nachat n ON n.id=d.nachat_id
                    JOIN hessa h ON h.id=n.hessa_id
                    JOIN day_data dd ON dd.id=h.day_data_id
                    WHERE dd.id=(
                        SELECT dd2.id
                        FROM day_data dd2
                        JOIN hessa h2 ON h2.day_data_id=dd2.id
                        WHERE 1=1 {year_filter}
                        ORDER BY dd2.date DESC, dd2.id DESC
                        LIMIT 1
                    )
                    GROUP BY n.title, d.key_name
                    ORDER BY latest_id DESC
                    LIMIT 32
                """, params).fetchall()

            for activity_title, key_name, _latest_id in pairs:
                values = CompletionWorker._get_cached_values(
                    self.db_path, key_name, activity_title
                )
                if values:
                    CompletionWorker._prepare_smart_model(
                        (
                            self.db_path, None, None, key_name,
                            activity_title,
                        ),
                        values,
                    )
        except Exception:
            logger.exception("Autocomplete startup warm-up failed")


def warm_completion_cache(db_path, year_id=None):
    if not db_path or str(db_path) == ":memory:":
        return
    worker = CompletionWarmupWorker(db_path, year_id)
    QThreadPool.globalInstance().start(
        worker, int(QThread.LowPriority.value)
    )


atexit.register(CompletionWorker.close_cached_connections)
