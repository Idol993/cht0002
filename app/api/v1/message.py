from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.schemas.message import (
    SendMessageRequest,
    SendMessageResponse,
    MessageListResponse,
    MessageRecordOut,
    MessageStatus,
)
from app.services.message_router import MessageRouter
from app.models.message import MessageRecord

router = APIRouter(prefix="/api/v1/messages", tags=["消息"])


@router.post("/send", response_model=SendMessageResponse, summary="发送消息")
async def send_message(
    request: SendMessageRequest,
    db: Session = Depends(get_db),
):
    """
    统一消息发送接口

    - **user_id**: 用户ID
    - **content**: 消息内容
    - **priority**: 优先级 (high/normal/marketing)
        - high: 高优先级，主通道失败立即切备用通道重试
        - normal: 普通优先级，失败延迟5分钟重试
        - marketing: 营销类，失败不重试
    - **title**: 消息标题（邮件/App推送使用）
    - **template_id**: 模板ID（微信模板消息使用）
    - **template_data**: 模板数据
    """
    router_svc = MessageRouter(db)

    message_id, status, channel, retry_after, http_status_code = router_svc.send_message(
        user_id=request.user_id,
        content=request.content,
        priority=request.priority.value,
        title=request.title,
        template_id=request.template_id,
        template_data=request.template_data,
        metadata=request.metadata,
        biz_msg_id=request.biz_msg_id,
        callback_url=request.callback_url,
    )

    status_msg_map = {
        MessageStatus.SUCCESS.value: "消息发送成功",
        MessageStatus.FAILED.value: "消息发送失败",
        MessageStatus.RATE_LIMITED.value: "消息被限频",
        MessageStatus.RETRYING.value: "消息正在重试中",
        MessageStatus.QUEUED.value: "消息已排队",
        MessageStatus.PENDING.value: "消息处理中",
    }

    resp = SendMessageResponse(
        message_id=message_id,
        status=status,
        channel=channel,
        retry_after_seconds=retry_after,
        message=status_msg_map.get(status, "未知状态"),
        biz_msg_id=request.biz_msg_id,
    )

    return JSONResponse(
        content=resp.model_dump(),
        status_code=http_status_code,
    )


@router.get("", response_model=MessageListResponse, summary="查询消息记录")
async def list_messages(
    user_id: Optional[str] = Query(None, description="按用户ID过滤"),
    channel: Optional[str] = Query(None, description="按通道过滤"),
    status: Optional[str] = Query(None, description="按状态过滤"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
):
    """
    支持按时间、用户、通道组合查询消息记录
    """
    query = db.query(MessageRecord)

    if user_id:
        query = query.filter(MessageRecord.user_id == user_id)
    if channel:
        query = query.filter(MessageRecord.channel == channel)
    if status:
        query = query.filter(MessageRecord.status == status)
    if start_time:
        query = query.filter(MessageRecord.send_time >= start_time)
    if end_time:
        query = query.filter(MessageRecord.send_time <= end_time)

    total = query.count()

    items = (
        query.order_by(MessageRecord.send_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return MessageListResponse(
        total=total,
        items=[MessageRecordOut.model_validate(item) for item in items],
    )


@router.get("/{message_id}", response_model=MessageRecordOut, summary="查询单条消息详情")
async def get_message(
    message_id: str,
    db: Session = Depends(get_db),
):
    record = (
        db.query(MessageRecord)
        .filter(MessageRecord.message_id == message_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="消息不存在")
    return MessageRecordOut.model_validate(record)
