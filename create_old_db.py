import os
import sys
import sqlite3

old_db_path = "data/message_gateway_old.db"
new_db_path = "data/message_gateway.db"

if os.path.exists(old_db_path):
    os.remove(old_db_path)
if os.path.exists(new_db_path):
    os.remove(new_db_path)

os.makedirs("data", exist_ok=True)

conn = sqlite3.connect(old_db_path)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS message_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id VARCHAR(64) NOT NULL UNIQUE,
    user_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    priority VARCHAR(32) NOT NULL,
    channel VARCHAR(32),
    status VARCHAR(32) NOT NULL,
    send_time DATETIME,
    delivered_time DATETIME,
    duration_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    extra_data TEXT,
    title VARCHAR(512),
    template_id VARCHAR(128),
    template_data TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS channel_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel VARCHAR(32) NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    daily_limit INTEGER NOT NULL DEFAULT 100,
    priority_weight INTEGER NOT NULL DEFAULT 10,
    retry_count INTEGER NOT NULL DEFAULT 3
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(64) NOT NULL UNIQUE,
    channel_order TEXT,
    enabled_channels TEXT,
    quiet_hours_start VARCHAR(8),
    quiet_hours_end VARCHAR(8),
    notify_email VARCHAR(255),
    notify_phone VARCHAR(32),
    notify_wechat_openid VARCHAR(128),
    notify_app_token VARCHAR(255)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS daily_limit_counters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(64) NOT NULL,
    channel VARCHAR(32) NOT NULL,
    date DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    marketing_count INTEGER NOT NULL DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    priority VARCHAR(32) NOT NULL,
    channels_tried TEXT,
    next_retry_time DATETIME NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    last_error TEXT,
    extra_data TEXT
)''')

for ch in ["sms", "email", "app_push", "wechat"]:
    c.execute(f"INSERT INTO channel_configs (channel, enabled, daily_limit, priority_weight, retry_count) VALUES ('{ch}', 1, 100, 10, 3)")

c.execute("INSERT INTO message_records (message_id, user_id, content, priority, status, send_time, retry_count) VALUES ('MSG_OLD_001', 'old_user', 'old message', 'normal', 'success', datetime('now'), 0)")
c.execute("INSERT INTO message_records (message_id, user_id, content, priority, status, send_time, retry_count) VALUES ('MSG_OLD_002', 'old_user2', 'old message 2', 'high', 'failed', datetime('now'), 1)")

c.execute("INSERT INTO user_preferences (user_id, channel_order, enabled_channels) VALUES ('old_user', 'sms,email,app_push,wechat', 'sms,email,app_push,wechat')")

c.execute("INSERT INTO daily_limit_counters (user_id, channel, date, count) VALUES ('old_user', 'sms', date('now'), 2)")

conn.commit()
conn.close()

print("旧数据库创建成功！")
print(f"旧数据库文件: {old_db_path}")
print("包含旧表结构（缺少 biz_msg_id, callback_url, first_send_time, error_code, circuit_breaker_*, callback_records 等）")

os.rename(old_db_path, new_db_path)
print(f"已将旧数据库重命名为: {new_db_path}")
print("现在启动服务会自动执行数据库迁移...")
