"""Prometheus 指标定义"""
from prometheus_client import Counter, Histogram

# 请求计数器（按租户、模型、状态码）
request_total = Counter(
    "llm_requests_total",
    "Total requests",
    ["tenant", "model", "status_code"]
)

# 请求延迟直方图（按租户、模型）
request_duration = Histogram(
    "llm_request_duration_seconds",
    "Request latency in seconds",
    ["tenant", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Token 消耗计数器（按租户、模型、token类型）
tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens consumed",
    ["tenant", "model", "type"]
)

# 护栏拦截计数器（按护栏名称）
guard_blocks_total = Counter(
    "llm_guard_blocks_total",
    "Total guard blocks",
    ["guard_name"]
)

# 限流计数器（按租户）
rate_limit_hits = Counter(
    "llm_rate_limit_hits_total",
    "Total rate limit hits",
    ["tenant"]
)