# FinTech LLM Gateway

企业级大模型推理网关，专为金融场景设计。提供统一的多模型接入、安全合规管控、智能路由、流量控制与全链路可观测性。

## 核心特性

- **多模型统一接入**：配置驱动注册，一行配置新增模型，支持 OpenAI、DeepSeek、Moonshot 等
- **安全合规管控**：管道式护栏，含提示注入检测、敏感词过滤、数据边界控制、金融合规审核
- **智能路由**：支持加权随机、成本优先、延迟优先三种策略，自动过滤熔断/过载模型
- **多维度限流**：租户级令牌桶限流 + 模型级并发控制（Redis 原子槽位）
- **先进先出排队**：指定模型并发满时，按申请时间排队等待，槽位释放时自动唤醒
- **熔断器**：3 状态熔断（Closed/Open/Half-Open），连续失败自动隔离，冷却后半开探测
- **Fallback 模型切换**：首选模型不可用时自动切换备选模型，响应头提示切换信息
- **请求去重缓存**：同租户短时间相同请求直接返回缓存，减少重复调用
- **鉴权本地缓存**：首次请求懒加载租户配置，后续纯内存读取，减少 Redis 访问
- **全链路审计**：每次调用记录租户、模型、Token 消耗、延迟、护栏拦截等 15+ 维度
- **Prometheus 可观测性**：QPS、延迟、Token、护栏、健康度、熔断状态等指标

## 系统架构

```
请求 → 中间件(鉴权/限流) → 编排层 → 路由引擎 → Fallback → 适配器 → 模型后端
 │      │                │         │          │         │
 │      │                │         │          │       Redis
 │      │                │         │          │      本地缓存
 │      │                │         │          │      健康度
 │      │                │         │          │      熔断器
 │      │                │         │          │      并发槽位
 │      │                │         │          │
 │      │                │         │       Prometheus
 │      │                │         │
 │      └────────────────┴─────────┘
 │
 └── Grafana
```

## 核心模块

| 模块 | 职责 |
|------|------|
| 接入层 | 请求准入（鉴权、权限校验、审计上下文初始化） |
| 合规层 | 管道式安全护栏（注入检测、敏感词、数据边界、金融合规） |
| 路由层 | 适配器注册、动态路由引擎、成本/延迟/健康度策略 |
| 韧性层 | 熔断器、Fallback 切换、并发控制、FIFO 排队、令牌桶限流 |
| 缓存层 | 请求去重缓存、鉴权本地缓存 |
| 审计层 | 全链路审计日志、Prometheus 指标 |

## 技术栈

- **Web 框架**：FastAPI + Uvicorn
- **异步**：asyncio + aiohttp
- **存储**：Redis（鉴权/限流/并发控制/缓存）
- **监控**：Prometheus + Grafana
- **配置**：Pydantic v2 + python-dotenv
- **部署**：Docker + Docker Compose

## 快速开始

### 环境要求

- Python 3.12+
- Redis 6+

### 安装

```bash
git clone <repo-url>
cd llm-gateway
pip install -r requirements.txt
```

### 配置

复制 `.env.example` 为 `.env`，填写必要配置：

```env
LLM_API_KEY=sk-your-deepseek-key
LLM_BASE_URL=https://api.deepseek.com/v1
REDIS_URL=redis://localhost:6379
```

### 启动 Redis

```bash
# Linux / macOS
redis-server

# Windows
redis-server.exe
```

### 初始化租户数据

```bash
redis-cli HSET tenant:sk-dev-team-001 id "dev_team" name "研发部" allowed_models "deepseek-chat,gpt-4" status "active"
```

### 启动网关

```bash
python main.py
```

网关默认监听 `http://localhost:8000`。

