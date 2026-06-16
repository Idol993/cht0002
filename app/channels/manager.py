from typing import Dict, Optional, List
from datetime import datetime, timedelta
from app.channels.base import BaseChannel
from app.channels.impl import SMSChannel, EmailChannel, AppPushChannel, WechatChannel
from app.models.message import ChannelConfig as DBChannelConfig
from app.config import settings
from sqlalchemy.orm import Session


class ChannelManager:
    _instance: Optional["ChannelManager"] = None
    _channels: Dict[str, BaseChannel] = {}
    _circuit_breaker_state: Dict[str, dict] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_channels()
        return cls._instance

    def _init_channels(self):
        self._channels = {
            "sms": SMSChannel(),
            "email": EmailChannel(),
            "app_push": AppPushChannel(),
            "wechat": WechatChannel(),
        }
        self._circuit_breaker_state = {}
        self._load_circuit_breaker_state()

    def _load_circuit_breaker_state(self):
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            configs = db.query(DBChannelConfig).all()
            for cfg in configs:
                self._circuit_breaker_state[cfg.channel] = {
                    "consecutive_failures": cfg.consecutive_failures or 0,
                    "active": cfg.circuit_breaker_active or False,
                    "until": cfg.circuit_breaker_until,
                }
        except Exception:
            pass
        finally:
            db.close()

    def get_channel(self, channel_type: str) -> Optional[BaseChannel]:
        return self._channels.get(channel_type)

    def get_all_channels(self) -> Dict[str, BaseChannel]:
        return self._channels.copy()

    def update_channel_config(self, channel_type: str, config_data: dict):
        channel = self._channels.get(channel_type)
        if channel:
            channel.config.update(config_data)

    def record_channel_success(self, channel: str):
        if channel not in self._circuit_breaker_state:
            self._circuit_breaker_state[channel] = {
                "consecutive_failures": 0,
                "active": False,
                "until": None,
            }
        self._circuit_breaker_state[channel]["consecutive_failures"] = 0
        if self._circuit_breaker_state[channel]["active"]:
            self._circuit_breaker_state[channel]["active"] = False
            self._circuit_breaker_state[channel]["until"] = None

    def record_channel_failure(self, channel: str, db: Session):
        if channel not in self._circuit_breaker_state:
            self._circuit_breaker_state[channel] = {
                "consecutive_failures": 0,
                "active": False,
                "until": None,
            }
        self._circuit_breaker_state[channel]["consecutive_failures"] += 1

        cfg = db.query(DBChannelConfig).filter(DBChannelConfig.channel == channel).first()
        threshold = cfg.circuit_breaker_threshold if cfg and cfg.circuit_breaker_threshold is not None else settings.default_circuit_breaker_threshold
        recovery_minutes = cfg.circuit_breaker_recovery_minutes if cfg and cfg.circuit_breaker_recovery_minutes is not None else settings.default_circuit_breaker_recovery_minutes

        if self._circuit_breaker_state[channel]["consecutive_failures"] >= threshold:
            until = datetime.utcnow() + timedelta(minutes=recovery_minutes)
            self._circuit_breaker_state[channel]["active"] = True
            self._circuit_breaker_state[channel]["until"] = until
        else:
            until = None

        if cfg:
            cfg.consecutive_failures = self._circuit_breaker_state[channel]["consecutive_failures"]
            cfg.circuit_breaker_active = self._circuit_breaker_state[channel]["active"]
            cfg.circuit_breaker_until = until
            db.commit()

    def is_circuit_breaker_active(self, channel: str, db: Session) -> bool:
        state = self._circuit_breaker_state.get(channel)
        if not state:
            state = {"consecutive_failures": 0, "active": False, "until": None}
            self._circuit_breaker_state[channel] = state

        cfg = db.query(DBChannelConfig).filter(DBChannelConfig.channel == channel).first()

        if cfg and cfg.circuit_breaker_active and not state.get("active"):
            state["active"] = True
            state["until"] = cfg.circuit_breaker_until
            state["consecutive_failures"] = cfg.consecutive_failures or 0

        if not state.get("active"):
            return False
        if state.get("until") and datetime.utcnow() < state["until"]:
            return True
        state["active"] = False
        state["until"] = None
        state["consecutive_failures"] = 0
        if cfg:
            cfg.circuit_breaker_active = False
            cfg.circuit_breaker_until = None
            cfg.consecutive_failures = 0
            db.commit()
        return False

    def get_available_channels(
        self,
        db: Session,
        enabled_only: bool = True,
    ) -> List[str]:
        channel_configs = db.query(DBChannelConfig).all()
        config_map = {cc.channel: cc for cc in channel_configs}

        available = []
        for ch_name in self._channels.keys():
            if enabled_only:
                cfg = config_map.get(ch_name)
                if cfg and not cfg.enabled:
                    continue
            if self.is_circuit_breaker_active(ch_name, db):
                continue
            available.append(ch_name)
        return available


channel_manager = ChannelManager()
