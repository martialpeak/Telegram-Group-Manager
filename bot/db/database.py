"""
پایگاه داده SQLite — اخطارها، لاگ پیام‌ها، دانش یادگرفته‌شده
"""

import aiosqlite
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = "group_manager.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS warnings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            chat_id    INTEGER NOT NULL,
            reason     TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS message_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            chat_id      INTEGER NOT NULL,
            username     TEXT,
            full_name    TEXT,
            text         TEXT,
            message_type TEXT,
            confidence   REAL,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS spam_tracker (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            chat_id    INTEGER NOT NULL,
            sent_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS knowledge_base (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            question    TEXT NOT NULL,
            answer      TEXT NOT NULL,
            source      TEXT DEFAULT 'learned',
            score       REAL DEFAULT 1.0,
            use_count   INTEGER DEFAULT 0,
            chat_id     INTEGER,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id  INTEGER,
            user_id     INTEGER,
            chat_id     INTEGER,
            original_q  TEXT,
            bot_answer  TEXT,
            correct     INTEGER DEFAULT 0,
            correction  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS feedback_rate (
            user_id    INTEGER NOT NULL,
            chat_id    INTEGER NOT NULL,
            sent_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS correction_votes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_id   INTEGER NOT NULL,
            voter_id      INTEGER NOT NULL,
            vote          INTEGER NOT NULL,
            created_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(feedback_id, voter_id)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id   INTEGER NOT NULL,
            reported_id   INTEGER NOT NULL,
            chat_id       INTEGER NOT NULL,
            message_id    INTEGER,
            message_text  TEXT,
            reason        TEXT,
            status        TEXT DEFAULT 'pending',
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS punishment_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            type        TEXT    NOT NULL,
            duration    INTEGER NOT NULL,
            reason      TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_levels (
            user_id     INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            level       TEXT    NOT NULL DEFAULT 'simple',
            set_by      INTEGER,
            updated_at  TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, chat_id)
        );

        CREATE TABLE IF NOT EXISTS bot_query_count (
            user_id  INTEGER NOT NULL,
            chat_id  INTEGER NOT NULL,
            day      TEXT    NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, chat_id, day)
        );

        CREATE TABLE IF NOT EXISTS daily_action_count (
            user_id  INTEGER NOT NULL,
            chat_id  INTEGER NOT NULL,
            day      TEXT    NOT NULL,
            action   TEXT    NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, chat_id, day, action)
        );

        CREATE TABLE IF NOT EXISTS user_message_count (
            user_id  INTEGER NOT NULL,
            chat_id  INTEGER NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        );

        CREATE TABLE IF NOT EXISTS user_points (
            user_id  INTEGER NOT NULL,
            chat_id  INTEGER NOT NULL,
            points   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        );

        CREATE TABLE IF NOT EXISTS upgrade_pending (
            user_id     INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            from_level  TEXT NOT NULL,
            to_level    TEXT NOT NULL,
            points      INTEGER NOT NULL,
            notified_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, chat_id)
        );

        CREATE INDEX IF NOT EXISTS idx_warnings_user  ON warnings(user_id, chat_id);
        CREATE INDEX IF NOT EXISTS idx_msglog_chat    ON message_log(chat_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_kb_question    ON knowledge_base(question);
        CREATE INDEX IF NOT EXISTS idx_fb_rate        ON feedback_rate(user_id, chat_id, sent_at);
        CREATE INDEX IF NOT EXISTS idx_cv_feedback    ON correction_votes(feedback_id);
        CREATE INDEX IF NOT EXISTS idx_reports_chat   ON reports(chat_id, status, created_at);
        CREATE INDEX IF NOT EXISTS idx_reports_user   ON reports(reporter_id, chat_id);
        CREATE INDEX IF NOT EXISTS idx_ph_user        ON punishment_history(user_id, chat_id, type);
        CREATE INDEX IF NOT EXISTS idx_ul_chat        ON user_levels(chat_id);
        """)
        await db.commit()
    logger.info("✅ پایگاه داده آماده شد.")


# ─── اخطارها ─────────────────────────────────────────────────────────────────

async def add_warning(user_id: int, chat_id: int, reason: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (user_id, chat_id, reason) VALUES (?,?,?)",
            (user_id, chat_id, reason),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 1


async def get_warnings(user_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def reset_warnings(user_id: int, chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        await db.commit()


# ─── لاگ پیام‌ها ─────────────────────────────────────────────────────────────

async def log_message(
    user_id: int, chat_id: int, username: str,
    full_name: str, text: str, msg_type: str, confidence: float
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO message_log
               (user_id,chat_id,username,full_name,text,message_type,confidence)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, chat_id, username, full_name, text, msg_type, confidence),
        )
        await db.commit()


async def search_messages(query: str, chat_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT full_name, text, created_at FROM message_log
               WHERE chat_id=? AND text LIKE ? AND message_type='normal'
               ORDER BY created_at DESC LIMIT ?""",
            (chat_id, f"%{query}%", limit),
        )
        rows = await cur.fetchall()
        return [{"name": r[0], "text": r[1], "date": r[2]} for r in rows]


