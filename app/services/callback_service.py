import json
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.message import CallbackRecord


class CallbackService:
    def __init__(self):
        self.scheduler: Optional[BackgroundScheduler] = None

    def schedule_callback(
        self,
        db: Session,
        message_id: str,
        user_id: str,
        channel: str,
        status: str,
        error_message: str,
        callback_url: str,
    ) -> None:
        record = CallbackRecord(
            message_id=message_id,
            user_id=user_id,
            channel=channel,
            status=status,
            error_message=error_message,
            callback_url=callback_url,
            callback_status="pending",
            callback_retry_count=0,
            max_callback_retries=settings.max_callback_retries,
            next_callback_time=datetime.utcnow(),
        )
        db.add(record)
        db.commit()

    def process_pending_callbacks(self) -> None:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            pending = (
                db.query(CallbackRecord)
                .filter(
                    CallbackRecord.callback_status == "pending",
                    CallbackRecord.next_callback_time <= now,
                )
                .all()
            )
            for record in pending:
                self.execute_callback(db, record)
        finally:
            db.close()

    def execute_callback(self, db: Session, record: CallbackRecord) -> bool:
        payload = json.dumps({
            "message_id": record.message_id,
            "user_id": record.user_id,
            "channel": record.channel,
            "status": record.status,
            "error_message": record.error_message,
            "timestamp": datetime.utcnow().isoformat(),
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                record.callback_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    record.callback_status = "success"
                    record.updated_at = datetime.utcnow()
                    db.commit()
                    return True
        except Exception:
            pass

        record.callback_retry_count += 1
        if record.callback_retry_count < record.max_callback_retries:
            record.next_callback_time = datetime.utcnow() + timedelta(
                minutes=settings.callback_retry_delay_minutes * record.callback_retry_count
            )
        else:
            record.callback_status = "failed"
        record.updated_at = datetime.utcnow()
        db.commit()
        return False

    def start(self):
        self.scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
        self.scheduler.add_job(
            self.process_pending_callbacks,
            trigger=IntervalTrigger(seconds=30),
            id="callback_processor",
            replace_existing=True,
        )
        self.scheduler.start()

    def stop(self):
        if self.scheduler:
            self.scheduler.shutdown()


callback_service = CallbackService()
