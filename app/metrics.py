from prometheus_client import Counter, Histogram, Gauge


MESSAGE_TOTAL = Counter(
    "message_gateway_messages_total",
    "Total number of messages processed",
    ["channel", "priority"],
)

MESSAGE_SUCCESS = Counter(
    "message_gateway_messages_success_total",
    "Total number of successful messages",
    ["channel", "priority"],
)

MESSAGE_FAILED = Counter(
    "message_gateway_messages_failed_total",
    "Total number of failed messages",
    ["channel", "priority"],
)

MESSAGE_DURATION = Histogram(
    "message_gateway_message_duration_seconds",
    "Message delivery duration in seconds",
    ["channel"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

CHANNEL_STATUS = Gauge(
    "message_gateway_channel_status",
    "Channel status (1=enabled, 0=disabled)",
    ["channel"],
)

RATE_LIMITED_TOTAL = Counter(
    "message_gateway_rate_limited_total",
    "Total number of rate limited messages",
    ["channel"],
)

RETRY_QUEUE_SIZE = Gauge(
    "message_gateway_retry_queue_size",
    "Current size of retry queue",
)


class MessageMetrics:
    def inc_total(self, channel: str, priority: str = "normal"):
        MESSAGE_TOTAL.labels(channel=channel, priority=priority).inc()

    def inc_success(self, channel: str, priority: str = "normal"):
        MESSAGE_SUCCESS.labels(channel=channel, priority=priority).inc()

    def inc_failure(self, channel: str, priority: str = "normal"):
        MESSAGE_FAILED.labels(channel=channel, priority=priority).inc()

    def observe_duration(self, channel: str, duration_seconds: float):
        MESSAGE_DURATION.labels(channel=channel).observe(duration_seconds)

    def set_channel_status(self, channel: str, enabled: bool):
        CHANNEL_STATUS.labels(channel=channel).set(1 if enabled else 0)

    def inc_rate_limited(self, channel: str):
        RATE_LIMITED_TOTAL.labels(channel=channel).inc()

    def set_retry_queue_size(self, size: int):
        RETRY_QUEUE_SIZE.set(size)


message_metrics = MessageMetrics()
