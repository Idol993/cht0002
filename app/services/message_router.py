import uuid
import time
from datetime import datetime, timedelta
from typing import Tuple, Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models.message import (
    MessageRecord,
    MessageStatus,
    MessagePriority,
    ChannelConfig,
    RetryQueue,
)
from app.channels.manager import channel_manager
from app.channels.base import ChannelResult
from app.services.rate_limiter import RateLimiter
from app.services.user_preference import UserPreferenceService
from app.services.callback_service import callback_service
from app.config import settings
from app.metrics import message_metrics


class MessageRouter:
    def __init__(self, db: Session):
        self.db = db
        self.rate_limiter = RateLimiter(db)
        self.user_pref_service = UserPreferenceService(db)

    def send_message(
        self,
        user_id: str,
        content: str,
        priority: str,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        biz_msg_id: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> Tuple[str, str, Optional[str], Optional[int], int]:
        if biz_msg_id:
            existing = (
                self.db.query(MessageRecord)
                .filter(MessageRecord.biz_msg_id == biz_msg_id)
                .first()
            )
            if existing:
                status = existing.status
                if status in (MessageStatus.QUEUED.value, MessageStatus.RETRYING.value):
                    http_code = 202
                elif status == MessageStatus.RATE_LIMITED.value:
                    http_code = 429
                elif status == MessageStatus.FAILED.value:
                    http_code = 200
                else:
                    http_code = 200
                return (
                    existing.message_id,
                    existing.status,
                    existing.channel,
                    None,
                    http_code,
                )

        message_id = self._generate_message_id()
        is_marketing = priority == MessagePriority.MARKETING.value
        is_high_priority = priority == MessagePriority.HIGH.value

        channels_tried: List[str] = []

        record = MessageRecord(
            message_id=message_id,
            user_id=user_id,
            content=content,
            priority=priority,
            status=MessageStatus.PENDING.value,
            extra_data=metadata or {},
            send_time=datetime.utcnow(),
            biz_msg_id=biz_msg_id,
            callback_url=callback_url,
            first_send_time=datetime.utcnow(),
        )
        self.db.add(record)
        self.db.commit()

        ranked_channels = self._get_ranked_channels(user_id)
        if not ranked_channels:
            circuit_broken = (
                self.db.query(ChannelConfig)
                .filter(
                    ChannelConfig.enabled == True,
                    ChannelConfig.circuit_breaker_active == True,
                )
                .first()
            )
            if circuit_broken:
                record.status = MessageStatus.FAILED.value
                record.error_code = "CHANNEL_CIRCUIT_BREAKER"
                record.error_message = "所有通道因熔断不可用"
                self.db.commit()
                if callback_url:
                    callback_service.schedule_callback(
                        self.db, message_id, user_id, None,
                        MessageStatus.FAILED.value, record.error_message, callback_url,
                    )
                return message_id, MessageStatus.FAILED.value, None, None, 503
            else:
                record.status = MessageStatus.FAILED.value
                record.error_code = "NO_AVAILABLE_CHANNEL"
                record.error_message = "无可用通道"
                self.db.commit()
                if callback_url:
                    callback_service.schedule_callback(
                        self.db, message_id, user_id, None,
                        MessageStatus.FAILED.value, record.error_message, callback_url,
                    )
                return message_id, MessageStatus.FAILED.value, None, None, 200

        selected_channel = None
        for ch_name in ranked_channels:
            if self.rate_limiter.check_available(user_id, ch_name, is_marketing):
                selected_channel = ch_name
                break

        if not selected_channel:
            if is_high_priority:
                self._queue_for_retry(
                    message_id=message_id,
                    user_id=user_id,
                    content=content,
                    priority=priority,
                    channels_tried=[],
                    title=title,
                    template_id=template_id,
                    template_data=template_data,
                    delay_minutes=1,
                )
                record.status = MessageStatus.QUEUED.value
                record.channel = None
                record.error_code = "RATE_LIMITED"
                self.db.commit()
                if callback_url:
                    callback_service.schedule_callback(
                        self.db, message_id, user_id, None,
                        MessageStatus.QUEUED.value, "高优先级消息限频排队", callback_url,
                    )
                return message_id, MessageStatus.QUEUED.value, None, 60, 202
            else:
                record.status = MessageStatus.RATE_LIMITED.value
                record.error_message = "所有通道均已达日限频"
                record.error_code = "RATE_LIMITED"
                self.db.commit()
                if callback_url:
                    callback_service.schedule_callback(
                        self.db, message_id, user_id, None,
                        MessageStatus.RATE_LIMITED.value, record.error_message, callback_url,
                    )
                return message_id, MessageStatus.RATE_LIMITED.value, None, None, 429

        record.channel = selected_channel
        record.status = MessageStatus.SENDING.value
        self.db.commit()

        result = self._do_send(
            channel_name=selected_channel,
            user_id=user_id,
            content=content,
            title=title,
            template_id=template_id,
            template_data=template_data,
        )

        self.rate_limiter.check_and_consume(user_id, selected_channel, is_marketing)

        record.duration_ms = result.duration_ms
        record.delivered_time = datetime.utcnow() if result.success else None

        message_metrics.observe_duration(selected_channel, result.duration_ms / 1000.0)

        if result.success:
            record.status = MessageStatus.SUCCESS.value
            message_metrics.inc_success(selected_channel)
            channel_manager.record_channel_success(selected_channel)
            self.db.commit()
            if callback_url:
                callback_service.schedule_callback(
                    self.db, message_id, user_id, selected_channel,
                    MessageStatus.SUCCESS.value, None, callback_url,
                )
            return message_id, MessageStatus.SUCCESS.value, selected_channel, None, 200
        else:
            record.status = MessageStatus.FAILED.value
            record.error_message = result.message
            record.error_code = result.error_code or "CHANNEL_ERROR"
            message_metrics.inc_failure(selected_channel)
            channel_manager.record_channel_failure(selected_channel, self.db)

            channels_tried.append(selected_channel)

            if is_high_priority:
                fallback_result, fallback_channel = self._try_fallback_channels(
                    user_id=user_id,
                    content=content,
                    title=title,
                    template_id=template_id,
                    template_data=template_data,
                    priority=priority,
                    channels_tried=channels_tried,
                    is_marketing=is_marketing,
                    record=record,
                    callback_url=callback_url,
                )
                if fallback_result and fallback_result.success:
                    return (
                        message_id,
                        MessageStatus.SUCCESS.value,
                        fallback_channel,
                        None,
                        200,
                    )
                else:
                    self._queue_for_retry(
                        message_id=message_id,
                        user_id=user_id,
                        content=content,
                        priority=priority,
                        channels_tried=channels_tried,
                        title=title,
                        template_id=template_id,
                        template_data=template_data,
                        delay_minutes=0,
                    )
                    record.status = MessageStatus.RETRYING.value
                    self.db.commit()
                    if callback_url:
                        callback_service.schedule_callback(
                            self.db, message_id, user_id, selected_channel,
                            MessageStatus.RETRYING.value, record.error_message, callback_url,
                        )
                    return (
                        message_id,
                        MessageStatus.RETRYING.value,
                        selected_channel,
                        None,
                        202,
                    )
            elif priority == MessagePriority.NORMAL.value:
                self._queue_for_retry(
                    message_id=message_id,
                    user_id=user_id,
                    content=content,
                    priority=priority,
                    channels_tried=channels_tried,
                    title=title,
                    template_id=template_id,
                    template_data=template_data,
                    delay_minutes=settings.normal_retry_delay_minutes,
                )
                record.status = MessageStatus.RETRYING.value
                self.db.commit()
                if callback_url:
                    callback_service.schedule_callback(
                        self.db, message_id, user_id, selected_channel,
                        MessageStatus.RETRYING.value, record.error_message, callback_url,
                    )
                return (
                    message_id,
                    MessageStatus.RETRYING.value,
                    selected_channel,
                    settings.normal_retry_delay_minutes * 60,
                    202,
                )
            else:
                self.db.commit()
                if callback_url:
                    callback_service.schedule_callback(
                        self.db, message_id, user_id, selected_channel,
                        MessageStatus.FAILED.value, record.error_message, callback_url,
                    )
                return (
                    message_id,
                    MessageStatus.FAILED.value,
                    selected_channel,
                    None,
                    200,
                )

    def _try_fallback_channels(
        self,
        user_id: str,
        content: str,
        priority: str,
        channels_tried: List[str],
        is_marketing: bool,
        record: MessageRecord,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        callback_url: Optional[str] = None,
    ) -> Tuple[Optional[ChannelResult], Optional[str]]:
        ranked_channels = self._get_ranked_channels(user_id)

        for ch_name in ranked_channels:
            if ch_name in channels_tried:
                continue
            if not self.rate_limiter.check_available(user_id, ch_name, is_marketing):
                continue

            self.rate_limiter.check_and_consume(user_id, ch_name, is_marketing)

            record.retry_count += 1
            record.channel = ch_name
            self.db.commit()

            result = self._do_send(
                channel_name=ch_name,
                user_id=user_id,
                content=content,
                title=title,
                template_id=template_id,
                template_data=template_data,
            )

            record.duration_ms = (record.duration_ms or 0) + result.duration_ms
            message_metrics.observe_duration(ch_name, result.duration_ms / 1000.0)

            if result.success:
                record.status = MessageStatus.SUCCESS.value
                record.delivered_time = datetime.utcnow()
                record.error_message = None
                message_metrics.inc_success(ch_name)
                channel_manager.record_channel_success(ch_name)
                self.db.commit()
                if callback_url:
                    callback_service.schedule_callback(
                        self.db, record.message_id, user_id, ch_name,
                        MessageStatus.SUCCESS.value, None, callback_url,
                    )
                return result, ch_name
            else:
                message_metrics.inc_failure(ch_name)
                channel_manager.record_channel_failure(ch_name, self.db)
                channels_tried.append(ch_name)
                record.error_message = result.message
                record.error_code = result.error_code or "CHANNEL_ERROR"

        record.status = MessageStatus.FAILED.value
        self.db.commit()
        return None, None

    def _do_send(
        self,
        channel_name: str,
        user_id: str,
        content: str,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
    ) -> ChannelResult:
        channel = channel_manager.get_channel(channel_name)
        if not channel:
            return ChannelResult(success=False, message=f"通道{channel_name}不存在", error_code="CHANNEL_NOT_FOUND")

        user_info = self.user_pref_service.get_user_channel_info(user_id)

        message_metrics.inc_total(channel_name)

        result = channel.send(
            user_id=user_id,
            content=content,
            title=title,
            template_id=template_id,
            template_data=template_data,
            user_info=user_info,
        )
        return result

    def _get_ranked_channels(self, user_id: str) -> List[str]:
        db_enabled = channel_manager.get_available_channels(self.db, enabled_only=True)
        return self.user_pref_service.get_ranked_channels(
            user_id,
            db_channel_filter=db_enabled,
        )

    def _generate_message_id(self) -> str:
        return f"MSG_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    def _queue_for_retry(
        self,
        message_id: str,
        user_id: str,
        content: str,
        priority: str,
        channels_tried: List[str],
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        delay_minutes: int = 5,
    ):
        next_time = datetime.utcnow() + timedelta(minutes=delay_minutes)
        max_retries = 3 if priority == MessagePriority.HIGH.value else 1

        retry_item = RetryQueue(
            message_id=message_id,
            user_id=user_id,
            content=content,
            priority=priority,
            channels_tried=channels_tried,
            next_retry_time=next_time,
            max_retries=max_retries,
            status="pending",
        )
        retry_item.extra_data = {
            "title": title,
            "template_id": template_id,
            "template_data": template_data,
        }
        self.db.add(retry_item)
        self.db.commit()

        msg_record = self.db.query(MessageRecord).filter(MessageRecord.message_id == message_id).first()
        if msg_record:
            msg_record.retry_count = max(msg_record.retry_count or 0, 1)
            self.db.commit()

    def process_retry(self, retry_item: RetryQueue) -> bool:
        from app.services.retry_service import retry_service

        return retry_service.process_single_retry(self.db, retry_item)
