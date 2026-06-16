import requests
import time
import json

BASE_URL = "http://localhost:8000"

print("=" * 60)
print("多通道消息网关 - 第三阶段问题修复验证")
print("=" * 60)

# 首先清空数据库中的测试数据
print("\n[准备] 重置限频计数器，确保测试准确...")
for i in range(1, 11):
    try:
        requests.put(f"{BASE_URL}/api/v1/admin/channels/sms", json={"daily_limit": 5})
        requests.put(f"{BASE_URL}/api/v1/admin/channels/app_push", json={"daily_limit": 20})
        break
    except Exception as e:
        print(f"  重试 {i}/10: {e}")
        time.sleep(0.5)

print("\n" + "=" * 60)
print("问题1: 高优消息限频排队时返回 queued 状态")
print("=" * 60)

# 为了模拟全通道限频，先设置所有通道日限额为1，然后给用户发2条高优消息
# 第一条成功，第二条会全通道限频
print("\n[步骤1] 设置所有通道日限额为1，用户1001先发1条耗尽额度...")
for ch in ["sms", "email", "app_push", "wechat"]:
    r = requests.put(f"{BASE_URL}/api/v1/admin/channels/{ch}", json={"daily_limit": 1})
    print(f"  {ch}: {r.status_code} - {r.json().get('message', '')}")

# 发第一条高优消息，应该成功
print("\n[步骤2] 发送第一条 high 消息（应该成功）...")
r = requests.post(f"{BASE_URL}/api/v1/messages/send", json={
    "user_id": "user_1001",
    "content": "高优测试消息1",
    "priority": "high",
    "biz_msg_id": "biz_high_001"
})
print(f"  HTTP状态: {r.status_code}")
print(f"  响应: {json.dumps(r.json(), indent=2, ensure_ascii=False)}")
assert r.status_code == 200, "第一条应该成功"
assert r.json()["status"] == "sent", "第一条状态应该是 sent"

# 等待一小会儿确保第一条发送完成
time.sleep(0.5)

# 发第二条高优消息，应该全通道限频，返回 queued
print("\n[步骤3] 发送第二条 high 消息（应该全通道限频，返回 queued）...")
r = requests.post(f"{BASE_URL}/api/v1/messages/send", json={
    "user_id": "user_1001",
    "content": "高优测试消息2",
    "priority": "high",
    "biz_msg_id": "biz_high_002"
})
print(f"  HTTP状态: {r.status_code}")
resp = r.json()
print(f"  响应: {json.dumps(resp, indent=2, ensure_ascii=False)}")
print(f"  status: {resp.get('status')}")
print(f"  retry_after_seconds: {resp.get('retry_after_seconds')}")

# 验证：HTTP状态应该是202，status应该是queued
assert r.status_code == 202, f"期望HTTP 202，实际 {r.status_code}"
assert resp["status"] == "queued", f"期望 status=queued，实际 {resp.get('status')}"
assert resp["retry_after_seconds"] is not None, "应该有 retry_after_seconds"
msg_id2 = resp["message_id"]
print(f"  ✅ 验证通过：status=queued, HTTP=202")

# 幂等测试：用同一个biz_msg_id重复提交第二条消息
print("\n[步骤4] 幂等测试：重复提交 biz_high_002，应该返回相同的 queued 状态...")
r = requests.post(f"{BASE_URL}/api/v1/messages/send", json={
    "user_id": "user_1001",
    "content": "高优测试消息2（重复）",
    "priority": "high",
    "biz_msg_id": "biz_high_002"
})
print(f"  HTTP状态: {r.status_code}")
resp = r.json()
print(f"  响应: {json.dumps(resp, indent=2, ensure_ascii=False)}")
print(f"  status: {resp.get('status')}")

# 验证：重复提交也应该返回 queued，不应该是 rate_limited
assert resp["status"] == "queued", f"幂等重复提交期望 status=queued，实际 {resp.get('status')}"
assert resp["message_id"] == msg_id2, "应该返回相同的 message_id"
print(f"  ✅ 验证通过：重复提交返回相同 queued 状态")

