from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime, timedelta, date

from pydantic import BaseModel

from app.database import get_db
from app.schemas.message import (
    ChannelStatsResponse,
    ChannelStats,
    DailyTrendResponse,
    DailyTrendItem,
    PriorityStatsResponse,
    PriorityStats,
    FailureReasonStatsResponse,
    FailureReasonStats,
    RetryStats,
    HighPriorityLatencyStats,
    NormalRetrySuccessStats,
)
from app.models.message import MessageRecord, MessageStatus
from app.channels.manager import channel_manager

router = APIRouter(prefix="/api/v1/stats", tags=["统计"])


class RetryEffectivenessResponse(BaseModel):
    retry_breakdown: List[RetryStats]
    high_priority_latency: HighPriorityLatencyStats
    normal_retry_success: NormalRetrySuccessStats


def _safe_int(val) -> int:
    if val is None:
        return 0
    return int(val)


def _safe_float(val) -> float:
    if val is None:
        return 0.0
    return float(val)


def _apply_date_filter(query, start_date: Optional[str], end_date: Optional[str]):
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
    return query


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
    query = _apply_date_filter(query, start_date, end_date)

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


@router.get("/by-priority", response_model=PriorityStatsResponse, summary="按优先级统计")
async def get_priority_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    query = db.query(MessageRecord)
    query = _apply_date_filter(query, start_date, end_date)
    records = query.all()

    priority_map = {}
    for rec in records:
        p = rec.priority
        if p not in priority_map:
            priority_map[p] = {
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "total_duration": 0.0,
                "duration_count": 0,
            }
        priority_map[p]["total_count"] += 1
        if rec.status == MessageStatus.SUCCESS.value:
            priority_map[p]["success_count"] += 1
        elif rec.status == MessageStatus.FAILED.value:
            priority_map[p]["failed_count"] += 1
        if rec.duration_ms is not None:
            priority_map[p]["total_duration"] += rec.duration_ms
            priority_map[p]["duration_count"] += 1

    items = []
    for p, s in priority_map.items():
        total = s["total_count"]
        success = s["success_count"]
        delivery_rate = (success / total * 100) if total > 0 else 0.0
        avg_duration = (s["total_duration"] / s["duration_count"]) if s["duration_count"] > 0 else 0.0
        items.append(PriorityStats(
            priority=p,
            total_count=total,
            success_count=success,
            failed_count=s["failed_count"],
            delivery_rate=round(delivery_rate, 2),
            avg_duration_ms=round(avg_duration, 2),
        ))

    return PriorityStatsResponse(items=items)


@router.get("/failure-reasons", response_model=FailureReasonStatsResponse, summary="失败原因统计")
async def get_failure_reason_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    channel: Optional[str] = Query(None, description="按通道过滤"),
    db: Session = Depends(get_db),
):
    query = db.query(MessageRecord).filter(
        MessageRecord.status == MessageStatus.FAILED.value,
        MessageRecord.error_code.isnot(None),
    )
    query = _apply_date_filter(query, start_date, end_date)
    if channel:
        query = query.filter(MessageRecord.channel == channel)

    rows = query.with_entities(
        MessageRecord.error_code,
        func.count(MessageRecord.id).label("cnt"),
    ).group_by(MessageRecord.error_code).all()

    items = [FailureReasonStats(error_code=r.error_code, count=r.cnt) for r in rows]
    return FailureReasonStatsResponse(items=items)


@router.get("/retry-effectiveness", response_model=RetryEffectivenessResponse, summary="重试效果统计")
async def get_retry_effectiveness(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    query = db.query(MessageRecord)
    query = _apply_date_filter(query, start_date, end_date)
    records = query.all()

    bucket_map = {}
    for rec in records:
        rc = rec.retry_count or 0
        if rc >= 3:
            key = 3
        else:
            key = rc
        if key not in bucket_map:
            bucket_map[key] = {"total": 0, "success": 0}
        bucket_map[key]["total"] += 1
        if rec.status == MessageStatus.SUCCESS.value:
            bucket_map[key]["success"] += 1

    retry_breakdown = []
    for key in sorted(bucket_map.keys()):
        s = bucket_map[key]
        success_rate = (s["success"] / s["total"] * 100) if s["total"] > 0 else 0.0
        retry_breakdown.append(RetryStats(
            retry_count=key,
            total=s["total"],
            success=s["success"],
            success_rate=round(success_rate, 2),
        ))

    high_priority_records = [
        rec for rec in records
        if rec.priority == "high"
        and rec.first_send_time is not None
        and rec.delivered_time is not None
    ]
    if high_priority_records:
        latencies = [
            (rec.delivered_time - rec.first_send_time).total_seconds() * 1000
            for rec in high_priority_records
        ]
        avg_lat = sum(latencies) / len(latencies)
        sorted_lat = sorted(latencies)
        p95_idx = int(len(sorted_lat) * 0.95)
        p95_lat = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]
        high_priority_latency = HighPriorityLatencyStats(
            avg_end_to_end_ms=round(avg_lat, 2),
            p95_end_to_end_ms=round(p95_lat, 2),
            count=len(latencies),
        )
    else:
        high_priority_latency = HighPriorityLatencyStats(
            avg_end_to_end_ms=0.0,
            p95_end_to_end_ms=0.0,
            count=0,
        )

    normal_retry_records = [
        rec for rec in records
        if rec.priority == "normal"
        and (rec.retry_count or 0) > 0
    ]
    total_entered_retry = len(normal_retry_records)
    final_success = sum(
        1 for rec in normal_retry_records
        if rec.status == MessageStatus.SUCCESS.value
    )
    final_success_rate = (final_success / total_entered_retry * 100) if total_entered_retry > 0 else 0.0
    normal_retry_success = NormalRetrySuccessStats(
        total_entered_retry=total_entered_retry,
        final_success=final_success,
        final_success_rate=round(final_success_rate, 2),
    )

    return RetryEffectivenessResponse(
        retry_breakdown=retry_breakdown,
        high_priority_latency=high_priority_latency,
        normal_retry_success=normal_retry_success,
    )
