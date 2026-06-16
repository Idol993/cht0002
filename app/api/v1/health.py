from fastapi import APIRouter, Depends
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.message import HealthCheckResponse, ChannelHealthDetail
from app.channels.manager import channel_manager
from app.config import settings
from app.models.message import ChannelConfig

router = APIRouter(tags=["系统"])


@router.get("/health", response_model=HealthCheckResponse, summary="健康检查")
async def health_check(db: Session = Depends(get_db)):
    """
    服务健康检查端点，返回服务状态、版本和各通道状态
    """
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_healthy = True
    except Exception:
        db_healthy = False

    channel_statuses = {}
    configs = db.query(ChannelConfig).all()
    config_map = {c.channel: c for c in configs}

    for ch_name in channel_manager.get_all_channels().keys():
        channel_manager.is_circuit_breaker_active(ch_name, db)
        cfg = config_map.get(ch_name)
        if cfg:
            channel_statuses[ch_name] = ChannelHealthDetail(
                enabled=cfg.enabled,
                circuit_breaker_active=cfg.circuit_breaker_active or False,
                circuit_breaker_until=cfg.circuit_breaker_until,
                consecutive_failures=cfg.consecutive_failures or 0,
            )
        else:
            channel_statuses[ch_name] = ChannelHealthDetail(
                enabled=True,
                circuit_breaker_active=False,
                circuit_breaker_until=None,
                consecutive_failures=0,
            )

    return HealthCheckResponse(
        status="healthy" if db_healthy else "degraded",
        version=settings.app_version,
        timestamp=datetime.utcnow(),
        channels={k: v.model_dump() for k, v in channel_statuses.items()},
    )
