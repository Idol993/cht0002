from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal
from app.models.message import RetryQueue, MessageRecord, MessageStatus, MessagePriority
from app.channels.manager import channel_manager
from app.services.rate_limiter import RateLimiter
from app.services.user_preference import UserPreferenceService
from app.services.callback_service import callback_service
from app.metrics import message_metrics
from app.config import settings


class RetryService:
    def __init__(self):
        self.scheduler: Optional[BackgroundScheduler] = None

    def start(self):
        self.scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
        self.scheduler.add_job(
            self._process_retry_queue,
            trigger=IntervalTrigger(seconds=30),
            id="retry_queue_processor",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._update_retry_queue_metric,
            trigger=IntervalTrigger(minutes=1),
            id="retry_queue_metric_updater",
            replace_existing=True,
        )
        self.scheduler.start()

    def stop(self):
        if self.scheduler:
            self.scheduler.shutdown()

    def _process_retry_queue(self):
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            pending_retries = (
                db.query(RetryQueue)
                .filter(
                    RetryQueue.status == "pending",
                    RetryQueue.next_retry_time <= now,
                )
                .order_by(RetryQueue.next_retry_time.asc())
                .limit(50)
                .all()
            )

            for retry_item in pending_retries:
                self.process_single_retry(db, retry_item)
        finally:
            db.close()

    def process_single_retry(self, db: Session, retry_item: RetryQueue) -> bool:
        retry_item.status = "processing"
        db.commit()

        try:
            user_id = retry_item.user_id
            content = retry_item.content
            priority = retry_item.priority
            channels_tried = retry_item.channels_tried or []
            is_marketing = priority == MessagePriority.MARKETING.value

            extra_data = retry_item.extra_data or {}
            title = extra_data.get("title")
            template_id = extra_data.get("template_id")
            template_data = extra_data.get("template_data")

            rate_limiter = RateLimiter(db)
            user_pref_service = UserPreferenceService(db)

            db_enabled = channel_manager.get_available_channels(db, enabled_only=True)
            ranked_channels = user_pref_service.get_ranked_channels(
                user_id,
                db_channel_filter=db_enabled,
            )

            record = (
                db.query(MessageRecord)
                .filter(MessageRecord.message_id == retry_item.message_id)
                .first()
            )

            success = False
            used_channel = None

            for ch_name in ranked_channels:
                if ch_name in channels_tried:
                    continue
                if not rate_limiter.check_available(user_id, ch_name, is_marketing):
                    continue

                rate_limiter.check_and_consume(user_id, ch_name, is_marketing)

                channel = channel_manager.get_channel(ch_name)
                if not channel:
                    continue

                user_info = user_pref_service.get_user_channel_info(user_id)
                message_metrics.inc_total(ch_name, priority)

                import time
                start = time.time()
                result = channel.send(
                    user_id=user_id,
                    content=content,
                    title=title,
                    template_id=template_id,
                    template_data=template_data,
                    user_info=user_info,
                )
                duration = time.time() - start
                message_metrics.observe_duration(ch_name, duration)

                if result.success:
                    success = True
                    used_channel = ch_name
                    message_metrics.inc_success(ch_name, priority)
                    channel_manager.record_channel_success(ch_name)
                    if record:
                        record.status = MessageStatus.SUCCESS.value
                        record.channel = ch_name
                        record.duration_ms = (record.duration_ms or 0) + result.duration_ms
                        record.delivered_time = datetime.utcnow()
                        record.retry_count = (record.retry_count or 0) + 1
                        record.error_message = None
                    break
                else:
                    message_metrics.inc_failure(ch_name, priority)
                    channel_manager.record_channel_failure(ch_name, db)
                    channels_tried.append(ch_name)

            if success:
                retry_item.status = "success"
                db.commit()
                if record and record.callback_url:
                    callback_service.schedule_callback(
                        db,
                        record.message_id,
                        record.user_id,
                        used_channel,
                        MessageStatus.SUCCESS.value,
                        None,
                        record.callback_url,
                    )
                return True
            else:
                retry_item.retry_count += 1
                retry_item.channels_tried = channels_tried

                if retry_item.retry_count >= retry_item.max_retries:
                    retry_item.status = "failed"
                    retry_item.last_error = "已达最大重试次数"
                    if record:
                        record.status = MessageStatus.FAILED.value
                        record.error_message = "重试全部失败"
                        record.retry_count = (record.retry_count or 0) + 1
                    db.commit()
                    if record and record.callback_url:
                        callback_service.schedule_callback(
                            db,
                            record.message_id,
                            record.user_id,
                            record.channel,
                            MessageStatus.FAILED.value,
                            record.error_message,
                            record.callback_url,
                        )
                    return False
                else:
                    retry_item.next_retry_time = datetime.utcnow() + timedelta(
                        minutes=5 * retry_item.retry_count
                    )
                    retry_item.status = "pending"
                    db.commit()
                    return False

        except Exception as e:
            retry_item.status = "failed"
            retry_item.last_error = str(e)
            db.commit()
            if record and record.callback_url:
                callback_service.schedule_callback(
                    db,
                    record.message_id,
                    record.user_id,
                    record.channel,
                    MessageStatus.FAILED.value,
                    str(e),
                    record.callback_url,
                )
            return False

    def _update_retry_queue_metric(self):
        db = SessionLocal()
        try:
            count = db.query(RetryQueue).filter(RetryQueue.status == "pending").count()
            message_metrics.set_retry_queue_size(count)
        finally:
            db.close()


retry_service = RetryService()
