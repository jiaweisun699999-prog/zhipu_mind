"""
迁移脚本：为 conversations 表补充 persona_id 列
在生产服务器上执行一次即可：python migrate_add_persona.py
"""
from pathlib import Path
from sqlalchemy import create_engine, text

DB_PATH = Path(__file__).parent / "data" / "app.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

with engine.connect() as conn:
    try:
        conn.execute(text(
            "ALTER TABLE conversations ADD COLUMN persona_id VARCHAR(64) NOT NULL DEFAULT 'hu-chenfeng'"
        ))
        conn.commit()
        print("✅ 迁移成功：persona_id 列已添加到 conversations 表")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️  列已存在，无需迁移")
        else:
            print(f"❌ 迁移失败: {e}")
            raise
