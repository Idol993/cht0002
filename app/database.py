from sqlalchemy import create_engine, inspect, text, String, Integer, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings
import os
import json

os.makedirs("./data", exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_database(engine):
    inspector = inspect(engine)
    with engine.connect() as conn:
        if "message_records" in inspector.get_table_names():
            existing_columns = [col["name"] for col in inspector.get_columns("message_records")]
            message_columns = [
                ("biz_msg_id", "VARCHAR(128)", None, None),
                ("callback_url", "VARCHAR(512)", None, None),
                ("first_send_time", "DATETIME", None, None),
                ("error_code", "VARCHAR(64)", None, None),
                ("error_message", "TEXT", None, None),
                ("max_retries", "INTEGER", None, "3"),
                ("created_at", "DATETIME", None, None),
                ("updated_at", "DATETIME", None, None),
            ]
            for col_name, col_type, sql_default, py_default in message_columns:
                if col_name not in existing_columns:
                    try:
                        conn.execute(text(f"ALTER TABLE message_records ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        if py_default is not None:
                            conn.execute(text(f"UPDATE message_records SET {col_name} = :val"), {"val": py_default})
                            conn.commit()
                    except Exception:
                        pass
            try:
                from datetime import datetime
                now = datetime.utcnow()
                conn.execute(text("UPDATE message_records SET created_at = send_time WHERE created_at IS NULL"))
                conn.commit()
                conn.execute(text("UPDATE message_records SET updated_at = send_time WHERE updated_at IS NULL"))
                conn.commit()
            except Exception:
                pass

        if "channel_configs" in inspector.get_table_names():
            existing_columns = [col["name"] for col in inspector.get_columns("channel_configs")]
            channel_columns = [
                ("config_data", "TEXT", None, "'{}'"),
                ("circuit_breaker_threshold", "INTEGER", None, "5"),
                ("circuit_breaker_recovery_minutes", "INTEGER", None, "10"),
                ("circuit_breaker_active", "BOOLEAN", None, "0"),
                ("circuit_breaker_until", "DATETIME", None, None),
                ("consecutive_failures", "INTEGER", None, "0"),
                ("created_at", "DATETIME", None, None),
                ("updated_at", "DATETIME", None, None),
            ]
            for col_name, col_type, sql_default, py_default in channel_columns:
                if col_name not in existing_columns:
                    try:
                        conn.execute(text(f"ALTER TABLE channel_configs ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        if py_default is not None:
                            if col_name == "config_data":
                                conn.execute(text(f"UPDATE channel_configs SET {col_name} = :val"), {"val": "{}"})
                            else:
                                conn.execute(text(f"UPDATE channel_configs SET {col_name} = :val"), {"val": py_default})
                            conn.commit()
                    except Exception:
                        pass
            try:
                from datetime import datetime
                now = datetime.utcnow()
                conn.execute(text("UPDATE channel_configs SET created_at = :val WHERE created_at IS NULL"), {"val": now})
                conn.commit()
                conn.execute(text("UPDATE channel_configs SET updated_at = :val WHERE updated_at IS NULL"), {"val": now})
                conn.commit()
            except Exception:
                pass

        if "user_preferences" in inspector.get_table_names():
            existing_columns = [col["name"] for col in inspector.get_columns("user_preferences")]
            user_columns = [
                ("created_at", "DATETIME", None, None),
                ("updated_at", "DATETIME", None, None),
            ]
            for col_name, col_type, sql_default, py_default in user_columns:
                if col_name not in existing_columns:
                    try:
                        conn.execute(text(f"ALTER TABLE user_preferences ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except Exception:
                        pass
            try:
                from datetime import datetime
                now = datetime.utcnow()
                conn.execute(text("UPDATE user_preferences SET created_at = :val WHERE created_at IS NULL"), {"val": now})
                conn.commit()
                conn.execute(text("UPDATE user_preferences SET updated_at = :val WHERE updated_at IS NULL"), {"val": now})
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute(text("UPDATE user_preferences SET channel_order = :val WHERE channel_order IS NULL OR channel_order = ''"), {"val": '["app_push", "sms", "email", "wechat"]'})
                conn.commit()
                conn.execute(text("UPDATE user_preferences SET enabled_channels = :val WHERE enabled_channels IS NULL OR enabled_channels = ''"), {"val": '["sms", "email", "app_push", "wechat"]'})
                conn.commit()
                result = conn.execute(text("SELECT id, channel_order, enabled_channels FROM user_preferences"))
                for row in result:
                    rid, ch_order, ch_enabled = row
                    if ch_order and isinstance(ch_order, str) and not ch_order.startswith('['):
                        new_order = json.dumps([x.strip() for x in ch_order.split(',') if x.strip()])
                        conn.execute(text("UPDATE user_preferences SET channel_order = :val WHERE id = :rid"), {"val": new_order, "rid": rid})
                    if ch_enabled and isinstance(ch_enabled, str) and not ch_enabled.startswith('['):
                        new_enabled = json.dumps([x.strip() for x in ch_enabled.split(',') if x.strip()])
                        conn.execute(text("UPDATE user_preferences SET enabled_channels = :val WHERE id = :rid"), {"val": new_enabled, "rid": rid})
                conn.commit()
            except Exception:
                pass

        if "daily_limit_counters" in inspector.get_table_names():
            existing_columns = [col["name"] for col in inspector.get_columns("daily_limit_counters")]
            counter_columns = [
                ("created_at", "DATETIME", None, None),
                ("updated_at", "DATETIME", None, None),
            ]
            for col_name, col_type, sql_default, py_default in counter_columns:
                if col_name not in existing_columns:
                    try:
                        conn.execute(text(f"ALTER TABLE daily_limit_counters ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except Exception:
                        pass
            try:
                from datetime import datetime
                now = datetime.utcnow()
                conn.execute(text("UPDATE daily_limit_counters SET created_at = :val WHERE created_at IS NULL"), {"val": now})
                conn.commit()
                conn.execute(text("UPDATE daily_limit_counters SET updated_at = :val WHERE updated_at IS NULL"), {"val": now})
                conn.commit()
            except Exception:
                pass
            existing_indexes = [idx["name"] for idx in inspector.get_indexes("daily_limit_counters")]
            if "idx_user_date" not in existing_indexes:
                try:
                    conn.execute(text("CREATE INDEX idx_user_date ON daily_limit_counters (user_id, date)"))
                    conn.commit()
                except Exception:
                    pass

        if "retry_queue" in inspector.get_table_names():
            existing_columns = [col["name"] for col in inspector.get_columns("retry_queue")]
            if "created_at" not in existing_columns:
                try:
                    conn.execute(text("ALTER TABLE retry_queue ADD COLUMN created_at DATETIME"))
                    conn.commit()
                except Exception:
                    pass
            try:
                from datetime import datetime
                now = datetime.utcnow()
                conn.execute(text("UPDATE retry_queue SET created_at = :val WHERE created_at IS NULL"), {"val": now})
                conn.commit()
            except Exception:
                pass

        if "callback_records" not in inspector.get_table_names():
            try:
                conn.execute(text("""
                    CREATE TABLE callback_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id VARCHAR(64),
                        user_id VARCHAR(64),
                        channel VARCHAR(32),
                        status VARCHAR(32),
                        error_message TEXT,
                        callback_url VARCHAR(512),
                        callback_status VARCHAR(32) DEFAULT 'pending',
                        callback_retry_count INTEGER DEFAULT 0,
                        max_callback_retries INTEGER DEFAULT 3,
                        next_callback_time DATETIME,
                        callback_response TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text("CREATE INDEX ix_callback_records_message_id ON callback_records (message_id)"))
                conn.execute(text("CREATE INDEX ix_callback_records_user_id ON callback_records (user_id)"))
                conn.commit()
            except Exception:
                pass
