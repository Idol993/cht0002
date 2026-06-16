from app.channels.base import BaseChannel, ChannelResult
from typing import Dict, Any, Optional
import time
import random
import uuid


class SMSChannel(BaseChannel):
    channel_type = "sms"
    channel_name = "短信"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.success_rate = self.config.get("success_rate", 0.95)
        self.min_delay_ms = self.config.get("min_delay_ms", 50)
        self.max_delay_ms = self.config.get("max_delay_ms", 200)

    def send(
        self,
        user_id: str,
        content: str,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        user_info: Optional[Dict[str, Any]] = None,
    ) -> ChannelResult:
        phone = user_info.get("notify_phone") if user_info else None
        if not phone:
            return ChannelResult(
                success=False,
                message="用户手机号未配置",
                error_code="NO_PHONE",
            )

        start_time = time.time()
        time.sleep(random.uniform(self.min_delay_ms / 1000, self.max_delay_ms / 1000))
        duration_ms = (time.time() - start_time) * 1000

        success = random.random() < self.success_rate
        if success:
            return ChannelResult(
                success=True,
                message="发送成功",
                provider_msg_id=f"SMS_{uuid.uuid4().hex[:16].upper()}",
                duration_ms=duration_ms,
            )
        else:
            return ChannelResult(
                success=False,
                message="短信通道发送失败",
                duration_ms=duration_ms,
                error_code="SMS_DELIVERY_FAILED",
            )

    def validate_user_info(self, user_info: Optional[Dict[str, Any]]) -> bool:
        if not user_info:
            return False
        return bool(user_info.get("notify_phone"))


class EmailChannel(BaseChannel):
    channel_type = "email"
    channel_name = "邮件"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.success_rate = self.config.get("success_rate", 0.97)
        self.min_delay_ms = self.config.get("min_delay_ms", 100)
        self.max_delay_ms = self.config.get("max_delay_ms", 500)

    def send(
        self,
        user_id: str,
        content: str,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        user_info: Optional[Dict[str, Any]] = None,
    ) -> ChannelResult:
        email = user_info.get("notify_email") if user_info else None
        if not email:
            return ChannelResult(
                success=False,
                message="用户邮箱未配置",
                error_code="NO_EMAIL",
            )

        start_time = time.time()
        time.sleep(random.uniform(self.min_delay_ms / 1000, self.max_delay_ms / 1000))
        duration_ms = (time.time() - start_time) * 1000

        success = random.random() < self.success_rate
        if success:
            return ChannelResult(
                success=True,
                message="发送成功",
                provider_msg_id=f"EMAIL_{uuid.uuid4().hex[:16].upper()}",
                duration_ms=duration_ms,
            )
        else:
            return ChannelResult(
                success=False,
                message="邮件发送失败",
                duration_ms=duration_ms,
                error_code="EMAIL_DELIVERY_FAILED",
            )

    def validate_user_info(self, user_info: Optional[Dict[str, Any]]) -> bool:
        if not user_info:
            return False
        return bool(user_info.get("notify_email"))


class AppPushChannel(BaseChannel):
    channel_type = "app_push"
    channel_name = "App推送"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.success_rate = self.config.get("success_rate", 0.92)
        self.min_delay_ms = self.config.get("min_delay_ms", 20)
        self.max_delay_ms = self.config.get("max_delay_ms", 100)

    def send(
        self,
        user_id: str,
        content: str,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        user_info: Optional[Dict[str, Any]] = None,
    ) -> ChannelResult:
        app_token = user_info.get("notify_app_token") if user_info else None
        if not app_token:
            return ChannelResult(
                success=False,
                message="用户App推送Token未配置",
                error_code="NO_APP_TOKEN",
            )

        start_time = time.time()
        time.sleep(random.uniform(self.min_delay_ms / 1000, self.max_delay_ms / 1000))
        duration_ms = (time.time() - start_time) * 1000

        success = random.random() < self.success_rate
        if success:
            return ChannelResult(
                success=True,
                message="发送成功",
                provider_msg_id=f"APP_{uuid.uuid4().hex[:16].upper()}",
                duration_ms=duration_ms,
            )
        else:
            return ChannelResult(
                success=False,
                message="App推送失败",
                duration_ms=duration_ms,
                error_code="APP_PUSH_FAILED",
            )

    def validate_user_info(self, user_info: Optional[Dict[str, Any]]) -> bool:
        if not user_info:
            return False
        return bool(user_info.get("notify_app_token"))


class WechatChannel(BaseChannel):
    channel_type = "wechat"
    channel_name = "微信模板消息"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.success_rate = self.config.get("success_rate", 0.94)
        self.min_delay_ms = self.config.get("min_delay_ms", 80)
        self.max_delay_ms = self.config.get("max_delay_ms", 300)

    def send(
        self,
        user_id: str,
        content: str,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        user_info: Optional[Dict[str, Any]] = None,
    ) -> ChannelResult:
        openid = user_info.get("notify_wechat_openid") if user_info else None
        if not openid:
            return ChannelResult(
                success=False,
                message="用户微信OpenID未配置",
                error_code="NO_WECHAT_OPENID",
            )

        if not template_id:
            return ChannelResult(
                success=False,
                message="微信模板消息需要template_id",
                error_code="NO_TEMPLATE_ID",
            )

        start_time = time.time()
        time.sleep(random.uniform(self.min_delay_ms / 1000, self.max_delay_ms / 1000))
        duration_ms = (time.time() - start_time) * 1000

        success = random.random() < self.success_rate
        if success:
            return ChannelResult(
                success=True,
                message="发送成功",
                provider_msg_id=f"WX_{uuid.uuid4().hex[:16].upper()}",
                duration_ms=duration_ms,
            )
        else:
            return ChannelResult(
                success=False,
                message="微信模板消息发送失败",
                duration_ms=duration_ms,
                error_code="WECHAT_DELIVERY_FAILED",
            )

    def validate_user_info(self, user_info: Optional[Dict[str, Any]]) -> bool:
        if not user_info:
            return False
        return bool(user_info.get("notify_wechat_openid"))
