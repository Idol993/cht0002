import requests
import json
import time
import sqlite3

BASE = "http://localhost:8000"

print("=" * 60)
print("问题1验证：高优消息全通道限频返回 queued")
print("=" * 60)

# 把所有通道日限额设为0
for ch in ['sms', 'email', 'app_push', 'wechat']:
    r = requests.put(f'{BASE}/api/v1/admin/channels/{ch}', json={'daily_limit': 0})
    print(f'{ch}: {r.status_code}')

# 发送高优消息
print("\n发送 high 消息:")
r = requests.post(f'{BASE}/api/v1/messages/send', json={
    'user_id': 'user_3001',
    'content': '高优限频测试',
    'priority': 'high',
    'biz_msg_id': 'biz_test_queued_001'
})
print(f'HTTP: {r.status_code}')
resp = r.json()
print(f'status: {resp.get("status")}')
print(f'retry_after: {resp.get("retry_after_seconds")}')
print(f'msg_id: {resp.get("message_id")}')

assert r.status_code == 202
assert resp['status'] == 'queued'
assert resp['retry_after_seconds'] is not None
msg_id = resp['message_id']
print("✅ 1a: 高优全通道限频返回 queued + HTTP 202")

# 幂等测试
print("\n幂等测试:")
r2 = requests.post(f'{BASE}/api/v1/messages/send', json={
    'user_id': 'user_3001',
    'content': '重复提交',
    'priority': 'high',
    'biz_msg_id': 'biz_test_queued_001'
})
resp2 = r2.json()
print(f'status: {resp2.get("status")}')
print(f'msg_id: {resp2.get("message_id")}')
assert resp2['status'] == 'queued'
assert resp2['message_id'] == msg_id
print("✅ 1b: 幂等重复提交返回相同 queued 状态")

# 查询详情
r3 = requests.get(f'{BASE}/api/v1/messages/{msg_id}')
print(f'\n详情status: {r3.json()["status"]}')
assert r3.json()['status'] == 'queued'
print("✅ 1c: 发送接口与详情接口状态一致")

# 恢复限额
for ch, limit in [('sms', 5), ('email', 10), ('app_push', 20), ('wechat', 5)]:
    requests.put(f'{BASE}/api/v1/admin/channels/{ch}', json={'daily_limit': limit})

print("\n" + "=" * 60)
print("问题2验证：重试效果统计分母包含所有重试消息")
print("=" * 60)

# 造数据：5条进入重试（3成功+2失败），1条直接成功
conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 清理之前的测试数据
cursor.execute("DELETE FROM message_records WHERE user_id = 'user_stat_test'")
conn.commit()

# 插入测试数据
from datetime import datetime, timedelta
now = datetime.utcnow()

test_data = [
    # (status, retry_count, priority)
    ('sent', 1, 'normal'),   # 重试成功1
    ('sent', 1, 'normal'),   # 重试成功2
    ('sent', 1, 'normal'),   # 重试成功3
    ('failed', 1, 'normal'), # 重试失败1
    ('failed', 1, 'normal'), # 重试失败2
    ('sent', 0, 'normal'),   # 直接成功（不计入重试统计）
    ('sent', 1, 'high'),     # 高优先级，不计入普通消息统计
]

for i, (status, rc, pri) in enumerate(test_data):
    cursor.execute("""
        INSERT INTO message_records 
        (message_id, user_id, content, priority, status, retry_count, send_time, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (f'MSG_STAT_{i}', 'user_stat_test', f'test{i}', pri, status, rc, now, now))

conn.commit()

# 调用统计接口
r = requests.get(f'{BASE}/api/v1/stats/retry-effectiveness')
print(f'\n统计接口响应: {json.dumps(r.json(), indent=2, ensure_ascii=False)}')

normal_retry = r.json()['normal_message_retry']
print(f'\n普通消息重试效果:')
print(f'  总重试: {normal_retry["total_retried"]} (期望5)')
print(f'  成功: {normal_retry["retried_success"]} (期望3)')
print(f'  成功率: {normal_retry["success_rate"]} (期望0.6)')

assert normal_retry['total_retried'] == 5, f'期望5，实际{normal_retry["total_retried"]}'
assert normal_retry['retried_success'] == 3, f'期望3，实际{normal_retry["retried_success"]}'
assert normal_retry['success_rate'] == 0.6, f'期望0.6，实际{normal_retry["success_rate"]}'
print("✅ 问题2验证通过：分母包含所有进入重试的消息（成功+失败）")

conn.close()

print("\n" + "=" * 60)
print("问题3验证：熔断恢复主动刷新")
print("=" * 60)

# 设置sms通道熔断，恢复时间设为过去（已到期）
conn = sqlite3.connect('data/message_gateway.db')
cursor = conn.cursor()

# 先清零，然后设置熔断状态但恢复时间已过
cursor.execute("""
    UPDATE channel_configs 
    SET circuit_breaker_active = 1, 
        consecutive_failures = 5,
        circuit_breaker_until = ?
    WHERE channel = 'sms'
""", ((now - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'),))
conn.commit()
conn.close()

print("\n已设置sms通道熔断，但恢复时间已到（1秒前过期）")

# 检查健康接口 - 应该自动恢复
r = requests.get(f'{BASE}/health')
channels = r.json()['channels']
sms_health = next(c for c in channels if c['channel'] == 'sms')
print(f'\n健康接口 - sms:')
print(f'  circuit_breaker: {sms_health["circuit_breaker"]} (期望False)')
print(f'  consecutive_failures: {sms_health["consecutive_failures"]} (期望0)')
assert sms_health['circuit_breaker'] == False
assert sms_health['consecutive_failures'] == 0
print("✅ 3a: 健康接口主动检查到熔断恢复")

# 检查管理接口
r = requests.get(f'{BASE}/api/v1/admin/channels')
channels = r.json()['channels']
sms_admin = next(c for c in channels if c['channel'] == 'sms')
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
cursor.execute("SELECT COUNT(*) FROM message_records WHERE user_id = 'old_user_001'")
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
    import json
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
