from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "多通道消息聚合推送服务"
    app_version: str = "1.0.0"
    debug: bool = False

    database_url: str = "sqlite:///./data/message_gateway.db"

    scheduler_timezone: str = "Asia/Shanghai"

    default_sms_daily_limit: int = 5
    default_app_push_daily_limit: int = 20
    default_marketing_daily_limit: int = 1
    default_email_daily_limit: int = 50
    default_wechat_daily_limit: int = 10

    normal_retry_delay_minutes: int = 5
    high_priority_retry_immediate: bool = True

    prometheus_port: int = 9090
    api_port: int = 8000
    api_host: str = "0.0.0.0"


settings = Settings()
