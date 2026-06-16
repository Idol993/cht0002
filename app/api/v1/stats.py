from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timedelta, date

from app.database import get_db
from app.schemas.message import (
    ChannelStatsResponse,
    ChannelStats,
    DailyTrendResponse,
    DailyTrendItem,
)
from app.models.message import MessageRecord, MessageStatus
from app.channels.manager import channel_manager

router = APIRouter(prefix="/api/v1/stats", tags=["统计"])


def _safe_int(val) -> int:
    if val is None:
        return 0
    return int(val)


def _safe_float(val) -> float:
    if val is None:
        return 0.0
    return float(val)


@router.get("/channels", response_model=ChannelStatsResponse, summary="各通道统计")
async def get_channel_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    返回各通道的送达率、平均延迟和发送量
    """
    all_channels = list(channel_manager.get_all_channels().keys())

    query = db.query(MessageRecord).filter(MessageRecord.channel.isnot(None))

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(MessageRecord.send_time >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(MessageRecord.send_time < end_dt)
        except ValueError:
            pass

    records = query.all()

    stats_map = {}
    for ch in all_channels:
        stats_map[ch] = {
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "total_duration": 0.0,
            "duration_count": 0,
        }

    for rec in records:
        ch = rec.channel
        if ch not in stats_map:
            continue
        stats_map[ch]["total_count"] += 1
        if rec.status == MessageStatus.SUCCESS.value:
            stats_map[ch]["success_count"] += 1
        elif rec.status == MessageStatus.FAILED.value:
            stats_map[ch]["failed_count"] += 1
        if rec.duration_ms is not None:
            stats_map[ch]["total_duration"] += rec.duration_ms
            stats_map[ch]["duration_count"] += 1

    channels_stats = []
    for ch in all_channels:
        s = stats_map[ch]
        total = s["total_count"]
        success = s["success_count"]
        delivery_rate = (success / total * 100) if total > 0 else 0.0
        avg_duration = (s["total_duration"] / s["duration_count"]) if s["duration_count"] > 0 else 0.0

        channels_stats.append(
            ChannelStats(
                channel=ch,
                total_count=total,
                success_count=success,
                failed_count=s["failed_count"],
                delivery_rate=round(delivery_rate, 2),
                avg_duration_ms=round(avg_duration, 2),
            )
        )

    return ChannelStatsResponse(channels=channels_stats)


@router.get("/daily-trend", response_model=DailyTrendResponse, summary="日发送量趋势")
async def get_daily_trend(
    days: int = Query(7, ge=1, le=30, description="查询最近N天"),
    channel: Optional[str] = Query(None, description="按通道过滤"),
    db: Session = Depends(get_db),
):
    """
    返回最近N天的日发送量趋势
    """
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days - 1)

    query = db.query(MessageRecord).filter(
        MessageRecord.send_time >= datetime.combine(start_date, datetime.min.time()),
        MessageRecord.send_time < datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
    )

    if channel:
        query = query.filter(MessageRecord.channel == channel)

    records = query.all()

    date_map = {}
    for i in range(days):
        d = start_date + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        date_map[date_str] = {"total": 0, "success": 0, "failed": 0}

    for rec in records:
        if rec.send_time:
            date_str = rec.send_time.strftime("%Y-%m-%d")
            if date_str in date_map:
                date_map[date_str]["total"] += 1
                if rec.status == MessageStatus.SUCCESS.value:
                    date_map[date_str]["success"] += 1
                elif rec.status == MessageStatus.FAILED.value:
                    date_map[date_str]["failed"] += 1

    trends = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        data = date_map[date_str]
        trends.append(
            DailyTrendItem(
                date=date_str,
                total=data["total"],
                success=data["success"],
                failed=data["failed"],
            )
        )

    return DailyTrendResponse(
        trends=trends,
        channel=channel,
    )
