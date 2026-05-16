"""
数据库迁移脚本 —— 一次性执行
功能：
  1. 给 users 表添加 invite_code 字段（若不存在）
  2. 创建 invite_codes 表（若不存在）

SQLite 不支持 ALTER COLUMN，但支持 ADD COLUMN。
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "app.db"

if not DB_PATH.exists():
    print("DB file not found, skipping migration (tables will be created on first startup).")
    exit(0)

conn = sqlite3.connect(str(DB_PATH))
cur  = conn.cursor()

# -- 1. Add invite_code column to users table if missing ---------------------
cur.execute("PRAGMA table_info(users)")
columns = [row[1] for row in cur.fetchall()]
if "invite_code" not in columns:
    cur.execute("ALTER TABLE users ADD COLUMN invite_code TEXT")
    print("[OK] Added invite_code column to users table")
else:
    print("[SKIP] users.invite_code already exists")

# -- 2. Create invite_codes table if not exists ------------------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS invite_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    distributor TEXT    NOT NULL,
    is_used     INTEGER NOT NULL DEFAULT 0,
    used_by     TEXT,
    used_at     DATETIME,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_invite_codes_code ON invite_codes (code)")
print("[OK] invite_codes table is ready")

conn.commit()
conn.close()
print("\n[DONE] Migration complete! You can now start the server.")
