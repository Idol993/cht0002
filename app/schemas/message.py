from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ChannelType(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    APP_PUSH = "app_push"
    WECHAT = "wechat"


class MessagePriority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    MARKETING = "marketing"


class MessageStatus(str, Enum):
    PENDING = "pending"
    SENDING = "sending"
    SUCCESS = "success"
    FAILED = "failed"
    QUEUED = "queued"
    RATE_LIMITED = "rate_limited"
    RETRYING = "retrying"


class SendMessageRequest(BaseModel):
    user_id: str = Field(..., description="用户ID")
    content: str = Field(..., description="消息内容")
    priority: MessagePriority = Field(MessagePriority.NORMAL, description="消息优先级")
    title: Optional[str] = Field(None, description="消息标题（邮件/App推送使用）")
    template_id: Optional[str] = Field(None, description="模板ID（微信模板消息使用）")
    template_data: Optional[Dict[str, Any]] = Field(None, description="模板数据")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="附加元数据")


class SendMessageResponse(BaseModel):
    message_id: str
    status: MessageStatus
    channel: Optional[str] = None
    retry_after_seconds: Optional[int] = None
    message: str


class MessageRecordOut(BaseModel):
    id: int
    message_id: str
    user_id: str
    content: str
    priority: str
    channel: Optional[str]
    status: str
    send_time: Optional[datetime]
    delivered_time: Optional[datetime]
    duration_ms: Optional[float]
    retry_count: int
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    total: int
    items: List[MessageRecordOut]


class ChannelStats(BaseModel):
    channel: str
    total_count: int
    success_count: int
    failed_count: int
    delivery_rate: float
    avg_duration_ms: float
    date: Optional[str] = None


class DailyTrendItem(BaseModel):
    date: str
    total: int
    success: int
    failed: int


class ChannelStatsResponse(BaseModel):
    channels: List[ChannelStats]


class DailyTrendResponse(BaseModel):
    trends: List[DailyTrendItem]
    channel: Optional[str] = None


class ChannelConfigOut(BaseModel):
    channel: str
    enabled: bool
    daily_limit: int
    priority_weight: int
    retry_count: int

    class Config:
        from_attributes = True


class UpdateChannelConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    daily_limit: Optional[int] = Field(None, ge=1)
    priority_weight: Optional[int] = Field(None, ge=1, le=100)
    retry_count: Optional[int] = Field(None, ge=0, le=10)


class UserPreferenceOut(BaseModel):
    user_id: str
    channel_order: List[str]
    enabled_channels: List[str]
    quiet_hours_start: Optional[str]
    quiet_hours_end: Optional[str]
    notify_email: Optional[str]
    notify_phone: Optional[str]
    notify_wechat_openid: Optional[str]
    notify_app_token: Optional[str]


class UpdateUserPreferenceRequest(BaseModel):
    channel_order: Optional[List[str]] = None
    enabled_channels: Optional[List[str]] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    notify_email: Optional[str] = None
    notify_phone: Optional[str] = None
    notify_wechat_openid: Optional[str] = None
    notify_app_token: Optional[str] = None


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    channels: Dict[str, bool]