### 验证

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-dev-team-001" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"你好"}]}'
```

## API 设计

兼容 OpenAI SDK，业务方只需修改 `base_url` 即可接入。

| 端点 | 方法 | 鉴权 | 说明 |
|------|------|------|------|
| `/v1/chat/completions` | POST | 需要 | 核心聊天接口，支持流式/非流式 |
| `/health` | GET | 否 | 健康检查 |
| `/metrics` | GET | 否 | Prometheus 指标 |
| `/admin/model-health` | GET | 否 | 模型健康度详情 |

### 请求参数

```json
{
  "model": "deepseek-chat",
  "messages": [...],
  "stream": false,
  "cache_bypass": false,
  "temperature": 0.7,
  "max_tokens": 512
}
```

## 项目结构

```
llm-gateway/
├── app/
│   ├── api/                    # 接入层
│   │   ├── v1/chat.py          # 编排层入口
│   │   ├── request_prepare.py  # 请求准入
│   │   ├── cache_handler.py    # 去重缓存
│   │   ├── finalizer.py        # 请求收尾
│   │   ├── fallback_handler.py # Fallback 处理
│   │   └── admin.py            # 管理接口
│   ├── adapters/               # 模型适配器
│   │   ├── base.py             # 适配器基类
│   │   ├── registry.py         # 适配器注册中心
│   │   └── universal.py        # 通用适配器
│   ├── middleware/             # 中间件
│   │   ├── authentication.py   # API Key 鉴权
│   │   └── ratelimit.py        # 令牌桶限流
│   ├── services/               # 业务服务
│   │   ├── routing/            # 路由引擎
│   │   │   ├── engine.py       # 路由决策核心
│   │   │   ├── strategies.py   # 策略实现
│   │   │   ├── cost.py         # 成本估算
│   │   │   ├── health.py       # 健康度追踪 + 并发控制
│   │   │   └── router.py       # 模型转发
│   │   ├── resilience/         # 韧性层
│   │   │   ├── circuit_breaker.py  # 熔断器
│   │   │   ├── token_bucket.py     # 令牌桶
│   │   │   └── rate_limiter.py     # 限流器
│   │   └── compliance/         # 合规层
│   │       ├── base.py          # 护栏基类
│   │       ├── input_guards.py  # 输入护栏
│   │       ├── output_guards.py # 输出护栏
│   │       ├── rules_engine.py  # 规则引擎
│   │       └── rules/compliance_rules.yaml
│   ├── models/                 # 数据模型
│   │   ├── chat.py              # 请求/响应模型
│   │   └── health.py            # 健康度模型
│   └── core/                   # 基础设施
│       ├── config.py            # 全局配置
│       ├── metrics.py           # Prometheus 指标
│       ├── audit_context.py     # 审计上下文
│       └── audit_logger.py      # 审计日志
├── logs/                        # 审计日志文件
├── main.py                      # 启动入口
├── requirements.txt
├── .env.example
└── README.md
```

## 设计决策与亮点

### 租户鉴权本地缓存

首次请求从 Redis 加载租户配置到本地内存，后续请求纯内存读取（纳秒级）。通过 `asyncio.Lock` 实现双重检查锁定，防止缓存过期时的并发击穿。参考 Kong/APISIX 数据面本地缓存模式。

### 模型并发控制

使用 Redis 原子 `INCR/DECR` + Lua 脚本实现，保证高并发下的准确性。批量读取通过 `MGET` 一次获取所有模型并发数。显式指定模型时支持 FIFO 排队等待（`Condition` + `deque`），槽位释放时主动唤醒下一个等待者。

### 熔断 + Fallback 双层保护

熔断器（3 状态）在模型连续失败或失败率超阈值时自动隔离，冷却后进入半开探测。Fallback 在模型不可用时按策略顺序切换备选模型，切换信息通过响应头告知客户端。

### 金融合规护栏

6 个独立护栏节点可插拔组合，覆盖提示注入、敏感词、数据边界、金融合规审核、系统提示词泄露检测。规则通过 YAML 配置文件驱动，合规团队无需改代码即可调整规则，支持热更新。

### 路由策略

支持加权随机、成本优先、延迟优先三种策略。成本估算根据请求实际 Token 数和模型单价动态计算。延迟数据通过滑动窗口维护，P95 异常时自动降权。

## 开发计划

- [x] 多模型路由与适配器注册
- [x] 多租户鉴权与权限管理
- [x] 安全护栏管道（输入/输出）
- [x] 令牌桶限流（租户级）
- [x] 模型并发控制（Redis 原子槽位）
- [x] 熔断器（3 状态）
- [x] Fallback 模型切换
- [x] 先进先出排队等待
- [x] 审计日志与 Prometheus 指标
- [x] 租户配置本地缓存
- [ ] 客户端断连检测（开发中）
- [ ] Grafana 仪表盘模板
