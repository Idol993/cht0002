from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.message import DailyLimitCounter, ChannelConfig
from app.config import settings
from typing import Tuple


_DEFAULT_CHANNEL_LIMITS = {
    "sms": settings.default_sms_daily_limit,
    "email": settings.default_email_daily_limit,
    "app_push": settings.default_app_push_daily_limit,
    "wechat": settings.default_wechat_daily_limit,
}


class RateLimiter:
    def __init__(self, db: Session):
        self.db = db

    def _get_channel_limit(self, channel: str) -> int:
        config = self.db.query(ChannelConfig).filter(ChannelConfig.channel == channel).first()
        if config and config.daily_limit is not None:
            return config.daily_limit
        return _DEFAULT_CHANNEL_LIMITS.get(channel, 10)

    def _get_today_str(self) -> str:
        return date.today().strftime("%Y-%m-%d")

    def _get_or_create_counter(self, user_id: str, channel: str) -> DailyLimitCounter:
        today = self._get_today_str()
        counter = (
            self.db.query(DailyLimitCounter)
            .filter(
                DailyLimitCounter.user_id == user_id,
                DailyLimitCounter.channel == channel,
                DailyLimitCounter.date == today,
            )
            .first()
        )
        if not counter:
            counter = DailyLimitCounter(
                user_id=user_id,
                channel=channel,
                date=today,
                count=0,
                marketing_count=0,
            )
            self.db.add(counter)
            self.db.commit()
            self.db.refresh(counter)
        return counter

    def check_marketing_global_limit(self, user_id: str) -> Tuple[bool, str]:
        today = self._get_today_str()
        total_marketing = (
            self.db.query(func.coalesce(func.sum(DailyLimitCounter.marketing_count), 0))
            .filter(
                DailyLimitCounter.user_id == user_id,
                DailyLimitCounter.date == today,
            )
            .scalar()
        )
        if total_marketing >= settings.default_marketing_daily_limit:
            return False, f"营销类消息全局日发送量已达上限{settings.default_marketing_daily_limit}条"
        return True, ""

    def check_and_consume(
        self,
        user_id: str,
        channel: str,
        is_marketing: bool = False,
    ) -> Tuple[bool, str]:
        if is_marketing:
            allowed, msg = self.check_marketing_global_limit(user_id)
            if not allowed:
                return False, msg

        counter = self._get_or_create_counter(user_id, channel)

        channel_limit = self._get_channel_limit(channel)
        if counter.count >= channel_limit:
            return False, f"通道{channel}日发送量已达上限{channel_limit}条"

        if is_marketing:
            if counter.marketing_count >= settings.default_marketing_daily_limit:
                return False, f"营销类消息日发送量已达上限{settings.default_marketing_daily_limit}条"
            counter.marketing_count += 1

        counter.count += 1
        self.db.commit()
        return True, ""

    def check_available(
        self,
        user_id: str,
        channel: str,
        is_marketing: bool = False,
    ) -> bool:
        if is_marketing:
            allowed, _ = self.check_marketing_global_limit(user_id)
            if not allowed:
                return False

        counter = self._get_or_create_counter(user_id, channel)

        channel_limit = self._get_channel_limit(channel)
        if counter.count >= channel_limit:
            return False

        if is_marketing and counter.marketing_count >= settings.default_marketing_daily_limit:
            return False

        return True

    def get_remaining(self, user_id: str, channel: str) -> Tuple[int, int]:
        counter = self._get_or_create_counter(user_id, channel)
        channel_limit = self._get_channel_limit(channel)
        remaining = channel_limit - counter.count
        marketing_remaining = settings.default_marketing_daily_limit - counter.marketing_count
        return max(0, remaining), max(0, marketing_remaining)
