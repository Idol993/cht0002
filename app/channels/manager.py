from typing import Dict, Optional, List
from app.channels.base import BaseChannel
from app.channels.impl import SMSChannel, EmailChannel, AppPushChannel, WechatChannel
from app.models.message import ChannelConfig as DBChannelConfig
from sqlalchemy.orm import Session


class ChannelManager:
    _instance: Optional["ChannelManager"] = None
    _channels: Dict[str, BaseChannel] = {}

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

    def get_channel(self, channel_type: str) -> Optional[BaseChannel]:
        return self._channels.get(channel_type)

    def get_all_channels(self) -> Dict[str, BaseChannel]:
        return self._channels.copy()

    def update_channel_config(self, channel_type: str, config_data: dict):
        channel = self._channels.get(channel_type)
        if channel:
            channel.config.update(config_data)

    def get_available_channels(
        self,
        db: Session,
        enabled_only: bool = True,
    ) -> List[str]:
        from app.models.message import ChannelConfig

        channel_configs = db.query(ChannelConfig).all()
        config_map = {cc.channel: cc for cc in channel_configs}

        available = []
        for ch_name in self._channels.keys():
            if enabled_only:
                cfg = config_map.get(ch_name)
                if cfg and not cfg.enabled:
                    continue
            available.append(ch_name)
        return available


channel_manager = ChannelManager()
