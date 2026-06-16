from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models.message import UserPreference
from app.channels.manager import channel_manager


class UserPreferenceService:
    def __init__(self, db: Session):
        self.db = db

    def get_preference(self, user_id: str) -> UserPreference:
        pref = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == user_id)
            .first()
        )
        if not pref:
            pref = self._create_default_preference(user_id)
        return pref

    def _create_default_preference(self, user_id: str) -> UserPreference:
        pref = UserPreference(
            user_id=user_id,
            channel_order=["app_push", "sms", "email", "wechat"],
            enabled_channels=["sms", "email", "app_push", "wechat"],
        )
        self.db.add(pref)
        self.db.commit()
        self.db.refresh(pref)
        return pref

    def update_preference(
        self,
        user_id: str,
        channel_order: Optional[List[str]] = None,
        enabled_channels: Optional[List[str]] = None,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
        notify_email: Optional[str] = None,
        notify_phone: Optional[str] = None,
        notify_wechat_openid: Optional[str] = None,
        notify_app_token: Optional[str] = None,
    ) -> UserPreference:
        pref = self.get_preference(user_id)

        if channel_order is not None:
            pref.channel_order = channel_order
        if enabled_channels is not None:
            pref.enabled_channels = enabled_channels
        if quiet_hours_start is not None:
            pref.quiet_hours_start = quiet_hours_start
        if quiet_hours_end is not None:
            pref.quiet_hours_end = quiet_hours_end
        if notify_email is not None:
            pref.notify_email = notify_email
        if notify_phone is not None:
            pref.notify_phone = notify_phone
        if notify_wechat_openid is not None:
            pref.notify_wechat_openid = notify_wechat_openid
        if notify_app_token is not None:
            pref.notify_app_token = notify_app_token

        self.db.commit()
        self.db.refresh(pref)
        return pref

    def get_user_channel_info(self, user_id: str) -> Dict[str, Any]:
        pref = self.get_preference(user_id)
        return {
            "notify_email": pref.notify_email,
            "notify_phone": pref.notify_phone,
            "notify_wechat_openid": pref.notify_wechat_openid,
            "notify_app_token": pref.notify_app_token,
        }

    def get_ranked_channels(
        self,
        user_id: str,
        db_channel_filter: Optional[List[str]] = None,
    ) -> List[str]:
        pref = self.get_preference(user_id)
        user_enabled = set(pref.enabled_channels)
        channel_order = pref.channel_order

        all_channels = channel_manager.get_all_channels()
        available_types = set(all_channels.keys())

        if db_channel_filter:
            available_types = available_types & set(db_channel_filter)

        ranked = []
        for ch in channel_order:
            if ch in user_enabled and ch in available_types:
                ranked.append(ch)

        for ch in available_types:
            if ch not in ranked and ch in user_enabled:
                ranked.append(ch)

        return ranked
