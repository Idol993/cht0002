from fastapi import APIRouter, Depends
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.message import HealthCheckResponse
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
        cfg = config_map.get(ch_name)
        channel_statuses[ch_name] = cfg.enabled if cfg else True

    return HealthCheckResponse(
        status="healthy" if db_healthy else "degraded",
        version=settings.app_version,
        timestamp=datetime.utcnow(),
        channels=channel_statuses,
    )
