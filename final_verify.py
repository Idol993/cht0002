import requests
import json
import sqlite3
from datetime import datetime, timedelta

BASE = "http://localhost:8000"

print("=" * 60)
print("问题1验证：幂等重复提交返回真实状态")
print("=" * 60)

conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 清理测试数据
cursor.execute("DELETE FROM message_records WHERE biz_msg_id = 'biz_idempotent_test_001'")
conn.commit()

# 插入一条queued状态的消息
now = datetime.utcnow()
cursor.execute("""
    INSERT INTO message_records
    (message_id, user_id, content, priority, status, biz_msg_id,
     send_time, first_send_time, created_at, retry_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    'MSG_IDEMPOTENT_001',
    'user_idempotent_001',
    '测试幂等消息',
    'high',
    'queued',
    'biz_idempotent_test_001',
    now,
    now,
    now,
    1
))
conn.commit()
conn.close()

print("已在数据库中插入一条 status=queued 的消息")

# 用相同的biz_msg_id发送
r = requests.post(f'{BASE}/api/v1/messages/send', json={
    'user_id': 'user_idempotent_001',
    'content': '重复提交的内容',
    'priority': 'high',
    'biz_msg_id': 'biz_idempotent_test_001'
})

print(f'\n重复提交响应:')
print(f'  HTTP状态: {r.status_code}')
resp = r.json()
print(f'  status: {resp.get("status")}')
print(f'  message_id: {resp.get("message_id")}')

assert r.status_code == 202, f'期望HTTP 202，实际 {r.status_code}'
assert resp['status'] == 'queued', f'期望status=queued，实际 {resp.get("status")}'
assert resp['message_id'] == 'MSG_IDEMPOTENT_001'
print("✅ 问题1验证通过：幂等重复提交返回真实 queued 状态 + HTTP 202")

print("\n" + "=" * 60)
print("问题2验证：重试效果统计分母包含所有重试消息")
print("=" * 60)

conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 清理之前的测试数据
cursor.execute("DELETE FROM message_records WHERE user_id = 'user_stat_test'")
conn.commit()

# 插入测试数据：注意成功状态是 'success' 不是 'sent'
test_data = [
    ('success', 1, 'normal'),   # 重试成功1
    ('success', 1, 'normal'),   # 重试成功2
    ('success', 1, 'normal'),   # 重试成功3
    ('failed', 1, 'normal'),    # 重试失败1
    ('failed', 1, 'normal'),    # 重试失败2
    ('success', 0, 'normal'),   # 直接成功（不计入重试统计）
    ('success', 1, 'high'),     # 高优先级，不计入普通消息统计
]

for i, (status, rc, pri) in enumerate(test_data):
    cursor.execute("""
        INSERT INTO message_records 
        (message_id, user_id, content, priority, status, retry_count, send_time, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (f'MSG_STAT_{i}', 'user_stat_test', f'test{i}', pri, status, rc, now, now))

conn.commit()
conn.close()

print(f'已插入7条测试数据:')
print(f'  - 普通消息: 5条进入重试(3成功+2失败), 1条直接成功')
print(f'  - 高优先级: 1条进入重试(不计入普通消息统计)')

# 调用统计接口
r = requests.get(f'{BASE}/api/v1/stats/retry-effectiveness')
normal_retry = r.json()['normal_retry_success']

print(f'\n统计接口返回:')
print(f'  total_entered_retry: {normal_retry["total_entered_retry"]} (期望5)')
print(f'  final_success: {normal_retry["final_success"]} (期望3)')
print(f'  final_success_rate: {normal_retry["final_success_rate"]}% (期望60.0%)')

assert normal_retry['total_entered_retry'] == 5, f'期望5，实际{normal_retry["total_entered_retry"]}'
assert normal_retry['final_success'] == 3, f'期望3，实际{normal_retry["final_success"]}'
assert normal_retry['final_success_rate'] == 60.0, f'期望60.0，实际{normal_retry["final_success_rate"]}'
print("✅ 问题2验证通过：分母包含所有进入重试的消息（成功+失败）")

print("\n" + "=" * 60)
print("问题3验证：熔断恢复主动刷新")
print("=" * 60)

# 设置sms通道熔断，恢复时间设为过去（已到期）
conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

recovery_time = (now - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')
cursor.execute("""
    UPDATE channel_configs 
    SET circuit_breaker_active = 1, 
        consecutive_failures = 5,
        circuit_breaker_until = ?
    WHERE channel = 'sms'
""", (recovery_time,))
conn.commit()
conn.close()

print(f"已设置sms通道熔断，恢复时间: {recovery_time} (已过期)")
print("现在调用健康检查和管理接口，应该自动检测到恢复")

# 检查健康接口
r = requests.get(f'{BASE}/health')
channels = r.json()['channels']
sms_health = channels['sms']
print(f'\n健康接口 - sms:')
print(f'  circuit_breaker_active: {sms_health["circuit_breaker_active"]} (期望False)')
print(f'  consecutive_failures: {sms_health["consecutive_failures"]} (期望0)')
assert sms_health['circuit_breaker_active'] == False
assert sms_health['consecutive_failures'] == 0
print("✅ 3a: 健康接口主动检查到熔断恢复，连续失败次数清零")

# 检查管理接口
r = requests.get(f'{BASE}/api/v1/admin/channels')
channels_list = r.json()
sms_admin = next(c for c in channels_list if c['channel'] == 'sms')
print(f'\n管理接口 - sms:')
print(f'  circuit_breaker_active: {sms_admin["circuit_breaker_active"]} (期望False)')
print(f'  consecutive_failures: {sms_admin["consecutive_failures"]} (期望0)')
assert sms_admin['circuit_breaker_active'] == False
assert sms_admin['consecutive_failures'] == 0
print("✅ 3b: 管理接口主动检查到熔断恢复，与健康检查一致")

print("\n" + "=" * 60)
print("问题4验证：数据库迁移兼容旧版本")
print("=" * 60)

conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 检查message_records的新字段
cursor.execute("PRAGMA table_info(message_records)")
cols = [col[1] for col in cursor.fetchall()]
required_msg_cols = ['biz_msg_id', 'callback_url', 'first_send_time', 
                      'error_code', 'error_message', 'max_retries', 
                      'created_at', 'updated_at']

print("\nmessage_records 新字段检查:")
all_ok = True
for col in required_msg_cols:
    ok = col in cols
    print(f'  {col}: {"✅" if ok else "❌"}')
    if not ok:
        all_ok = False

# 检查channel_configs的新字段
cursor.execute("PRAGMA table_info(channel_configs)")
cols = [col[1] for col in cursor.fetchall()]
required_ch_cols = ['config_data', 'circuit_breaker_threshold', 
                    'circuit_breaker_recovery_minutes', 'circuit_breaker_active',
                    'circuit_breaker_until', 'consecutive_failures',
                    'created_at', 'updated_at']

print("\nchannel_configs 新字段检查:")
for col in required_ch_cols:
    ok = col in cols
    print(f'  {col}: {"✅" if ok else "❌"}')
    if not ok:
        all_ok = False

# 检查callback_records表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='callback_records'")
has_callback = cursor.fetchone() is not None
print(f'\ncallback_records 表: {"✅" if has_callback else "❌"}')
if not has_callback:
    all_ok = False

# 检查旧数据是否保留
cursor.execute("SELECT COUNT(*) FROM message_records WHERE user_id IN ('old_user', 'old_user2')")
old_count = cursor.fetchone()[0]
print(f'\n旧数据库测试记录保留: {old_count} 条 (>0)')
if old_count <= 0:
    all_ok = False
    print("❌ 旧数据丢失！")
else:
    print("✅ 旧数据已保留")

# 检查user_preferences的JSON字段格式
cursor.execute("SELECT channel_order, enabled_channels FROM user_preferences LIMIT 1")
row = cursor.fetchone()
if row:
    ch_order, ch_enabled = row
    print(f'\nuser_preferences JSON字段:')
    print(f'  channel_order: {ch_order}')
    print(f'  enabled_channels: {ch_enabled}')
    try:
        json.loads(ch_order)
        json.loads(ch_enabled)
        print("  ✅ JSON格式正确")
    except:
        print("  ❌ JSON格式错误")
        all_ok = False

conn.close()

if all_ok:
    print("\n✅ 问题4验证通过：数据库迁移成功，旧数据保留")
else:
    print("\n❌ 问题4验证失败")
    exit(1)

print("\n" + "=" * 60)
print("🎉 所有4个问题修复验证全部通过！")
print("=" * 60)
print("\n修复总结:")
print("1. 高优消息限频排队: 返回 queued 状态 + HTTP 202")
print("   - message_router.py 第129-138行: 返回 QUEUED 而非 RATE_LIMITED")
print("   - message_router.py 第47-63行: 幂等重复提交根据消息状态返回对应HTTP码")
print("2. 重试效果统计: 分母包含所有 retry_count>0 的消息")
print("   - message_router.py _queue_for_retry: 设置 retry_count=1")
print("   - retry_service.py: 重试失败也更新 retry_count")
print("   - stats.py 第315-319行: 统计条件为 (rec.retry_count or 0) > 0")
print("3. 熔断恢复: 健康检查和管理接口主动刷新")
print("   - health.py: 主动调用 channel_manager.is_circuit_breaker_active()")
print("   - admin.py list_channel_configs: 主动检查所有通道熔断状态")
print("   - manager.py is_circuit_breaker_active: 恢复后清零连续失败次数")
print("4. 数据库升级: 启动时自动 ALTER TABLE 补齐新字段")
print("   - database.py migrate_database(): 所有表的新增字段都自动添加")
print("   - main.py: 正确的调用顺序: create_all -> migrate -> init_configs")