# ─── اسپم ────────────────────────────────────────────────────────────────────

async def track_spam(
    user_id: int, chat_id: int, time_window: int, max_messages: int
) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM spam_tracker WHERE sent_at < datetime('now', ?)",
            (f"-{time_window} seconds",),
        )
        await db.execute(
            "INSERT INTO spam_tracker (user_id, chat_id) VALUES (?,?)",
            (user_id, chat_id),
        )
        await db.commit()
        cur = await db.execute(
            """SELECT COUNT(*) FROM spam_tracker
               WHERE user_id=? AND chat_id=?
               AND sent_at >= datetime('now', ?)""",
            (user_id, chat_id, f"-{time_window} seconds"),
        )
        row = await cur.fetchone()
        return (row[0] if row else 0) >= max_messages


# ─── پایگاه دانش ─────────────────────────────────────────────────────────────

async def save_knowledge(
    question: str, answer: str, chat_id: int,
    source: str = "learned", score: float = 1.0
):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM knowledge_base WHERE question=? AND chat_id=?",
            (question, chat_id),
        )
        row = await cur.fetchone()
        if row:
            await db.execute(
                """UPDATE knowledge_base
                   SET answer=?, score=?, updated_at=datetime('now')
                   WHERE id=?""",
                (answer, score, row[0]),
            )
        else:
            await db.execute(
                """INSERT INTO knowledge_base
                   (question, answer, chat_id, source, score)
                   VALUES (?,?,?,?,?)""",
                (question, answer, chat_id, source, score),
            )
        await db.commit()


async def get_knowledge(chat_id: int, limit: int = 200) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT id, question, answer, score FROM knowledge_base
               WHERE chat_id=? OR chat_id IS NULL
               ORDER BY score DESC, use_count DESC LIMIT ?""",
            (chat_id, limit),
        )
        rows = await cur.fetchall()
        return [{"id": r[0], "question": r[1], "answer": r[2], "score": r[3]}
                for r in rows]


async def increment_use(kb_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE knowledge_base SET use_count=use_count+1 WHERE id=?",
            (kb_id,),
        )
        await db.commit()


async def save_feedback(
    user_id: int, chat_id: int, original_q: str, bot_answer: str,
    correct: bool, correction: str = ""
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO feedback
               (user_id,chat_id,original_q,bot_answer,correct,correction)
               VALUES (?,?,?,?,?,?)""",
            (user_id, chat_id, original_q, bot_answer, int(correct), correction),
        )
        await db.commit()
        return cur.lastrowid


# ─── Rate Limit فیدبک ────────────────────────────────────────────────────────

async def check_feedback_rate(
    user_id: int, chat_id: int, max_per_hour: int = 5
) -> bool:
    """True = مجاز است، False = محدود شده"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM feedback_rate WHERE sent_at < datetime('now', '-1 hour')"
        )
        cur = await db.execute(
            """SELECT COUNT(*) FROM feedback_rate
               WHERE user_id=? AND chat_id=?
               AND sent_at >= datetime('now', '-1 hour')""",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        count = row[0] if row else 0
        if count >= max_per_hour:
            await db.commit()
            return False
        await db.execute(
            "INSERT INTO feedback_rate (user_id, chat_id) VALUES (?,?)",
            (user_id, chat_id),
        )
        await db.commit()
        return True


# ─── رای‌گیری روی تصحیح‌ها ────────────────────────────────────────────────────

async def vote_correction(feedback_id: int, voter_id: int, vote: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO correction_votes (feedback_id, voter_id, vote)
                   VALUES (?,?,?)""",
                (feedback_id, voter_id, vote),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            pass  # قبلاً رای داده

        cur = await db.execute(
            """SELECT
                 SUM(CASE WHEN vote=1  THEN 1 ELSE 0 END),
                 SUM(CASE WHEN vote=-1 THEN 1 ELSE 0 END)
               FROM correction_votes WHERE feedback_id=?""",
            (feedback_id,),
        )
        row = await cur.fetchone()
        ups   = row[0] or 0
        downs = row[1] or 0
        return {"ups": ups, "downs": downs, "net": ups - downs}


