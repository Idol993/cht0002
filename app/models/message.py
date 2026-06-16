from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean, JSON, Index
from datetime import datetime
from app.database import Base
import enum


class ChannelType(str, enum.Enum):
    SMS = "sms"
    EMAIL = "email"
    APP_PUSH = "app_push"
    WECHAT = "wechat"


class MessagePriority(str, enum.Enum):
    HIGH = "high"
    NORMAL = "normal"
    MARKETING = "marketing"


class MessageStatus(str, enum.Enum):
    PENDING = "pending"
    SENDING = "sending"
    SUCCESS = "success"
    FAILED = "failed"
    QUEUED = "queued"
    RATE_LIMITED = "rate_limited"
    RETRYING = "retrying"


class MessageRecord(Base):
    __tablename__ = "message_records"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(64), unique=True, index=True)
    user_id = Column(String(64), index=True)
    content = Column(Text)
    priority = Column(String(32), index=True)
    channel = Column(String(32), index=True)
    status = Column(String(32), index=True, default=MessageStatus.PENDING.value)
    send_time = Column(DateTime, index=True)
    delivered_time = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    extra_data = Column(JSON, default={})
    biz_msg_id = Column(String(128), unique=True, index=True, nullable=True)
    callback_url = Column(String(512), nullable=True)
    first_send_time = Column(DateTime, nullable=True)
    error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_user_time", "user_id", "send_time"),
        Index("idx_channel_time", "channel", "send_time"),
        Index("idx_status_time", "status", "send_time"),
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(64), unique=True, index=True)
    channel_order = Column(JSON, default=["app_push", "sms", "email", "wechat"])
    enabled_channels = Column(JSON, default=["sms", "email", "app_push", "wechat"])
    quiet_hours_start = Column(String(5), nullable=True)
    quiet_hours_end = Column(String(5), nullable=True)
    notify_email = Column(String(255), nullable=True)
    notify_phone = Column(String(32), nullable=True)
    notify_wechat_openid = Column(String(128), nullable=True)
    notify_app_token = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CallbackRecord(Base):
    __tablename__ = "callback_records"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)
    channel = Column(String(32))
    status = Column(String(32))
    error_message = Column(Text, nullable=True)
    callback_url = Column(String(512))
    callback_status = Column(String(32), default="pending")
    callback_retry_count = Column(Integer, default=0)
    max_callback_retries = Column(Integer, default=3)
    next_callback_time = Column(DateTime, nullable=True)
    callback_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChannelConfig(Base):
    __tablename__ = "channel_configs"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String(32), unique=True, index=True)
    enabled = Column(Boolean, default=True)
    daily_limit = Column(Integer, default=1000)
    priority_weight = Column(Integer, default=10)
    retry_count = Column(Integer, default=3)
    config_data = Column(JSON, default={})
    circuit_breaker_threshold = Column(Integer, default=5)
    circuit_breaker_recovery_minutes = Column(Integer, default=10)
    circuit_breaker_active = Column(Boolean, default=False)
    circuit_breaker_until = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyLimitCounter(Base):
    __tablename__ = "daily_limit_counters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(64), index=True)
    channel = Column(String(32), index=True)
    date = Column(String(10), index=True)
    count = Column(Integer, default=0)
    marketing_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_user_channel_date", "user_id", "channel", "date", unique=True),
        Index("idx_user_date", "user_id", "date"),
    )


class RetryQueue(Base):
    __tablename__ = "retry_queue"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(64), unique=True, index=True)
    user_id = Column(String(64), index=True)
    content = Column(Text)
    priority = Column(String(32))
    channels_tried = Column(JSON, default=[])
    next_retry_time = Column(DateTime, index=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    status = Column(String(32), default="pending")
    last_error = Column(Text, nullable=True)
    extra_data = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
