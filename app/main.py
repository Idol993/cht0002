from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app

from app.config import settings
from app.database import Base, engine
from app.api.v1.message import router as message_router
from app.api.v1.stats import router as stats_router
from app.api.v1.admin import router as admin_router
from app.api.v1.health import router as health_router
from app.services.retry_service import retry_service
from app.channels.manager import channel_manager
from app.metrics import message_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _init_channel_configs()
    retry_service.start()
    yield
    retry_service.stop()


def _init_channel_configs():
    from app.database import SessionLocal
    from app.models.message import ChannelConfig

    db = SessionLocal()
    try:
        default_limits = {
            "sms": settings.default_sms_daily_limit,
            "email": settings.default_email_daily_limit,
            "app_push": settings.default_app_push_daily_limit,
            "wechat": settings.default_wechat_daily_limit,
        }

        for ch_name in channel_manager.get_all_channels().keys():
            config = db.query(ChannelConfig).filter(ChannelConfig.channel == ch_name).first()
            if not config:
                config = ChannelConfig(
                    channel=ch_name,
                    enabled=True,
                    daily_limit=default_limits.get(ch_name, 100),
                    priority_weight=10,
                    retry_count=3,
                )
                db.add(config)
            message_metrics.set_channel_status(ch_name, config.enabled if config else True)
        db.commit()
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="""
        多通道消息聚合推送API服务

        ## 功能特性
        - **统一发送接口**: 上游业务系统统一调用一个接口发消息
        - **智能路由**: 根据用户偏好和通道状态自动选最优通道
        - **多通道支持**: 短信、邮件、App推送、微信模板消息
        - **差异化重试**: 高优先级立即重试，普通延迟5分钟，营销不重试
        - **限频控制**: 每个用户每种通道有日限频
        - **消息记录**: 全部消息记录落库，支持多维度查询
        - **统计分析**: 送达率、平均延迟、日发送量趋势
        - **管理功能**: 动态开关通道、调整限频规则
        - **可观测性**: 健康检查、Prometheus指标、OpenAPI文档
        """,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={
            "name": "消息网关团队",
            "email": "msg-gateway@example.com",
        },
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(message_router)
    app.include_router(stats_router)
    app.include_router(admin_router)
    app.include_router(health_router)

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


app = create_app()