# 查询详情验证状态一致
print("\n[步骤5] 查询消息详情，验证数据库中的状态也是 queued...")
r = requests.get(f"{BASE_URL}/api/v1/messages/{msg_id2}")
resp = r.json()
print(f"  详情状态: {resp.get('status')}")
assert resp["status"] == "queued", f"详情状态期望 queued，实际 {resp.get('status')}"
print(f"  ✅ 验证通过：发送接口和详情接口状态一致")

print("\n" + "=" * 60)
print("问题2: 重试效果统计 - 分母包含所有进入重试的消息")
print("=" * 60)

# 先恢复通道日限额
print("\n[准备] 恢复通道日限额...")
for ch, limit in [("sms", 5), ("email", 10), ("app_push", 20), ("wechat", 5)]:
    requests.put(f"{BASE_URL}/api/v1/admin/channels/{ch}", json={"daily_limit": limit})

# 发送一些普通消息，模拟进入延迟重试
# 为了让普通消息进入重试，我们可以先让通道失败（暂时用mock）
# 或者直接造数据：发送普通消息，然后手动更新数据库标记为已重试
print("\n[步骤1] 发送10条普通消息，其中一些会进入延迟重试...")
for i in range(10):
    r = requests.post(f"{BASE_URL}/api/v1/messages/send", json={
        "user_id": "user_2001",
        "content": f"普通测试消息{i+1}",
        "priority": "normal"
    })
    print(f"  消息{i+1}: HTTP={r.status_code}, status={r.json().get('status')}")

# 现在手动在数据库中造一些进入重试的数据（模拟重试服务已经处理过）
# 我们需要：3条成功进入重试且最终成功，2条进入重试但最终失败，1条没进入重试直接成功
print("\n[步骤2] 手动修改数据库模拟重试场景（3成功+2失败）...")
import sqlite3
conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 获取刚才发送的10条消息的ID
cursor.execute("SELECT id, status FROM message_records WHERE user_id = 'user_2001' ORDER BY created_at DESC LIMIT 10")
rows = cursor.fetchall()
print(f"  找到 {len(rows)} 条消息")

# 修改前5条：3条标记为已重试且成功，2条标记为已重试但失败
for i, (mid, status) in enumerate(rows[:5]):
    if i < 3:
        # 重试成功
        cursor.execute("""
            UPDATE message_records 
            SET status = 'sent', retry_count = 1, first_send_time = created_at
            WHERE id = ?
        """, (mid,))
        print(f"  消息{mid}: 标记为重试成功 (retry_count=1, status=sent)")
    else:
        # 重试失败
        cursor.execute("""
            UPDATE message_records 
            SET status = 'failed', retry_count = 1, first_send_time = created_at
            WHERE id = ?
        """, (mid,))
        print(f"  消息{mid}: 标记为重试失败 (retry_count=1, status=failed)")

# 修改第6条：没进入重试，直接成功
if len(rows) > 5:
    cursor.execute("""
        UPDATE message_records 
        SET status = 'sent', retry_count = 0, first_send_time = created_at
        WHERE id = ?
    """, (rows[5][0],))
    print(f"  消息{rows[5][0]}: 标记为直接成功 (retry_count=0, status=sent)")

conn.commit()
conn.close()
print("  数据库修改完成")

# 查询重试效果统计
print("\n[步骤3] 查询重试效果统计接口...")
r = requests.get(f"{BASE_URL}/api/v1/stats/retry-effectiveness")
print(f"  HTTP状态: {r.status_code}")
resp = r.json()
print(f"  完整响应: {json.dumps(resp, indent=2, ensure_ascii=False)}")