async def get_feedback_by_id(feedback_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id,user_id,chat_id,original_q,bot_answer,correction FROM feedback WHERE id=?",
            (feedback_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "user_id": row[1], "chat_id": row[2],
            "question": row[3], "bot_answer": row[4], "correction": row[5],
        }


async def count_user_corrections(
    user_id: int, chat_id: int, original_q: str
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM feedback
               WHERE user_id=? AND chat_id=? AND original_q=? AND correct=0""",
            (user_id, chat_id, original_q),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_pending_feedback(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT f.user_id, f.chat_id, f.original_q, f.correction
               FROM feedback f
               WHERE f.correct=0 AND f.correction != ''
               AND (
                   SELECT COALESCE(SUM(v.vote), 0)
                   FROM correction_votes v
                   WHERE v.feedback_id = f.id
               ) >= 2
               LIMIT ?""",
            (limit,),
        )
        rows = await cur.fetchall()
        return [{"user_id": r[0], "chat_id": r[1],
                 "question": r[2], "answer": r[3]} for r in rows]


# ─── تاریخچه مجازات پلکانی ───────────────────────────────────────────────────

async def add_punishment(
    user_id: int, chat_id: int, ptype: str, duration: int, reason: str = ""
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO punishment_history (user_id, chat_id, type, duration, reason)
               VALUES (?,?,?,?,?)""",
            (user_id, chat_id, ptype, duration, reason),
        )
        await db.commit()


async def get_punishment_count(user_id: int, chat_id: int, ptype: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM punishment_history
               WHERE user_id=? AND chat_id=? AND type=?""",
            (user_id, chat_id, ptype),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ─── سطح کاربری ──────────────────────────────────────────────────────────────

async def get_user_level(user_id: int, chat_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT level FROM user_levels WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        return row[0] if row else "simple"


async def set_user_level(user_id: int, chat_id: int, level: str, set_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_levels (user_id, chat_id, level, set_by, updated_at)
               VALUES (?,?,?,?,datetime('now'))
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET level=excluded.level, set_by=excluded.set_by,
                   updated_at=excluded.updated_at""",
            (user_id, chat_id, level, set_by),
        )
        await db.commit()


async def get_chat_levels(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT user_id, level, updated_at FROM user_levels
               WHERE chat_id=? AND level != 'simple'
               ORDER BY level, updated_at DESC""",
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [{"user_id": r[0], "level": r[1], "updated_at": r[2]} for r in rows]


# ─── شمارش روزانه لینک / فوروارد ─────────────────────────────────────────────

async def increment_daily_action(user_id: int, chat_id: int, action: str) -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO daily_action_count (user_id, chat_id, day, action, count)
               VALUES (?,?,?,?,1)
               ON CONFLICT(user_id, chat_id, day, action) DO UPDATE
               SET count = count + 1""",
            (user_id, chat_id, today, action),
        )
        await db.commit()
        cur = await db.execute(
            """SELECT count FROM daily_action_count
               WHERE user_id=? AND chat_id=? AND day=? AND action=?""",
            (user_id, chat_id, today, action),
        )
        row = await cur.fetchone()
        return row[0] if row else 1


async def get_daily_action(user_id: int, chat_id: int, action: str) -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT count FROM daily_action_count
               WHERE user_id=? AND chat_id=? AND day=? AND action=?""",
            (user_id, chat_id, today, action),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ─── شمارش پیام برای ارتقاء خودکار ──────────────────────────────────────────

async def increment_message_count(user_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_message_count (user_id, chat_id, count)
               VALUES (?,?,1)
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET count = count + 1""",
            (user_id, chat_id),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT count FROM user_message_count WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 1


async def get_message_count(user_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT count FROM user_message_count WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ─── شمارش سوال روزانه ────────────────────────────────────────────────────────

async def increment_query_count(user_id: int, chat_id: int) -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO bot_query_count (user_id, chat_id, day, count)
               VALUES (?,?,?,1)
               ON CONFLICT(user_id, chat_id, day) DO UPDATE
               SET count = count + 1""",
            (user_id, chat_id, today),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT count FROM bot_query_count WHERE user_id=? AND chat_id=? AND day=?",
            (user_id, chat_id, today),
        )
        row = await cur.fetchone()
        return row[0] if row else 1


async def get_query_count(user_id: int, chat_id: int) -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT count FROM bot_query_count WHERE user_id=? AND chat_id=? AND day=?",
            (user_id, chat_id, today),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ─── گزارش‌ها ─────────────────────────────────────────────────────────────────

async def save_report(
    reporter_id: int, reported_id: int, chat_id: int,
    message_id: int, message_text: str, reason: str
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO reports
               (reporter_id, reported_id, chat_id, message_id, message_text, reason)
               VALUES (?,?,?,?,?,?)""",
            (reporter_id, reported_id, chat_id, message_id, message_text, reason),
        )
        await db.commit()
        return cur.lastrowid


async def get_user_report_today(reporter_id: int, chat_id: int) -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM reports
               WHERE reporter_id=? AND chat_id=? AND date(created_at)=?""",
            (reporter_id, chat_id, today),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_pending_reports(chat_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT id, reporter_id, reported_id, message_id,
                      message_text, reason, created_at
               FROM reports
               WHERE chat_id=? AND status='pending'
               ORDER BY created_at DESC LIMIT ?""",
            (chat_id, limit),
        )
        rows = await cur.fetchall()
        return [
            {
                "id":           r[0],
                "reporter_id":  r[1],
                "reported_id":  r[2],
                "message_id":   r[3],
                "message_text": r[4],
                "reason":       r[5],
                "created_at":   r[6],
            }
            for r in rows
        ]


async def update_report_status(report_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reports SET status=? WHERE id=?",
            (status, report_id),
        )
        await db.commit()


async def get_report_count(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT status, COUNT(*) FROM reports WHERE chat_id=? GROUP BY status",
            (chat_id,),
        )
        return {r[0]: r[1] for r in await cur.fetchall()}


# ─── آمار ─────────────────────────────────────────────────────────────────────

async def get_stats(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT message_type, COUNT(*) FROM message_log WHERE chat_id=? GROUP BY message_type",
            (chat_id,),
        )
        stats = {r[0]: r[1] for r in await cur.fetchall()}

        cur2 = await db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM warnings WHERE chat_id=?", (chat_id,)
        )
        r2 = await cur2.fetchone()
        stats["warned_users"] = r2[0] if r2 else 0

        cur3 = await db.execute(
            "SELECT COUNT(*) FROM knowledge_base WHERE chat_id=?", (chat_id,)
        )
        r3 = await cur3.fetchone()
        stats["knowledge_items"] = r3[0] if r3 else 0

        return stats


async def get_daily_stats(chat_id: int) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT message_type, COUNT(*) FROM message_log
               WHERE chat_id=? AND date(created_at)=? GROUP BY message_type""",
            (chat_id, today),
        )
        msgs = {r[0]: r[1] for r in await cur.fetchall()}

        cur = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id=? AND date(created_at)=?",
            (chat_id, today),
        )
        msgs["warns_today"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COUNT(*) FROM punishment_history
               WHERE chat_id=? AND type='mute' AND date(created_at)=?""",
            (chat_id, today),
        )
        msgs["mutes_today"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COUNT(*) FROM punishment_history
               WHERE chat_id=? AND type='ban' AND date(created_at)=?""",
            (chat_id, today),
        )
        msgs["bans_today"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COUNT(DISTINCT user_id) FROM message_log
               WHERE chat_id=? AND date(created_at)=?""",
            (chat_id, today),
        )
        msgs["active_users_today"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COALESCE(SUM(count),0) FROM daily_action_count
               WHERE chat_id=? AND day=? AND action='link'""",
            (chat_id, today),
        )
        msgs["links_today"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COALESCE(SUM(count),0) FROM daily_action_count
               WHERE chat_id=? AND day=? AND action='forward'""",
            (chat_id, today),
        )
        msgs["forwards_today"] = (await cur.fetchone())[0] or 0

        return msgs


async def get_violation_stats(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT message_type, COUNT(*) FROM message_log
               WHERE chat_id=? AND message_type IN ('insult','spam')
               GROUP BY message_type""",
            (chat_id,),
        )
        totals = {r[0]: r[1] for r in await cur.fetchall()}

        cur = await db.execute(
            """SELECT message_type, COUNT(*) FROM message_log
               WHERE chat_id=? AND message_type IN ('insult','spam')
               AND created_at >= datetime('now','-7 days')
               GROUP BY message_type""",
            (chat_id,),
        )
        week = {r[0]: r[1] for r in await cur.fetchall()}

        cur = await db.execute(
            "SELECT COUNT(*) FROM punishment_history WHERE chat_id=? AND type='mute'",
            (chat_id,),
        )
        totals["mutes"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            "SELECT COUNT(*) FROM punishment_history WHERE chat_id=? AND type='ban'",
            (chat_id,),
        )
        totals["bans"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COUNT(*) FROM punishment_history
               WHERE chat_id=? AND type='mute'
               AND created_at >= datetime('now','-7 days')""",
            (chat_id,),
        )
        week["mutes"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COUNT(*) FROM punishment_history
               WHERE chat_id=? AND type='ban'
               AND created_at >= datetime('now','-7 days')""",
            (chat_id,),
        )
        week["bans"] = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT full_name, COUNT(*) as cnt FROM message_log
               WHERE chat_id=? AND message_type IN ('insult','spam')
               GROUP BY user_id ORDER BY cnt DESC LIMIT 5""",
            (chat_id,),
        )
        top_violators = [{"name": r[0], "count": r[1]} for r in await cur.fetchall()]

        return {"total": totals, "week": week, "top_violators": top_violators}


async def get_user_daily_stats(user_id: int, chat_id: int) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM message_log
               WHERE user_id=? AND chat_id=? AND date(created_at)=?""",
            (user_id, chat_id, today),
        )
        msgs_today = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COUNT(*) FROM message_log
               WHERE user_id=? AND chat_id=? AND date(created_at)=?
               AND message_type IN ('insult','spam')""",
            (user_id, chat_id, today),
        )
        violations_today = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            """SELECT COUNT(*) FROM punishment_history
               WHERE user_id=? AND chat_id=? AND type='mute'
               AND created_at >= datetime('now','-7 days')""",
            (user_id, chat_id),
        )
        mutes_week = (await cur.fetchone())[0] or 0

        cur = await db.execute(
            "SELECT COUNT(*) FROM punishment_history WHERE user_id=? AND chat_id=? AND type='ban'",
            (user_id, chat_id),
        )
        bans_total = (await cur.fetchone())[0] or 0

        return {
            "msgs_today":       msgs_today,
            "violations_today": violations_today,
            "mutes_week":       mutes_week,
            "bans_total":       bans_total,
        }


# ─── امتیاز کاربران ──────────────────────────────────────────────────────────

async def add_points(user_id: int, chat_id: int, delta: int) -> int:
    """امتیاز اضافه/کم کن، برگردون مجموع جدید"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_points (user_id, chat_id, points)
               VALUES (?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET points = points + excluded.points""",
            (user_id, chat_id, delta),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT points FROM user_points WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_points(user_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT points FROM user_points WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def save_upgrade_pending(
    user_id: int, chat_id: int, from_level: str, to_level: str, points: int
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO upgrade_pending (user_id, chat_id, from_level, to_level, points)
               VALUES (?,?,?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET from_level=excluded.from_level,
                   to_level=excluded.to_level,
                   points=excluded.points,
                   notified_at=datetime('now')""",
            (user_id, chat_id, from_level, to_level, points),
        )
        await db.commit()


async def get_upgrade_pending(user_id: int, chat_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT user_id, chat_id, from_level, to_level, points
               FROM upgrade_pending WHERE user_id=? AND chat_id=?""",
            (user_id, chat_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "user_id":    row[0],
            "chat_id":    row[1],
            "from_level": row[2],
            "to_level":   row[3],
            "points":     row[4],
        }


async def delete_upgrade_pending(user_id: int, chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM upgrade_pending WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        await db.commit()
