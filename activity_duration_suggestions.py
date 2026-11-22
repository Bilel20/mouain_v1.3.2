"""Low-priority activity-duration suggestions backed by a revisioned cache."""
import logging
import math
import statistics
import threading
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal

from database import Database
from database_connection import connect_database


logger = logging.getLogger(__name__)
_CACHE_REFRESH_LOCK = threading.Lock()
_HISTORY_LIMIT = 5000


class _SuggestionSignals(QObject):
    ready = Signal(int, str)
    failed = Signal(str)


class ActivityDurationSuggestionWorker(QRunnable):
    def __init__(
        self, database_path, learning_mode, activity_name, class_id,
        plan_id, current_mode_durations, remaining_minutes,
        fallback_duration,
    ):
        super().__init__()
        self.database_path = str(database_path)
        self.learning_mode = str(learning_mode or "").strip()
        self.activity_name = str(activity_name or "").strip()
        self.class_id = class_id
        self.plan_id = plan_id
        self.current_mode_durations = tuple(current_mode_durations)
        self.remaining_minutes = remaining_minutes
        self.fallback_duration = int(fallback_duration)
        self.signals = _SuggestionSignals()

    def run(self):
        try:
            history = _historical_duration_hint(
                self.database_path,
                self.learning_mode,
                self.activity_name,
                self.class_id,
                self.plan_id,
            )
            duration, explanation = _suggest_duration(
                history,
                self.current_mode_durations,
                self.remaining_minutes,
                self.fallback_duration,
            )
            self.signals.ready.emit(duration, explanation)
        except Exception as error:
            logger.exception("Activity duration suggestion failed")
            self.signals.failed.emit(str(error) or "تعذر تقدير مدة النشاط.")


class ActivityDurationCacheWarmupWorker(QRunnable):
    def __init__(self, database_path):
        super().__init__()
        self.database_path = str(database_path)

    def run(self):
        try:
            _refresh_duration_cache_if_needed(self.database_path)
        except Exception:
            logger.exception("Activity duration cache warm-up failed")


def _cache_path(database_path):
    return f"{database_path}.analytics.sqlite3"