# 验证普通消息重试效果
normal_retry = resp.get("normal_message_retry", {})
print(f"\n  普通消息重试效果:")
print(f"    总重试次数: {normal_retry.get('total_retried')}")
print(f"    重试成功: {normal_retry.get('retried_success')}")
print(f"    成功率: {normal_retry.get('success_rate')}")

# 验证：分母应该是5（3成功+2失败），不是3（只有成功的）
assert normal_retry.get("total_retried") == 5, f"期望 total_retried=5，实际 {normal_retry.get('total_retried')}"
assert normal_retry.get("retried_success") == 3, f"期望 retried_success=3，实际 {normal_retry.get('retried_success')}"
assert normal_retry.get("success_rate") == 0.6, f"期望 success_rate=0.6，实际 {normal_retry.get('success_rate')}"
print(f"  ✅ 验证通过：分母包含所有进入重试的消息（成功+失败）")

print("\n" + "=" * 60)
print("问题3: 熔断恢复主动刷新 - 健康检查和管理接口")
print("=" * 60)

print("\n[步骤1] 触发sms通道熔断：连续失败5次...")
# 直接修改数据库模拟sms通道连续失败5次，激活熔断
import sqlite3
from datetime import datetime, timedelta
conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 设置sms通道熔断，恢复时间在1秒后
recovery_time = (datetime.utcnow() + timedelta(seconds=3)).strftime('%Y-%m-%d %H:%M:%S')
cursor.execute("""
    UPDATE channel_configs 
    SET circuit_breaker_active = 1, 
        consecutive_failures = 5,
        circuit_breaker_until = ?
    WHERE channel = 'sms'
""", (recovery_time,))
conn.commit()
conn.close()
print(f"  已设置sms通道熔断，恢复时间: {recovery_time}")

# 检查健康接口 - 应该显示熔断
print("\n[步骤2] 检查健康接口 - 应该显示sms熔断...")
r = requests.get(f"{BASE_URL}/health")
resp = r.json()
channels = resp.get("channels", [])
sms_status = next((c for c in channels if c["channel"] == "sms"), None)
print(f"  sms通道: circuit_breaker={sms_status.get('circuit_breaker')}, consecutive_failures={sms_status.get('consecutive_failures')}")
assert sms_status.get("circuit_breaker") == True, "应该显示熔断激活"
assert sms_status.get("consecutive_failures") == 5, "连续失败次数应该是5"
print(f"  ✅ 健康接口正确显示熔断状态")

# 检查管理接口 - 应该显示熔断
print("\n[步骤3] 检查管理接口 - 应该显示sms熔断...")
r = requests.get(f"{BASE_URL}/api/v1/admin/channels")
resp = r.json()
channels = resp.get("channels", [])
sms_cfg = next((c for c in channels if c["channel"] == "sms"), None)
print(f"  sms通道: circuit_breaker_active={sms_cfg.get('circuit_breaker_active')}, consecutive_failures={sms_cfg.get('consecutive_failures')}")
assert sms_cfg.get("circuit_breaker_active") == True, "应该显示熔断激活"
assert sms_cfg.get("consecutive_failures") == 5, "连续失败次数应该是5"
print(f"  ✅ 管理接口正确显示熔断状态")

# 等待熔断恢复时间到期
print("\n[步骤4] 等待熔断恢复时间到期（3秒）...")
time.sleep(3)
print("  熔断恢复时间已到！")

# 先查健康接口 - 应该自动恢复，不需要发送消息
print("\n[步骤5] 检查健康接口 - 应该显示sms已自动恢复（无需发送消息）...")
r = requests.get(f"{BASE_URL}/health")
resp = r.json()
channels = resp.get("channels", [])
sms_status = next((c for c in channels if c["channel"] == "sms"), None)
print(f"  sms通道: circuit_breaker={sms_status.get('circuit_breaker')}, consecutive_failures={sms_status.get('consecutive_failures')}")
assert sms_status.get("circuit_breaker") == False, "应该显示熔断已恢复"
assert sms_status.get("consecutive_failures") == 0, "连续失败次数应该已清零"
print(f"  ✅ 健康接口正确显示自动恢复，连续失败次数已清零")

