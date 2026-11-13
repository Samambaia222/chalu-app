"""SQLite 数据库连接与会话管理"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "chalu.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """建表（幂等）+ 老库自动补列"""
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate_user_columns()


def _migrate_user_columns():
    """给已存在的老版本表补充新增列（SQLite ALTER 幂等）"""
    from sqlalchemy import text
    plan = {
        "user": [
            ("archive_code", "ALTER TABLE user ADD COLUMN archive_code VARCHAR(8)"),
            ("gender", "ALTER TABLE user ADD COLUMN gender VARCHAR(6)"),
            ("tags", "ALTER TABLE user ADD COLUMN tags TEXT"),
            ("raw_text", "ALTER TABLE user ADD COLUMN raw_text TEXT"),
        ],
        "sample": [
            ("key_action", "ALTER TABLE sample ADD COLUMN key_action VARCHAR(40)"),
            ("gender", "ALTER TABLE sample ADD COLUMN gender VARCHAR(6)"),
        ],
    }
    with engine.connect() as conn:
        for table, cols_def in plan.items():
            cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))]
            for col, ddl in cols_def:
                if col not in cols:
                    conn.execute(text(ddl))
        conn.commit()
