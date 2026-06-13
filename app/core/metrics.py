"""
Prometheus 指标定义与记录
--------------------------
定义所有业务指标，并提供一个统一的 record() 函数供编排层调用。
"""
import time
from prometheus_client import Counter, Histogram

# ======================== 指标定义 ========================

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


# ======================== 统一记录函数 ========================

def record(ctx):
    """
    记录所有 Prometheus 指标。
    编排层只需调用此函数，不需要知道内部有哪些指标。
    """
    request_total.labels(
        tenant=ctx.tenant_id,
        model=ctx.model,
        status_code=str(ctx.status_code)
    ).inc()

    request_duration.labels(
        tenant=ctx.tenant_id,
        model=ctx.model
    ).observe(time.time() - ctx.start_time)

    if ctx.status_code == 200:
        tokens_total.labels(
            tenant=ctx.tenant_id, model=ctx.model, type="prompt"
        ).inc(ctx.tokens_prompt)
        tokens_total.labels(
            tenant=ctx.tenant_id, model=ctx.model, type="completion"
        ).inc(ctx.tokens_completion)
        tokens_total.labels(
            tenant=ctx.tenant_id, model=ctx.model, type="total"
        ).inc(ctx.tokens_total)

    if ctx.guard_triggered:
        guard_blocks_total.labels(
            guard_name=ctx.guard_triggered
        ).inc()

    if ctx.status_code == 429:
        rate_limit_hits.labels(
            tenant=ctx.tenant_id
        ).inc()