# 再查管理接口 - 应该一致
print("\n[步骤6] 检查管理接口 - 应该显示sms已自动恢复...")
r = requests.get(f"{BASE_URL}/api/v1/admin/channels")
resp = r.json()
channels = resp.get("channels", [])
sms_cfg = next((c for c in channels if c["channel"] == "sms"), None)
print(f"  sms通道: circuit_breaker_active={sms_cfg.get('circuit_breaker_active')}, consecutive_failures={sms_cfg.get('consecutive_failures')}")
assert sms_cfg.get("circuit_breaker_active") == False, "应该显示熔断已恢复"
assert sms_cfg.get("consecutive_failures") == 0, "连续失败次数应该已清零"
print(f"  ✅ 管理接口正确显示自动恢复，与健康检查一致")

print("\n" + "=" * 60)
print("问题4: 数据库升级兼容 - 旧数据库自动迁移")
print("=" * 60)

# 检查数据库中的新字段是否存在
print("\n[步骤1] 验证数据库迁移后的表结构...")
import sqlite3
conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 检查 message_records 表的新字段
cursor.execute("PRAGMA table_info(message_records)")
columns = [col[1] for col in cursor.fetchall()]
new_columns = ["biz_msg_id", "callback_url", "first_send_time", "error_code", "created_at", "updated_at", "max_retries"]
print(f"  message_records 新字段:")
for col in new_columns:
    exists = col in columns
    print(f"    {col}: {'✅ 存在' if exists else '❌ 缺失'}")
    assert exists, f"缺少字段: {col}"

# 检查 channel_configs 表的新字段
cursor.execute("PRAGMA table_info(channel_configs)")
columns = [col[1] for col in cursor.fetchall()]
new_columns = ["circuit_breaker_threshold", "circuit_breaker_recovery_minutes", 
               "circuit_breaker_active", "circuit_breaker_until", 
               "consecutive_failures", "config_data", "created_at", "updated_at"]
print(f"  channel_configs 新字段:")
for col in new_columns:
    exists = col in columns
    print(f"    {col}: {'✅ 存在' if exists else '❌ 缺失'}")
    assert exists, f"缺少字段: {col}"

# 检查 callback_records 表是否存在
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='callback_records'")
assert cursor.fetchone() is not None, "缺少 callback_records 表"
print(f"  callback_records 表: ✅ 存在")

# 检查 user_preferences 的 JSON 字段是否正确转换
cursor.execute("SELECT channel_order, enabled_channels FROM user_preferences LIMIT 1")
row = cursor.fetchone()
if row:
    ch_order, ch_enabled = row
    print(f"  user_preferences JSON字段:")
    print(f"    channel_order: {ch_order}")
    print(f"    enabled_channels: {ch_enabled}")
    # 验证是JSON格式
    import json
    json.loads(ch_order)
    json.loads(ch_enabled)
    print(f"    ✅ JSON格式正确")

# 检查旧数据是否保留
cursor.execute("SELECT COUNT(*) FROM message_records WHERE user_id = 'old_user_001'")
old_count = cursor.fetchone()[0]
print(f"  旧数据库中的测试记录: {old_count} 条（应该>0）")
assert old_count > 0, "旧数据丢失！"
print(f"  ✅ 旧数据已保留")

conn.close()

print("\n" + "=" * 60)
print("✅ 所有4个问题修复验证通过！")
print("=" * 60)
print("\n修复总结:")
print("1. 高优消息限频排队: 返回 queued 状态 + HTTP 202，幂等重复提交状态一致")
print("2. 重试效果统计: 分母包含所有进入重试的消息（成功+失败）")
print("3. 熔断恢复: 健康检查和管理接口主动刷新，恢复后连续失败次数清零")
print("4. 数据库升级: 自动 ALTER TABLE 补齐新字段，保留旧数据，服务正常启动")
