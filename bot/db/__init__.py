# Database layer — SQLite via aiosqlite
from .database import (
    init_db,
    # warnings
    add_warning, get_warnings, reset_warnings,
    # messages
    log_message, search_messages,
    # spam
    track_spam,
    # knowledge base
    save_knowledge, get_knowledge, increment_use,
    # feedback
    save_feedback, check_feedback_rate,
    vote_correction, get_feedback_by_id,
    count_user_corrections, get_pending_feedback,
    # punishments
    add_punishment, get_punishment_count,
    # user levels
    get_user_level, set_user_level, get_chat_levels,
    # daily counters
    increment_daily_action, get_daily_action,
    increment_message_count, get_message_count,
    increment_query_count, get_query_count,
    # reports
    save_report, get_user_report_today,
    get_pending_reports, update_report_status, get_report_count,
    # stats
    get_stats, get_daily_stats,
    get_violation_stats, get_user_daily_stats,
)

__all__ = [
    "init_db",
    "add_warning", "get_warnings", "reset_warnings",
    "log_message", "search_messages",
    "track_spam",
    "save_knowledge", "get_knowledge", "increment_use",
    "save_feedback", "check_feedback_rate",
    "vote_correction", "get_feedback_by_id",
    "count_user_corrections", "get_pending_feedback",
    "add_punishment", "get_punishment_count",
    "get_user_level", "set_user_level", "get_chat_levels",
    "increment_daily_action", "get_daily_action",
    "increment_message_count", "get_message_count",
    "increment_query_count", "get_query_count",
    "save_report", "get_user_report_today",
    "get_pending_reports", "update_report_status", "get_report_count",
    "get_stats", "get_daily_stats",
    "get_violation_stats", "get_user_daily_stats",
]