def _ensure_cache_schema(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS activity_duration_hint (
            learning_mode TEXT NOT NULL,
            activity_key TEXT NOT NULL,
            class_key TEXT NOT NULL,
            plan_id INTEGER NOT NULL,
            weighted_minutes REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            PRIMARY KEY(
                learning_mode, activity_key, class_key, plan_id
            )
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS activity_duration_hint_meta (
            id INTEGER PRIMARY KEY CHECK (id=1),
            source_revision INTEGER NOT NULL
        )
    """)


def _refresh_duration_cache_if_needed(database_path):
    cache_path = _cache_path(database_path)
    with _CACHE_REFRESH_LOCK:
        with closing(connect_database(database_path)) as source:
            source.execute("BEGIN")
            revision_row = source.execute(
                "SELECT revision FROM teaching_plan_data_revision WHERE id=1"
            ).fetchone()
            revision = int(revision_row[0]) if revision_row else 0
            with closing(connect_database(cache_path)) as cache:
                _ensure_cache_schema(cache)
                cached_revision = cache.execute(
                    "SELECT source_revision FROM activity_duration_hint_meta "
                    "WHERE id=1"
                ).fetchone()
                if (
                    cached_revision is not None
                    and int(cached_revision[0]) == revision
                ):
                    source.rollback()
                    return

                grouped = source.execute(f"""
                    WITH recent AS (
                        SELECT plan_id, learning_mode, activity_name,
                            plan_item_id, duration_minutes
                        FROM teaching_plan_activity
                        WHERE duration_minutes BETWEEN 1 AND 300
                        ORDER BY id DESC
                        LIMIT {_HISTORY_LIMIT}
                    )
                    SELECT recent.learning_mode,
                        COALESCE(
                            NULLIF(trim(recent.activity_name), ''),
                            item.activity_name,
                            ''
                        ) AS activity_name,
                        plan.classe_id,
                        recent.plan_id,
                        AVG(recent.duration_minutes),
                        COUNT(*)
                    FROM recent
                    JOIN teaching_plan AS plan ON plan.id=recent.plan_id
                    LEFT JOIN teaching_plan_item AS item
                        ON item.id=recent.plan_item_id
                    WHERE trim(COALESCE(
                        NULLIF(recent.activity_name, ''),
                        item.activity_name,
                        ''
                    )) <> ''
                    GROUP BY recent.learning_mode,
                        lower(trim(COALESCE(
                            NULLIF(recent.activity_name, ''),
                            item.activity_name,
                            ''
                        ))),
                        plan.classe_id,
                        recent.plan_id
                """).fetchall()

                class_aggregates = defaultdict(lambda: [0.0, 0])
                for mode, name, class_id, plan_id, average, count in grouped:
                    mode = str(mode or "").strip()
                    activity_key = Database._normalized_plan_activity(name)
                    if not mode or not activity_key:
                        continue
                    aggregate_key = (
                        mode,
                        activity_key,
                        str(class_id or ""),
                        int(plan_id),
                    )
                    class_aggregates[aggregate_key][0] += (
                        float(average) * int(count)
                    )
                    class_aggregates[aggregate_key][1] += int(count)

                cache_rows = []
                for (mode, activity_key, class_key, plan_id), (
                    weighted_total, count
                ) in class_aggregates.items():
                    if class_key:
                        cache_rows.append((
                            mode, activity_key, class_key, plan_id,
                            weighted_total, count,
                        ))

                cache.execute("BEGIN IMMEDIATE")
                cache.execute("DELETE FROM activity_duration_hint")
                cache.executemany("""
                    INSERT INTO activity_duration_hint(
                        learning_mode, activity_key, class_key,
                        plan_id, weighted_minutes, sample_count
                    ) VALUES(?, ?, ?, ?, ?, ?)
                """, cache_rows)
                cache.execute("""
                    INSERT INTO activity_duration_hint_meta(
                        id, source_revision
                    ) VALUES(1, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_revision=excluded.source_revision
                """, (revision,))
                cache.commit()
            source.rollback()


def _historical_duration_hint(
    database_path, learning_mode, activity_name, class_id, exclude_plan_id
):
    _refresh_duration_cache_if_needed(database_path)
    activity_key = Database._normalized_plan_activity(activity_name)
    class_key = str(class_id) if class_id is not None else ""
    cache_path = _cache_path(database_path)
    with closing(connect_database(cache_path)) as cache:
        scopes = []
        if class_key:
            scopes.append((activity_key, class_key))
        if activity_key:
            scopes.append((activity_key, None))
        scopes.append(("", None))
        for key_activity, key_class in scopes:
            activity_clause = (
                " AND activity_key=?" if key_activity else ""
            )
            class_clause = (
                " AND class_key=?" if key_class is not None else ""
            )
            parameters = [learning_mode]
            if key_activity:
                parameters.append(key_activity)
            if key_class is not None:
                parameters.append(key_class)
            parameters.append(int(exclude_plan_id or 0))
            row = cache.execute("""
                SELECT SUM(weighted_minutes) / SUM(sample_count),
                    SUM(sample_count)
                FROM activity_duration_hint
                WHERE learning_mode=? {activity_clause}
                    {class_clause} AND plan_id<>?
            """.format(
                activity_clause=activity_clause,
                class_clause=class_clause,
            ), parameters).fetchone()
            if row is not None and row[0] is not None and row[1]:
                return float(row[0]), int(row[1])
    return None


def _suggest_duration(
    history, current_mode_durations, remaining_minutes, fallback_duration,
):
    current_durations = [
        int(value)
        for value in current_mode_durations
        if isinstance(value, (int, float))
        and math.isfinite(value)
        and 1 <= value <= 300
    ]
    current_average = (
        float(statistics.median(current_durations))
        if current_durations else None
    )
    if history is not None and current_average is not None:
        history_average, history_count = history
        history_weight = min(max(history_count, 1), 8)
        current_weight = min(len(current_durations), 4) * 2
        estimate = (
            history_average * history_weight
            + current_average * current_weight
        ) / (history_weight + current_weight)
        explanation = "تخمين وفق نمط التوزيع الحالي والمخططات السابقة."
    elif history is not None:
        estimate = history[0]
        explanation = "تخمين وفق مدد النشاط في المخططات السابقة."
    elif current_average is not None:
        estimate = current_average
        explanation = "تخمين وفق نمط إسناد الأنشطة الحالي."
    else:
        estimate = fallback_duration
        explanation = "لا تتوفر بيانات كافية؛ استُخدمت مدة الحصة مبدئيًا."

    duration = max(1, min(300, int(math.floor(estimate + 0.5))))
    if remaining_minutes is not None:
        available = max(1, min(300, int(remaining_minutes)))
        if duration > available:
            duration = available
            explanation += " رُوعي الوقت المتبقي في الحصة."
    return duration, explanation


def request_activity_duration_suggestion(
    database_path, learning_mode, activity_name, class_id,
    plan_id, current_mode_durations, remaining_minutes,
    fallback_duration, on_result, on_error,
):
    if (
        not isinstance(database_path, (str, Path))
        or not str(database_path)
        or str(database_path) == ":memory:"
    ):
        return None
    worker = ActivityDurationSuggestionWorker(
        database_path,
        learning_mode,
        activity_name,
        class_id,
        plan_id,
        current_mode_durations,
        remaining_minutes,
        fallback_duration,
    )
    worker.signals.ready.connect(on_result)
    worker.signals.failed.connect(on_error)
    QThreadPool.globalInstance().start(
        worker, int(QThread.LowPriority.value)
    )
    return worker


def warm_activity_duration_cache(database_path):
    if (
        not isinstance(database_path, (str, Path))
        or not str(database_path)
        or str(database_path) == ":memory:"
    ):
        return None
    worker = ActivityDurationCacheWarmupWorker(database_path)
    QThreadPool.globalInstance().start(
        worker, int(QThread.LowPriority.value)
    )
    return worker
