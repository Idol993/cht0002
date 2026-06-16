from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas.message import (
    ChannelConfigOut,
    UpdateChannelConfigRequest,
    UserPreferenceOut,
    UpdateUserPreferenceRequest,
)
from app.models.message import ChannelConfig
from app.services.user_preference import UserPreferenceService
from app.channels.manager import channel_manager
from app.metrics import message_metrics
from app.config import settings

router = APIRouter(prefix="/api/v1/admin", tags=["管理"])


@router.get("/channels", response_model=List[ChannelConfigOut], summary="获取所有通道配置")
async def list_channel_configs(db: Session = Depends(get_db)):
    """
    获取所有通道的配置信息，包括开关状态和限频规则
    """
    configs = db.query(ChannelConfig).all()
    config_map = {c.channel: c for c in configs}

    all_channels = channel_manager.get_all_channels()
    result = []

    default_limits = {
        "sms": settings.default_sms_daily_limit,
        "email": settings.default_email_daily_limit,
        "app_push": settings.default_app_push_daily_limit,
        "wechat": settings.default_wechat_daily_limit,
    }

    for ch_name in all_channels.keys():
        if ch_name in config_map:
            result.append(ChannelConfigOut.model_validate(config_map[ch_name]))
        else:
            new_config = ChannelConfig(
                channel=ch_name,
                enabled=True,
                daily_limit=default_limits.get(ch_name, 100),
                priority_weight=10,
                retry_count=3,
            )
            db.add(new_config)
            db.commit()
            db.refresh(new_config)
            result.append(ChannelConfigOut.model_validate(new_config))
        message_metrics.set_channel_status(
            ch_name,
            config_map[ch_name].enabled if ch_name in config_map else True,
        )

    return result


@router.put("/channels/{channel}", response_model=ChannelConfigOut, summary="更新通道配置")
async def update_channel_config(
    channel: str,
    request: UpdateChannelConfigRequest,
    db: Session = Depends(get_db),
):
    """
    动态开关通道、调整限频规则

    - **enabled**: 是否启用通道
    - **daily_limit**: 日发送量上限
    - **priority_weight**: 优先级权重
    - **retry_count**: 重试次数
    """
    if channel not in channel_manager.get_all_channels():
        raise HTTPException(status_code=404, detail=f"通道 {channel} 不存在")

    config = db.query(ChannelConfig).filter(ChannelConfig.channel == channel).first()

    if not config:
        config = ChannelConfig(
            channel=channel,
            enabled=True,
            daily_limit=100,
            priority_weight=10,
            retry_count=3,
        )
        db.add(config)

    if request.enabled is not None:
        config.enabled = request.enabled
        message_metrics.set_channel_status(channel, request.enabled)
    if request.daily_limit is not None:
        config.daily_limit = request.daily_limit
    if request.priority_weight is not None:
        config.priority_weight = request.priority_weight
    if request.retry_count is not None:
        config.retry_count = request.retry_count

    db.commit()
    db.refresh(config)
    return ChannelConfigOut.model_validate(config)


@router.get("/users/{user_id}/preference", response_model=UserPreferenceOut, summary="获取用户偏好")
async def get_user_preference(
    user_id: str,
    db: Session = Depends(get_db),
):
    service = UserPreferenceService(db)
    pref = service.get_preference(user_id)
    return UserPreferenceOut(
        user_id=pref.user_id,
        channel_order=pref.channel_order,
        enabled_channels=pref.enabled_channels,
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        notify_email=pref.notify_email,
        notify_phone=pref.notify_phone,
        notify_wechat_openid=pref.notify_wechat_openid,
        notify_app_token=pref.notify_app_token,
    )


@router.put("/users/{user_id}/preference", response_model=UserPreferenceOut, summary="更新用户偏好")
async def update_user_preference(
    user_id: str,
    request: UpdateUserPreferenceRequest,
    db: Session = Depends(get_db),
):
    """
    更新用户的消息偏好设置

    - **channel_order**: 通道优先级顺序
    - **enabled_channels**: 启用的通道列表
    - **quiet_hours_start/end**: 免打扰时段
    - **notify_***: 各通道的联系方式
    """
    service = UserPreferenceService(db)
    pref = service.update_preference(
        user_id=user_id,
        channel_order=request.channel_order,
        enabled_channels=request.enabled_channels,
        quiet_hours_start=request.quiet_hours_start,
        quiet_hours_end=request.quiet_hours_end,
        notify_email=request.notify_email,
        notify_phone=request.notify_phone,
        notify_wechat_openid=request.notify_wechat_openid,
        notify_app_token=request.notify_app_token,
    )
    return UserPreferenceOut(
        user_id=pref.user_id,
        channel_order=pref.channel_order,
        enabled_channels=pref.enabled_channels,
        quiet_hours_start=pref.quiet_hours_start,
        quiet_hours_end=pref.quiet_hours_end,
        notify_email=pref.notify_email,
        notify_phone=pref.notify_phone,
        notify_wechat_openid=pref.notify_wechat_openid,
        notify_app_token=pref.notify_app_token,
    )
