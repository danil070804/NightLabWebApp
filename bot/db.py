from __future__ import annotations
import aiosqlite
import datetime as dt
from typing import Optional, Any

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'USER',
    balance_uah REAL NOT NULL DEFAULT 0,
    referral_code TEXT UNIQUE,
    referred_by INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(referred_by) REFERENCES users(tg_id)
);

CREATE TABLE IF NOT EXISTS countries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER,
    bank_name TEXT NOT NULL UNIQUE,
    requisites_text TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY(country_id) REFERENCES countries(id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_tg_id INTEGER NOT NULL,
    bank_id INTEGER,
    amount_uah REAL NOT NULL,
    payment_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    requisites_sent_at TEXT,
    expires_at TEXT,
    updated_at TEXT NOT NULL,
    assigned_merchant_tg_id INTEGER,
    requisites_text_override TEXT,
    receipt_file_id TEXT,
    receipt_file_type TEXT,
    FOREIGN KEY(user_tg_id) REFERENCES users(tg_id),
    FOREIGN KEY(bank_id) REFERENCES bank_accounts(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL,
    from_tg_id INTEGER NOT NULL,
    to_tg_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(app_id) REFERENCES applications(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER,
    action TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_tg_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    data TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_tg_id) REFERENCES users(tg_id)
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_tg_id INTEGER NOT NULL,
    referred_tg_id INTEGER NOT NULL,
    bonus_uah REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(referrer_tg_id) REFERENCES users(tg_id),
    FOREIGN KEY(referred_tg_id) REFERENCES users(tg_id),
    UNIQUE(referred_tg_id)
);
"""

def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

class Database:
    def __init__(self, path: str):
        self.path = path
        self._app_cols: set[str] | None = None

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)

            async def cols(table: str) -> set[str]:
                cur = await db.execute(f"PRAGMA table_info({table})")
                rows = await cur.fetchall()
                return {r[1] for r in rows}

            # Migration: bank_accounts.country_id
            bank_cols = await cols("bank_accounts")
            if "country_id" not in bank_cols:
                await db.execute("ALTER TABLE bank_accounts ADD COLUMN country_id INTEGER")

            # Migration: applications columns
            app_cols = await cols("applications")
            self._app_cols = app_cols
            if "bank_id" not in app_cols:
                await db.execute("ALTER TABLE applications ADD COLUMN bank_id INTEGER")
            if "receipt_file_id" not in app_cols:
                await db.execute("ALTER TABLE applications ADD COLUMN receipt_file_id TEXT")
            if "receipt_file_type" not in app_cols:
                await db.execute("ALTER TABLE applications ADD COLUMN receipt_file_type TEXT")
            if "requisites_text_override" not in app_cols:
                await db.execute("ALTER TABLE applications ADD COLUMN requisites_text_override TEXT")

            # Migration: users new columns
            user_cols = await cols("users")
            if "balance_uah" not in user_cols:
                await db.execute("ALTER TABLE users ADD COLUMN balance_uah REAL NOT NULL DEFAULT 0")
            if "referral_code" not in user_cols:
                await db.execute("ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE")
            if "referred_by" not in user_cols:
                await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")

            # Migration: legacy bank_name -> bank_id with countries
            if "bank_name" in app_cols:
                await db.execute(
                    "INSERT OR IGNORE INTO countries (name, is_active, created_at) VALUES (?, 1, ?)",
                    ("Украина", now_iso())
                )
                cur = await db.execute("SELECT id FROM countries WHERE name=?", ("Украина",))
                default_country_id = (await cur.fetchone())[0]

                cur = await db.execute("SELECT DISTINCT bank_name FROM applications WHERE bank_name IS NOT NULL AND bank_name != ''")
                names = [r[0] for r in await cur.fetchall()]
                for name in names:
                    await db.execute(
                        """INSERT OR IGNORE INTO bank_accounts (country_id, bank_name, requisites_text, is_active, created_at)
                           VALUES (?, ?, ?, 1, ?)""",
                        (default_country_id, name, "Реквизиты не заданы. Обновите в /admin.", now_iso()),
                    )
                await db.execute(
                    """
                    UPDATE applications
                    SET bank_id = (SELECT id FROM bank_accounts b WHERE b.bank_name = applications.bank_name)
                    WHERE bank_id IS NULL AND bank_name IS NOT NULL
                    """
                )
            await db.commit()

    # === Settings ===
    async def get_setting(self, key: str, default: str = "") -> str:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = await cur.fetchone()
            return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, value, now_iso())
            )
            await db.commit()

    # === Countries ===
    async def list_countries(self, active_only: bool = True) -> list[tuple[int, str, int]]:
        q = "SELECT id, name, is_active FROM countries"
        if active_only:
            q += " WHERE is_active=1"
        q += " ORDER BY name"
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(q)
            return await cur.fetchall()

    async def get_country(self, country_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT id, name, is_active FROM countries WHERE id=?", (country_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return {"id": row[0], "name": row[1], "is_active": bool(row[2])}

    async def upsert_country(self, name: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO countries (name, is_active, created_at) VALUES (?, 1, ?)
                   ON CONFLICT(name) DO UPDATE SET is_active=1""",
                (name, now_iso())
            )
            await db.commit()

    async def set_country_active(self, country_id: int, is_active: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE countries SET is_active=? WHERE id=?", (1 if is_active else 0, country_id))
            await db.commit()

    # === Banks ===
    async def list_banks(self, active_only: bool = True) -> list[tuple[int, str, int]]:
        q = "SELECT id, bank_name, is_active FROM bank_accounts"
        if active_only:
            q += " WHERE is_active=1"
        q += " ORDER BY bank_name"
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(q)
            return await cur.fetchall()

    async def list_banks_by_country(self, country_id: int, active_only: bool = True) -> list[tuple[int, str, int]]:
        q = "SELECT id, bank_name, is_active FROM bank_accounts WHERE country_id=?"
        if active_only:
            q += " AND is_active=1"
        q += " ORDER BY bank_name"
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(q, (country_id,))
            return await cur.fetchall()

    async def get_bank(self, bank_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT id, country_id, bank_name, requisites_text, is_active FROM bank_accounts WHERE id=?",
                (bank_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {"id": row[0], "country_id": row[1], "bank_name": row[2], "requisites_text": row[3], "is_active": bool(row[4])}

    async def upsert_bank(self, bank_name: str, requisites_text: str, country_id: int = 1) -> None:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT id, country_id FROM bank_accounts WHERE bank_name=?", (bank_name,))
            row = await cur.fetchone()
            if row:
                await db.execute(
                    "UPDATE bank_accounts SET requisites_text=?, country_id=?, is_active=1 WHERE id=?",
                    (requisites_text, country_id, row[0])
                )
            else:
                await db.execute(
                    """INSERT INTO bank_accounts (country_id, bank_name, requisites_text, is_active, created_at)
                       VALUES (?, ?, ?, 1, ?)""",
                    (country_id, bank_name, requisites_text, now_iso())
                )
            await db.commit()

    async def set_bank_active(self, bank_id: int, is_active: bool) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE bank_accounts SET is_active=? WHERE id=?", (1 if is_active else 0, bank_id))
            await db.commit()

    # === Applications ===
    async def create_application(self, user_tg_id: int, bank_id: int, amount_uah: float, payment_code: str) -> int:
        created = now_iso()
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                INSERT INTO applications (user_tg_id, bank_id, amount_uah, payment_code, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'WAITING_MERCHANT', ?, ?)
                """,
                (user_tg_id, bank_id, amount_uah, payment_code, created, created),
            )
            await db.commit()
            return cur.lastrowid

    async def get_application(self, app_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                SELECT id, user_tg_id, bank_id, amount_uah, payment_code, status,
                       created_at, requisites_sent_at, expires_at, updated_at,
                       assigned_merchant_tg_id, requisites_text_override,
                       receipt_file_id, receipt_file_type
                FROM applications WHERE id=?
                """,
                (app_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            keys = [
                "id","user_tg_id","bank_id","amount_uah","payment_code","status",
                "created_at","requisites_sent_at","expires_at","updated_at",
                "assigned_merchant_tg_id","requisites_text_override",
                "receipt_file_id","receipt_file_type"
            ]
            return dict(zip(keys, row))

    async def list_user_apps(self, user_tg_id: int, limit: int = 20, offset: int = 0, status_filter: str | None = None) -> list[tuple]:
        async with aiosqlite.connect(self.path) as db:
            query = """
                SELECT a.id, COALESCE(b.bank_name, '[UNKNOWN]') as bank_name, a.amount_uah, a.payment_code, a.status, a.created_at
                FROM applications a
                LEFT JOIN bank_accounts b ON b.id=a.bank_id
                WHERE a.user_tg_id=?
            """
            params = [user_tg_id]
            if status_filter:
                query += " AND a.status = ?"
                params.append(status_filter)
            query += " ORDER BY a.id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cur = await db.execute(query, params)
            return await cur.fetchall()

    async def count_user_apps(self, user_tg_id: int, status_filter: str | None = None) -> int:
        async with aiosqlite.connect(self.path) as db:
            query = "SELECT COUNT(*) FROM applications WHERE user_tg_id=?"
            params = [user_tg_id]
            if status_filter:
                query += " AND status = ?"
                params.append(status_filter)
            cur = await db.execute(query, params)
            row = await cur.fetchone()
            return row[0] if row else 0

    async def assign_merchant(self, app_id: int, merchant_tg_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                UPDATE applications
                SET assigned_merchant_tg_id=?, status='MERCHANT_TAKEN', updated_at=?
                WHERE id=? AND status='WAITING_MERCHANT'
                """,
                (merchant_tg_id, now_iso(), app_id),
            )
            await db.commit()
            return cur.rowcount == 1

    async def unassign_merchant(self, app_id: int, merchant_tg_id: int | None = None) -> bool:
        now = now_iso()
        async with aiosqlite.connect(self.path) as db:
            if merchant_tg_id is None:
                cur = await db.execute(
                    """
                    UPDATE applications
                    SET status='WAITING_MERCHANT', assigned_merchant_tg_id=NULL, updated_at=?
                    WHERE id=? AND status='MERCHANT_TAKEN'
                    """,
                    (now, app_id),
                )
            else:
                cur = await db.execute(
                    """
                    UPDATE applications
                    SET status='WAITING_MERCHANT', assigned_merchant_tg_id=NULL, updated_at=?
                    WHERE id=? AND status='MERCHANT_TAKEN' AND assigned_merchant_tg_id=?
                    """,
                    (now, app_id, merchant_tg_id),
                )
            await db.commit()
            return cur.rowcount == 1

    async def set_requisites_and_start_timer(self, app_id: int, requisites_text: str, ttl_minutes: int = 20) -> bool:
        created = dt.datetime.utcnow().replace(microsecond=0)
        sent = created.isoformat() + "Z"
        exp = (created + dt.timedelta(minutes=ttl_minutes)).isoformat() + "Z"
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                UPDATE applications
                SET requisites_text_override=?, requisites_sent_at=?, expires_at=?, status='WAITING_PAYMENT', updated_at=?
                WHERE id=? AND status='MERCHANT_TAKEN'
                """,
                (requisites_text, sent, exp, now_iso(), app_id),
            )
            await db.commit()
            return cur.rowcount == 1

    async def set_app_status(self, app_id: int, status: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE applications SET status=?, updated_at=? WHERE id=?", (status, now_iso(), app_id))
            await db.commit()

    async def set_receipt(self, app_id: int, file_id: str, file_type: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE applications SET receipt_file_id=?, receipt_file_type=?, updated_at=? WHERE id=?",
                (file_id, file_type, now_iso(), app_id),
            )
            await db.commit()

    async def expire_overdue(self) -> list[int]:
        now = now_iso()
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT id FROM applications WHERE status='WAITING_PAYMENT' AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            rows = await cur.fetchall()
            ids = [r[0] for r in rows]
            if ids:
                await db.executemany(
                    "UPDATE applications SET status='EXPIRED', updated_at=? WHERE id=?",
                    [(now, _id) for _id in ids],
                )
                await db.commit()
            return ids

    async def add_message(self, app_id: int, from_tg_id: int, to_tg_id: int, text: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO messages (app_id, from_tg_id, to_tg_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
                (app_id, from_tg_id, to_tg_id, text, now_iso()),
            )
            await db.commit()

    # === Users ===
    async def user_exists(self, tg_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT 1 FROM users WHERE tg_id=? LIMIT 1", (tg_id,))
            row = await cur.fetchone()
            return bool(row)

        async def upsert_user(self, tg_id: int, username: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            # Проверяем существование
            cur = await db.execute("SELECT tg_id FROM users WHERE tg_id=?", (tg_id,))
            row = await cur.fetchone()
            if row:
                await db.execute("UPDATE users SET username=? WHERE tg_id=?", (username, tg_id))
            else:
                referral_code = f"REF{tg_id}"
                await db.execute(
                    "INSERT INTO users (tg_id, username, role, referral_code, created_at) VALUES (?, ?, 'USER', ?, ?)",
                    (tg_id, username, referral_code, now_iso()),
                )
            await db.commit()

    async def get_user(self, tg_id: int) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT tg_id, username, role, balance_uah, referral_code, referred_by, created_at FROM users WHERE tg_id=?",
                (tg_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "tg_id": row[0],
                "username": row[1],
                "role": row[2],
                "balance_uah": row[3],
                "referral_code": row[4],
                "referred_by": row[5],
                "created_at": row[6]
            }

    async def get_user_by_referral_code(self, referral_code: str) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT tg_id, username, role, balance_uah, referral_code, referred_by, created_at FROM users WHERE referral_code=?",
                (referral_code,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "tg_id": row[0],
                "username": row[1],
                "role": row[2],
                "balance_uah": row[3],
                "referral_code": row[4],
                "referred_by": row[5],
                "created_at": row[6]
            }

    async def get_user_role(self, tg_id: int) -> str:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT role FROM users WHERE tg_id=?", (tg_id,))
            row = await cur.fetchone()
            return row[0] if row else "USER"

    async def set_user_role(self, tg_id: int, role: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET role=? WHERE tg_id=?", (role, tg_id))
            await db.commit()

    async def get_username(self, tg_id: int) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT username FROM users WHERE tg_id=?", (tg_id,))
            row = await cur.fetchone()
            return row[0] if row else None

    async def update_balance(self, tg_id: int, amount: float) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET balance_uah = balance_uah + ? WHERE tg_id=?",
                (amount, tg_id)
            )
            await db.commit()

    # === Statistics ===
    async def get_stats(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            # Total applications
            cur = await db.execute("SELECT COUNT(*) FROM applications")
            total_apps = (await cur.fetchone())[0]

            # Total users
            cur = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cur.fetchone())[0]

            # Total turnover
            cur = await db.execute("SELECT COALESCE(SUM(amount_uah), 0) FROM applications WHERE status IN ('CONFIRMED', 'WAITING_PAYMENT', 'WAITING_RECEIPT', 'WAITING_CHECK')")
            turnover = (await cur.fetchone())[0]

            # Today's applications
            today = dt.datetime.utcnow().strftime("%Y-%m-%d")
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE created_at LIKE ?", (f"{today}%",))
            today_apps = (await cur.fetchone())[0]

            return {
                "total_applications": total_apps,
                "total_users": total_users,
                "turnover": turnover,
                "today_applications": today_apps
            }

    async def get_user_stats(self, tg_id: int) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            # Total user applications
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE user_tg_id=?", (tg_id,))
            total_apps = (await cur.fetchone())[0]

            # Confirmed applications
            cur = await db.execute("SELECT COUNT(*) FROM applications WHERE user_tg_id=? AND status='CONFIRMED'", (tg_id,))
            confirmed_apps = (await cur.fetchone())[0]

            # Total spent
            cur = await db.execute(
                "SELECT COALESCE(SUM(amount_uah), 0) FROM applications WHERE user_tg_id=? AND status='CONFIRMED'",
                (tg_id,)
            )
            total_spent = (await cur.fetchone())[0]

            return {
                "total_applications": total_apps,
                "confirmed_applications": confirmed_apps,
                "total_spent": total_spent
            }

    # === Referrals ===
    async def get_referral_count(self, tg_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_tg_id=?", (tg_id,))
            return (await cur.fetchone())[0]

    async def add_referral(self, referrer_tg_id: int, referred_tg_id: int, bonus_uah: float = 0) -> bool:
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    "INSERT INTO referrals (referrer_tg_id, referred_tg_id, bonus_uah, created_at) VALUES (?, ?, ?, ?)",
                    (referrer_tg_id, referred_tg_id, bonus_uah, now_iso())
                )
                await db.execute(
                    "UPDATE users SET referred_by = ? WHERE tg_id = ?",
                    (referrer_tg_id, referred_tg_id)
                )
                await db.commit()
                return True
            except Exception:
                return False

    # === Notifications ===
    async def create_notification(self, user_tg_id: int, type: str, title: str, message: str, data: str | None = None) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """INSERT INTO notifications (user_tg_id, type, title, message, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_tg_id, type, title, message, data, now_iso())
            )
            await db.commit()
            return cur.lastrowid

    async def get_user_notifications(self, user_tg_id: int, limit: int = 20) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """SELECT id, type, title, message, is_read, data, created_at
                   FROM notifications WHERE user_tg_id=? ORDER BY id DESC LIMIT ?""",
                (user_tg_id, limit)
            )
            rows = await cur.fetchall()
            return [
                {
                    "id": row[0],
                    "type": row[1],
                    "title": row[2],
                    "message": row[3],
                    "is_read": bool(row[4]),
                    "data": row[5],
                    "created_at": row[6]
                }
                for row in rows
            ]

    async def mark_notification_read(self, notification_id: int, user_tg_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE notifications SET is_read=1 WHERE id=? AND user_tg_id=?",
                (notification_id, user_tg_id)
            )
            await db.commit()
            return cur.rowcount == 1

    async def get_unread_notifications_count(self, user_tg_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_tg_id=? AND is_read=0",
                (user_tg_id,)
            )
            return (await cur.fetchone())[0]

    # === Broadcast ===
    async def get_all_users(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT tg_id FROM users")
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def log(self, tg_id: int | None, action: str, payload: str | None = None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO audit_log (tg_id, action, payload, created_at) VALUES (?, ?, ?, ?)",
                (tg_id, action, payload, now_iso()),
            )
            await db.commit()
