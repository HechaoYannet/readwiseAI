# ReadWise AI

> 基于 FastAPI + 多 Agent 架构的智能高考英语学习系统

ReadWise AI 通过 AI 驱动的多个专家 Sub-Agent，为高中生提供**错题诊断、文章生成、题目生成、问答辅导、遗忘曲线复习**等全流程智能备考服务。

---

## 目录

1. [核心功能](#1-核心功能)
2. [系统架构](#2-系统架构)
3. [项目结构](#3-项目结构)
4. [快速开始](#4-快速开始)
5. [API 总览](#5-api-总览)
   - [认证 API](#51-认证-api)
   - [用户 API](#52-用户-api)
   - [答题 API](#53-答题-api)
   - [长期记忆 API](#54-长期记忆-api)
   - [会话 API](#55-会话-api)
   - [内部 API](#56-内部-api)
6. [request_type 说明](#6-request_type-说明)
7. [Sub-Agent 说明](#7-sub-agent-说明)
8. [记忆系统设计](#8-记忆系统设计)
9. [管理员 CLI](#9-管理员-cli)
10. [外部依赖](#10-外部依赖)
11. [配置与环境变量](#11-配置与环境变量)
12. [测试](#12-测试)
13. [POST /api/attempt 逐行代码分析与调用流程](#13-post-apiattempt-逐行代码分析与调用流程)

---

## 1. 核心功能

| 功能 | 说明 |
|------|------|
| **错题诊断** | 分析学生答题错误的根本原因，给出证据句、建议和同类题 |
| **文章生成** | 按难度 L1–L4 × 体裁（议论/说明/记叙）生成高考风格英文文章 |
| **完整训练题组** | 主控 LLM 规划 4 篇文章方案 → 动态注入子任务 → 生成文章+题目全套 |
| **题目生成** | 为指定文章生成细节题/推理题/词义题/主旨题，含答案解析 |
| **智能问答** | 查词、长难句拆解、语法解释、翻译，支持 LangChain 工具调用访问记忆 |
| **错题本** | 持久化存储所有错题，支持关键词/题型/难度筛选 |
| **遗忘曲线** | SM-2 间隔重复算法，自动调度下次复习时间 |
| **训练记录** | 记录每次学习的文章数、正确率、用时、得分等 |
| **战力值历史** | 跟踪学生综合学习能力评分曲线 |
| **用户管理** | 邀请码注册、JWT 认证、密码修改、用户信息管理 |

---

## 2. 系统架构

```
用户请求
   │
   ▼
POST /api/attempt（异步）
   │
   ▼
Orchestrator（主控循环）
   ├── Planner：LLM 任务分解 → 生成 SubTask 列表
   ├── Dispatcher：按依赖顺序分发任务，注入记忆上下文
   │       ├── diagnosis_expert  → 错因分析 + 同类题生成
   │       ├── corpus_expert     → 文章生成（普通/规划/风格化）
   │       ├── question_expert   → 题目生成
   │       └── qa_expert         → 问答（LangChain 工具调用）
   └── Verifier：验证结果 → 通过则完成，失败则 Replan

GET /api/result/{request_id}  （轮询结果）
```

**记忆层（每次请求前 Dispatcher 自动注入）：**

```
WorkingMemory         ← 会话级（文章、题目、对话）
LongTermMemory        ← 用户级（错题本、遗忘曲线、训练记录、战力值）
CorpusRepo            ← 语料库（真题文章索引）
```

---

## 3. 项目结构

```
readwiseAI/
├── app/
│   ├── main.py                    # FastAPI 入口 (v0.2.0)
│   ├── auth/
│   │   ├── jwt_handler.py         # JWT 生成/验证（7天有效期）
│   │   ├── dependencies.py        # get_current_user / get_admin_user
│   │   ├── models.py              # 请求/响应 Pydantic 模型
│   │   └── password.py            # bcrypt 密码哈希
│   ├── api/routes/
│   │   ├── auth.py                # /api/auth/* 认证接口
│   │   ├── users.py               # /api/users/* 用户接口
│   │   ├── attempts.py            # POST /api/attempt
│   │   ├── results.py             # GET  /api/result/{id}
│   │   ├── memory.py              # /api/memory/* 长期记忆接口
│   │   ├── sessions.py            # /api/sessions/* 工作记忆接口
│   │   └── callback.py            # POST /internal/callback/{id}
│   ├── models/
│   │   ├── state.py               # OrchestratorState / SubTask / AttemptRequest
│   │   ├── user.py                # User + UserStore（JSON 文件存储）
│   │   ├── invite.py              # InviteCode + InviteStore
│   │   ├── working_memory.py      # WorkingMemory（会话级）
│   │   ├── long_term_memory.py    # LongTermMemory 聚合类
│   │   ├── mistakes.py            # MistakeEntry + MistakeBook
│   │   └── forgetting.py          # SM2Item + ForgettingCurve
│   ├── orchestrator/
│   │   ├── agent.py               # Orchestrator 主控循环 + 动态子任务注入
│   │   ├── planner.py             # Planner（LLM分解 + 规则fallback）
│   │   ├── verifier.py            # Verifier（结果验证）
│   │   ├── dispatcher.py          # Dispatcher（记忆注入 + 跨任务引用解析）
│   │   └── checkpoint.py          # 状态持久化（按用户隔离）
│   ├── services/
│   │   ├── llm_service.py         # LLM 调用封装（OpenAI/DeepSeek）
│   │   └── user_service.py        # 用户业务逻辑层
│   ├── sub_agents/
│   │   ├── base.py                # BaseSubAgent（含 load_prompt / _call_llm）
│   │   ├── diagnosis.py           # 错因分析 + 同类题生成
│   │   ├── corpus.py              # 文章生成（普通/规划/风格化）
│   │   ├── question.py            # 题目生成
│   │   └── qa.py                  # 问答（LangChain 工具调用）
│   └── tools/
│       ├── dictionary.py          # 有道词典 API
│       ├── grammar.py             # 语法规则库
│       ├── vocabulary.py          # 词汇等级
│       ├── constraints.py         # 难度约束
│       ├── corpus_repo.py         # 语料库检索
│       └── memory_tools.py        # LangChain @tool 集（6个工具）
├── admin_cli/                     # 管理员 CLI
│   └── commands/
│       ├── invite.py              # 邀请码管理
│       ├── user.py                # 用户管理
│       ├── memory.py              # 记忆管理
│       └── system.py              # 系统状态/备份/健康检查
├── admin.py                       # CLI 入口
├── tests/                         # 测试（pytest）
├── data/
│   ├── prompts/                   # Sub-agent 提示词文件（.txt，热更新）
│   ├── corpus/                    # 语料库（文章 + index.json）
│   ├── working/sessions/{user_id}/ # 工作记忆（按用户隔离）
│   ├── long_term/{user_id}/        # 长期记忆（按用户隔离）
│   │   ├── mistakes.json           # 错题本
│   │   ├── forgetting.json         # SM-2 遗忘曲线状态
│   │   ├── training.json           # 训练记录
│   │   └── power_history.json      # 战力值历史
│   ├── users/users.json            # 用户数据
│   ├── invites/invites.json        # 邀请码
│   └── request_index/              # request_id → user_id 映射
├── docs/
│   └── frontend_follow.md         # 前端开发文档（含所有 API 详情）
├── requirements.txt
└── pytest.ini
```

---

## 4. 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（开发时可跳过，使用默认值）
export JWT_SECRET_KEY="your-strong-secret-key"   # 生产必须设置
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 可选，支持代理

# 3. 创建管理员邀请码
python admin.py invite create --max-uses 10

# 4. 启动服务
uvicorn app.main:app --reload --port 8000
```

**访问 API 文档：**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 5. API 总览

> 🔐 = 需要 Bearer JWT Token（`Authorization: Bearer <token>`）

### 5.1 认证 API

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/auth/verify-invite` | 无 | 验证邀请码有效性 |
| POST | `/api/auth/register` | 无 | 用邀请码注册，返回 Token |
| POST | `/api/auth/login` | 无 | 用户名/手机/邮箱 + 密码登录 |
| POST | `/api/auth/logout` | 无 | 登出（客户端清除 Token） |
| POST | `/api/auth/refresh` | 🔐 | 刷新 Token（有效期内可刷新） |

### 5.2 用户 API

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET  | `/api/users/me` | 🔐 | 获取当前用户信息 |
| PUT  | `/api/users/me` | 🔐 | 更新用户名/地区/年级/学校 |
| PUT  | `/api/users/password` | 🔐 | 修改密码 |
| GET  | `/api/users/stats` | 🔐 | 获取统计（错题数、战力值等） |

### 5.3 答题 API

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/attempt` | 🔐 | 提交请求（异步），返回 request_id |
| GET  | `/api/result/{request_id}` | 🔐 | 轮询处理结果 |

### 5.4 长期记忆 API

#### 训练记录

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET  | `/api/memory/training` | 🔐 | 获取训练记录列表 |
| POST | `/api/memory/training` | 🔐 | 添加训练记录 |

#### 错题本

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET  | `/api/memory/mistakes` | 🔐 | 获取错题列表（支持筛选） |
| GET  | `/api/memory/mistakes/due` | 🔐 | 获取待复习错题 |
| GET  | `/api/memory/mistakes/{id}` | 🔐 | 获取单条错题详情 |
| POST | `/api/memory/mistakes` | 🔐 | 添加错题 |
| PUT  | `/api/memory/mistakes/{id}` | 🔐 | 更新错题字段 |
| DELETE | `/api/memory/mistakes/{id}` | 🔐 | 删除错题 |

#### 遗忘曲线（SM-2）

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET  | `/api/memory/curve` | 🔐 | 获取遗忘曲线概况 |
| GET  | `/api/memory/curve/due` | 🔐 | 获取待复习条目 |
| GET  | `/api/memory/curve/{item_id}` | 🔐 | 获取单条 SM-2 状态 |
| POST | `/api/memory/curve/{item_id}/review` | 🔐 | 提交复习质量（0-5） |

#### 战力值历史

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET  | `/api/memory/power` | 🔐 | 获取战力值历史 |
| POST | `/api/memory/power` | 🔐 | 添加战力值记录 |

### 5.5 会话 API

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET  | `/api/sessions` | 🔐 | 获取会话 ID 列表 |
| GET  | `/api/sessions/current` | 🔐 | 获取最近一次会话 |
| GET  | `/api/sessions/{id}` | 🔐 | 获取会话完整数据 |
| GET  | `/api/sessions/{id}/articles` | 🔐 | 获取会话中的文章 |
| GET  | `/api/sessions/{id}/questions` | 🔐 | 获取会话中的题目 |
| GET  | `/api/sessions/{id}/history` | 🔐 | 获取对话历史 |
| GET  | `/api/sessions/{id}/agent-info` | 🔐 | 获取 Agent 运行信息 |
| DELETE | `/api/sessions/{id}` | 🔐 | 删除会话 |

### 5.6 内部 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/internal/callback/{request_id}` | Sub-agent 完成回调（内部使用） |

---

## 6. request_type 说明

`POST /api/attempt` 的 `request_type` 字段决定 AI 执行何种任务：

| request_type | 功能 | 主要输入字段 |
|-------------|------|------------|
| `attempt` | 错题诊断 + 同类题 | `paragraph`, `question_text`, `options`, `user_answer`, `correct_answer`, `time_spent` |
| `corpus` | 生成单篇文章 | `difficulty`(L1-L4), `genre`, `topic`, `word_count`, `reference_id` |
| `question` | 为文章出题 | `article`, `question_types`, `difficulty`, `count` |
| `qa` | 问答辅导 | `query_type`(word/sentence/grammar/translate/free), `content`, `context_sentence` |
| `training_set` | 完整训练题组（4篇文章+题目） | `user_level` |

**示例 – 提交错题分析：**

```json
POST /api/attempt
{
  "request_type": "attempt",
  "session_id": "session_001",
  "paragraph": "Scientists have found that...",
  "question_text": "What is the main idea of the passage?",
  "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
  "user_answer": "A",
  "correct_answer": "C",
  "time_spent": 45,
  "question_number": "A1"
}
```

**示例 – 生成完整训练题组：**

```json
POST /api/attempt
{
  "request_type": "training_set",
  "session_id": "session_train_001",
  "user_level": "L2"
}
```

> 详细字段说明及所有场景示例参见 [`docs/frontend_follow.md`](docs/frontend_follow.md)。

---

## 7. Sub-Agent 说明

### DiagnosisExpert（错因分析专家）

- **输入**：paragraph、question_text、options、user_answer、correct_answer、time_spent
- **输出**：error_category（错误类型）、explanation（错因分析）、evidence_sentence（证据句）、suggestion（学习建议）+ similar_question（同类题）
- **错误类型**：词汇理解 / 推理判断 / 细节查找 / 主旨理解 / 其他

### CorpusExpert（语料生成专家）

三种工作模式：

1. **普通模式**：按 difficulty/genre/topic 生成文章
2. **规划模式**（`enable_planning=True`）：读取语料库 + 用户错题/战力值，规划4篇文章方案，自动注入子任务
3. **风格化模式**（`reference_id` 指定）：以真题为风格参考生成文章

生成文章后自动同步到 WorkingMemory。

### QuestionExpert（出题专家）

- 支持批量出题（一次请求生成多道题）
- 题型：detail（细节题）/ inference（推理题）/ vocabulary（词义题）/ main_idea（主旨题）
- 支持跨任务引用：`article_task_id` 自动从 CorpusExpert 结果中读取文章

### QAExpert（问答专家）

- 结构化模式：word / sentence / grammar / translate
- 自由模式（`free`）：通过 LangChain 工具调用自主访问工作记忆、错题本、语料库

---

## 8. 记忆系统设计

### 工作记忆（WorkingMemory）

- 存储位置：`data/working/sessions/{user_id}/{session_id}.json`
- 会话类型：`training`（学习）/ `chatting`（聊天）
- 内容：articles（文章列表）、question_queue（题目队列）、conversation_history（对话历史）、agent_information（Agent 运行信息）
- 每次 Dispatcher 执行任务前自动加载注入

### 长期记忆（LongTermMemory）

存储位置：`data/long_term/{user_id}/`

| 文件 | 内容 |
|------|------|
| `mistakes.json` | 错题本（MistakeEntry 数组） |
| `forgetting.json` | SM-2 遗忘曲线状态（item_id → SM2Item） |
| `training.json` | 训练记录历史 |
| `power_history.json` | 战力值历史 |

**SM-2 算法说明：**

quality 0–5 对应复习质量（5=完美，0=完全遗忘），算法自动调整：
- `easiness`（难度因子，初始 2.5，最小 1.3）
- `interval_days`（下次复习间隔天数，连续成功后指数增长）
- `next_review_at`（下次复习时间戳）

### 安全设计

所有用户数据路径经过 `_safe_user_dir()` 验证：
- user_id 只允许字母数字、连字符、下划线
- 路径解析后校验在 base_dir 内，防止路径穿越攻击

---

## 9. 管理员 CLI

```bash
# 邀请码管理
python admin.py invite create --max-uses 5 --note "测试用"
python admin.py invite list
python admin.py invite revoke <code>

# 用户管理
python admin.py user list
python admin.py user disable <user_id>
python admin.py user enable <user_id>

# 记忆管理
python admin.py memory stats <user_id>

# 系统
python admin.py system health
python admin.py system stats
python admin.py system backup
```

---

## 10. 外部依赖

### LLM（OpenAI/DeepSeek）

- **使用场景**：所有 Sub-Agent 的推理输出、Planner 任务分解、Verifier 结果验证
- **调用方式**：`app/services/llm_service.py`，支持 `OPENAI_BASE_URL` 自定义（可接入 DeepSeek 等）
- **输出格式**：所有 LLM 调用均要求返回严格 JSON，异常自动捕获并 fallback

### 有道词典 API

- **使用场景**：QAExpert 查词（query_type=word）
- **封装**：`app/tools/dictionary.py`
- **说明**：不需要配置 Key，使用公开接口；LLM 作为补充释义

---

## 11. 配置与环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥（生产环境**必须**设置为强随机字符串） | 内置 dev 默认值（不安全） |
| `OPENAI_API_KEY` | OpenAI/DeepSeek API Key | 无（LLM 调用将失败） |
| `OPENAI_BASE_URL` | API 地址（支持代理/国内节点） | OpenAI 官方 URL |
| `OPENAI_MODEL` | 使用的模型名 | `gpt-4o` |

---

## 12. 测试

```bash
# 运行全部测试
python -m pytest tests/ -q

# 运行特定测试模块
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_memory.py -v
python -m pytest tests/test_agent.py -v
```

测试框架：`pytest` + `pytest-asyncio`（`asyncio_mode=auto`）

测试覆盖：JWT 认证、用户注册/登录/密码、错题本、遗忘曲线、工作记忆、Sub-Agent 集成。

---

## 前端开发

详细的接口文档（含所有字段说明、请求/响应示例、典型场景代码）请参见：

📄 **[docs/frontend_follow.md](docs/frontend_follow.md)**

---

---

## 13. POST /api/attempt 逐行代码分析与调用流程

> 本节对 `POST /api/attempt` 涉及的全部代码进行逐层分析，并给出完整调用链路图。

---

### 13.1 入口：路由层（app/api/routes/attempts.py）

```
路径：app/api/routes/attempts.py
注册：app/main.py → app.include_router(attempts.router, prefix="/api")
最终路径：POST /api/attempt
```

**逐行执行步骤：**

| 步骤 | 代码 | 说明 |
|------|------|------|
| 1 | `get_current_user(credentials)` | FastAPI Depends 自动触发，解析 Authorization 头中的 JWT Bearer Token |
| 2 | `token_data.user_id` | 从已验证 Token 中提取 user_id（前端不需要单独传） |
| 3 | `_generate_request_id()` | 生成 `req_` + 12位随机十六进制字符串，如 `req_a3f7c9b12d4e` |
| 4 | `session_id = attempt.session_id or "session_" + uuid...` | 使用前端传入的 session_id；若未传则自动生成 |
| 5 | `OrchestratorState(...)` | 创建初始状态对象（status=PENDING，含 original_request） |
| 6 | `checkpoint_manager.save(state)` | 将状态序列化为 JSON，写入 `data/users/{user_id}/checkpoints/{request_id}.json`；同时在 `data/request_index/{request_id}` 写入 user_id 实现所有权索引 |
| 7 | `background_tasks.add_task(orchestrator.process_request, ...)` | 注册后台任务，**立即返回响应**，实际处理异步进行 |
| 8 | 返回 `{request_id, session_id, status:"processing", result_url}` | 前端凭 request_id 轮询 GET /api/result/{request_id} |

**JWT 验证链（app/auth/dependencies.py → app/auth/jwt_handler.py）：**

- 从 Header 提取 Bearer token → `decode_token()` 验证签名和有效期 → 提取 `sub`（user_id）和 `role` → 返回 `TokenData`
- 失败路径：token 缺失 → 401 Missing；token 过期 → 401 Expired；无效 token → 401 Invalid

---

### 13.2 数据模型层（app/models/state.py）

**AttemptRequest**：接收前端 POST body，所有字段均为可选（除 session_id），以适应多种 request_type。

| 字段 | 类型 | 用于 request_type |
|------|------|------------------|
| `paragraph` / `question_text` / `options` / `user_answer` / `correct_answer` / `time_spent` | str/int/dict | `attempt` |
| `difficulty` / `genre` / `topic` / `word_count` / `reference_id` | str/int | `corpus` |
| `article` / `question_type` / `question_types` / `count` | str/list/int | `question` |
| `query_type` / `content` / `context_sentence` | str | `qa` |
| `user_level` / `enable_planning` | str/bool | `training_set` |
| `session_id` | str | 所有类型 |
| `question_number` | str | 可选，用于记忆跟踪（如 "A1"） |

**OrchestratorState**：贯穿整个处理生命周期的核心状态机对象。

```
status 枚举流转：
  PENDING → PLANNING → WAITING → (RETRY →) COMPLETED / FAILED
```

**SubTask**：每个子任务的数据结构，含 assigned_to、input、acceptance_criteria、depends_on、status、result。

---

### 13.3 状态持久化层（app/orchestrator/checkpoint.py）

| 操作 | 文件路径 | 触发时机 |
|------|----------|---------|
| `save(state)` | `data/users/{user_id}/checkpoints/{request_id}.json` | 路由层初始保存；Orchestrator 每次循环等待时保存 |
| `_write_index()` | `data/request_index/{request_id}` | 写入 user_id，用于所有权校验 |
| `save_result()` | `data/users/{user_id}/results/{request_id}.json` | 处理完成后写入最终结果 |
| `delete()` | 删除 checkpoints 中的文件 | 处理完成后清理中间状态 |
| `load_result()` | `data/users/{user_id}/results/{request_id}.json` | GET /api/result 轮询时读取 |

**安全性：** `_safe_user_dir()` 对 user_id 做正则校验（`^[\w\-]+$`）并用 `resolve().relative_to()` 防止路径穿越攻击。

---

### 13.4 Orchestrator 主控循环（app/orchestrator/agent.py）

`process_request()` 由 BackgroundTasks 调用，内部调用 `_run(state)`，最多循环 20 次：

```
迭代守卫：for _iteration in range(20)   # 防止无限循环

PENDING:
  → state.status = PLANNING
  → 调用 Planner.plan(state)
  → 若无 sub_tasks → FAILED
  → state.status = WAITING

WAITING:
  → dispatcher.dispatch_all_pending(state)   # 分发所有可执行任务
  → 查找第一个"已完成但未验收"的任务
    → 若找到：verifier.verify(state, task)
      → 验收通过：inject_new_tasks() + 检查全部完成
      → 验收失败可重试：state.status = RETRY
      → 超出重试上限：task.status = FAILED
    → 若未找到：
      → 所有任务完成 → 设置 COMPLETED / FAILED
      → 否则 → 保存 checkpoint，等待回调

RETRY:
  → planner.replan(state, failed_task)   # 调整失败任务输入
  → state.status = WAITING              # 继续主循环

COMPLETED / FAILED:
  → break，退出循环

→ _finalize(state):
     _assemble_result() → checkpoint.save_result() → checkpoint.delete()
```

**动态子任务注入（`_inject_new_tasks`）：**
- 检查 `completed_task.result["new_sub_tasks"]`
- 过滤掉已存在 sub_task_id
- 将新 SubTask 追加到 `state.sub_tasks`
- 主要由 CorpusExpert 规划模式触发（training_set 场景）

---

### 13.5 Planner（app/orchestrator/planner.py）

**主要职责：** 将 `original_request` 分解为 SubTask 列表。

**执行路径：**
1. 构建 `PLANNING_PROMPT`（中文系统提示 + 用户请求 JSON + 上下文），调用 `llm_json_call()`
2. 若 LLM 失败/返回空，退回规则分发（`_make_rule_based_plan()`）
3. 规则分发逻辑：

| request_type | 生成的 SubTask |
|---|---|
| `attempt` | 1个 diagnosis_expert 任务，input 包含题目所有字段 |
| `corpus` | 1个 corpus_expert 任务，input 包含 difficulty/genre/topic 等 |
| `question` | 1个 question_expert 任务，input 包含 article/question_types/count |
| `qa` | 1个 qa_expert 任务，input 包含 query_type/content/context_sentence |
| `training_set` | 1个 corpus_expert 任务，input 中 `enable_planning=true` |

**Replan（`replan()`）：**
- 将失败原因（error_log 最后一条）传给 LLM，要求输出调整后的任务 input JSON
- 重置 task.status = PENDING，task.retry_count += 1

---

### 13.6 Dispatcher（app/orchestrator/dispatcher.py）

**主要职责：** 按依赖顺序执行 SubTask，在执行前注入记忆上下文。

**`dispatch_all_pending(state)` 流程：**

```
for each task in state.sub_tasks:
  if task.status != PENDING: continue
  if not _deps_satisfied(task, state): continue   # 检查 depends_on 依赖
  await _execute_task(task, state)
```

**记忆上下文注入（`_build_memory_context(state)`）：**

| context key | 来源 | 说明 |
|---|---|---|
| `working_memory` | `WorkingMemory.get_or_create(session_id, user_id)` | 加载 `data/working/sessions/{user_id}/{session_id}.json` |
| `long_term_memory` | `LongTermMemory(user_id)` | 聚合 mistakes / forgetting / training / power_history |
| `corpus_repo` | `get_corpus_repo()` | 全局语料库单例（corpus/index.json） |
| `user_id` | `state.user_id` | 从 JWT 提取的 user_id |
| `completed_results` | `state.completed_results` | 已完成任务结果（供跨任务引用） |

**跨任务输入解析（`_resolve_task_inputs(task, state)`）：**
- 若 task.input 中有 `article_task_id`，从 `state.completed_results[article_task_id]["article"]["content"]` 提取文章内容
- 用于 question_expert 依赖 corpus_expert 输出的场景

**执行异常处理：**
- 未知 agent name → task.status = FAILED，记录 error_log
- agent.execute() 抛异常 → task.status = FAILED，记录异常信息

---

### 13.7 Sub-Agent 层

#### DiagnosisExpert（app/sub_agents/diagnosis.py）

**适用 request_type：** `attempt`

**执行步骤：**

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `_analyze_error(input, state)` | 若 user_answer == correct_answer，直接返回"无错误"；否则用 DIAGNOSIS_PROMPT 调用 LLM，输出 error_category / explanation / evidence_sentence / suggestion / confidence |
| 2 | `WorkingMemory.add_agent_information()` | 将诊断结果存入会话记忆（key: `diagnosis_{question_number}`） |
| 3 | `_generate_similar(input, diagnosis, state)` | 用 SIMILAR_QUESTION_PROMPT 调用 LLM，生成同类型练习题（可通过 `need_similar=false` 跳过） |
| 4 | `WorkingMemory.add_agent_information()` | 将同类题存入会话记忆（key: `similar_question`） |

**输出结构：**
```json
{
  "diagnosis": {
    "error_category": "词汇理解 | 推理判断 | 细节查找 | 主旨理解 | 其他",
    "explanation": "详细错因分析文本",
    "evidence_sentence": "原文中的关键证据句",
    "suggestion": "针对性学习建议",
    "confidence": 0.0
  },
  "similar_question": {
    "paragraph": "新阅读段落（英文）",
    "question": "题目",
    "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
    "correct_answer": "A",
    "explanation": "答案解析"
  },
  "metadata": { "latency_ms": 1200, "agent": "diagnosis_expert" }
}
```

#### CorpusExpert（app/sub_agents/corpus.py）

**三种模式：**

**模式 1：规划模式（`enable_planning=true`，用于 training_set）**
1. 加载语料库元数据（corpus_repo）
2. 加载用户错题摘要 + 战力值历史（long_term_memory）
3. 调用 LLM 生成训练方案（training_plan，含4篇文章规格）
4. `_build_training_sub_tasks()` 生成8个动态子任务：
   - `dyn_c1~c4`：4个 corpus_expert 任务（生成文章）
   - `dyn_q1~q4`：4个 question_expert 任务（各依赖对应的 dyn_cN）
5. 返回 `training_plan + new_sub_tasks`（Orchestrator 自动注入这8个任务）

**模式 2：风格化模式（`reference_id` 指定真题 ID）**
1. 从 corpus_repo 加载指定文章作为风格参考
2. 调用 LLM 按参考风格生成新文章（最多3次重试）
3. 验证文章（词数、标题等）
4. 调用 `_sync_working_memory()` 将文章写入 WorkingMemory

**模式 3：普通模式**
- 按 difficulty / genre / topic 生成文章，流程同模式2（跳过风格加载）

**普通/风格化模式输出：**
```json
{
  "article": {
    "title": "文章标题",
    "content": "正文（英文）",
    "word_count": 305,
    "difficulty_actual": "L2",
    "genre_actual": "expository",
    "key_vocabulary": ["word1", "word2"],
    "grammar_highlights": ["highlight1"]
  },
  "validation": { "passed": true, "issues": [] },
  "metadata": { "attempts": 1, "latency_ms": 2300 }
}
```

#### QuestionExpert（app/sub_agents/question.py）

**适用 request_type：** `question`，以及 training_set 场景中的 `dyn_q*` 动态任务

**执行步骤：**
1. 从 context["corpus_repo"] 获取语料库样例（风格参考）
2. 读取 `article`（来自 task.input 或跨任务解析的 article_task_id）
3. 确定题型列表：优先 `question_types`，其次 `question_type`，默认 `[detail, inference, vocabulary]`
4. 单次 LLM 调用，一次性生成所有 count 道题目（QUESTION_PROMPT）

**输出结构：**
```json
{
  "questions": [
    {
      "question_text": "...",
      "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
      "correct_answer": "B",
      "explanation": "...",
      "evidence": "原文证据句",
      "type": "detail | inference | vocabulary | main_idea"
    }
  ],
  "metadata": { "latency_ms": 1800, "agent": "question_expert", "count": 3 }
}
```

#### QAExpert（app/sub_agents/qa.py）

**适用 request_type：** `qa`

**按 query_type 分发：**

| query_type | 处理函数 | 行为 |
|---|---|---|
| `word` | `_handle_word()` | 有道词典 API 查词 → LLM 补充上下文含义 |
| `sentence` | `_handle_sentence()` | LLM 长难句拆解（主从句、修饰结构） |
| `grammar` | `_handle_grammar()` | LLM 语法规则解释（结合 grammar.py 规则库） |
| `translate` | `_handle_translate()` | LLM 英译中，保留语义和语气 |
| `free`（有记忆） | `_handle_free_with_tools()` | LangChain 工具调用循环（最多5轮），可访问6种记忆工具 |
| `free`（无记忆） | `_handle_free_simple()` | 直接 LLM 问答 |

**`_handle_free_with_tools()` 的6个 LangChain 工具（app/tools/memory_tools.py）：**

| 工具名 | 功能 |
|---|---|
| `get_current_article` | 获取当前 WorkingMemory 中的文章 |
| `get_conversation_history` | 获取当前会话对话历史 |
| `get_mistake_summary` | 获取用户错题摘要 |
| `get_power_history` | 获取战力值历史 |
| `get_training_records` | 获取训练记录 |
| `search_corpus` | 在语料库中搜索相关文章 |

---

### 13.8 Verifier（app/orchestrator/verifier.py）

**触发时机：** 每当有 SubTask 完成（status=COMPLETED）但尚未加入 state.completed_results 时触发。

**流程：**
1. 格式化 acceptance_criteria 为文本
2. 构建 VERIFICATION_PROMPT，调用 `llm_json_call()`
3. LLM 失败时 fallback：默认 passed=true，避免卡死流程
4. 验收通过（passed=true）：将 task.result 写入 `state.completed_results[task_id]`
5. 验收失败 + retry_count < 2：task.status = RETRY，state.retry_count += 1，记录 issues
6. 验收失败 + retry_count >= 2：task.status = FAILED，记录最终失败

---

### 13.9 LLM 服务层（app/services/llm_service.py）

所有 LLM 调用均通过 `llm_json_call(prompt)` 统一入口：

| 条件 | 行为 |
|---|---|
| 设置了 `OPENAI_API_KEY` | 使用 OpenAI API（ChatOpenAI） |
| 设置了 `DEEPSEEK_API_KEY` | 使用 DeepSeek（兼容 OpenAI 接口） |
| 均未设置 | 使用 _StubLLM（返回空 dict，流程降级） |
| LLM 响应含 Markdown 代码块 | 自动剥离 ``` 标记再解析 JSON |
| 响应非合法 JSON | 捕获 JSONDecodeError，返回 `{}` |
| 网络/API 异常 | 捕获所有 Exception，返回 `{}` |

---

### 13.10 完整调用链路图

```
CLIENT
  │
  │  POST /api/attempt
  │  Authorization: Bearer <jwt>
  │  Body: { request_type, session_id, ...fields }
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ app/api/routes/attempts.py :: submit_attempt()                  │
│                                                                 │
│  1. get_current_user()  ──►  app/auth/dependencies.py           │
│     └─ decode_token()   ──►  app/auth/jwt_handler.py            │
│        → 提取 user_id                                           │
│                                                                 │
│  2. AttemptRequest.model_dump()  → 请求字典                     │
│  3. OrchestratorState(status=PENDING)  → 初始状态               │
│  4. checkpoint_manager.save(state)                              │
│     └─ 写 data/users/{user_id}/checkpoints/{request_id}.json    │
│     └─ 写 data/request_index/{request_id}  (→ user_id)         │
│  5. background_tasks.add_task(orchestrator.process_request)     │
│                                                                 │
│  → 立即返回 { request_id, session_id, status, result_url }      │
└─────────────────────────────────────────────────────────────────┘
  │ (后台异步)
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ app/orchestrator/agent.py :: Orchestrator._run(state)           │
│                                                                 │
│  ┌── PENDING ──────────────────────────────────────────────┐   │
│  │  state.status = PLANNING                                │   │
│  │  planner.plan(state)  ──►  app/orchestrator/planner.py  │   │
│  │    1. llm_json_call(PLANNING_PROMPT)                    │   │
│  │       ──►  app/services/llm_service.py                  │   │
│  │    2. fallback: _make_rule_based_plan()                 │   │
│  │       → 按 request_type 生成 SubTask 列表               │   │
│  │  state.status = WAITING                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌── WAITING ──────────────────────────────────────────────┐   │
│  │  dispatcher.dispatch_all_pending(state)                  │   │
│  │  ──►  app/orchestrator/dispatcher.py                     │   │
│  │                                                          │   │
│  │  for each PENDING task (依赖已满足):                     │   │
│  │    _resolve_task_inputs(task, state)                     │   │
│  │      → 解析 article_task_id 跨任务引用                   │   │
│  │    _build_memory_context(state):                         │   │
│  │      → WorkingMemory.get_or_create()                     │   │
│  │        ──►  app/models/working_memory.py                 │   │
│  │        └─ 读 data/working/sessions/{user_id}/{sid}.json  │   │
│  │      → LongTermMemory(user_id)                           │   │
│  │        ──►  app/models/long_term_memory.py               │   │
│  │        └─ 读 data/long_term/{user_id}/*.json             │   │
│  │      → get_corpus_repo()                                 │   │
│  │        ──►  app/tools/corpus_repo.py                     │   │
│  │    agent.execute(task.input, context, state):            │   │
│  │      ┌── diagnosis_expert ──────────────────────────┐   │   │
│  │      │  ──►  app/sub_agents/diagnosis.py             │   │
│  │      │  _analyze_error() → llm_json_call()           │   │
│  │      │  → WorkingMemory.add_agent_information()      │   │
│  │      │  _generate_similar() → llm_json_call()        │   │
│  │      │  → WorkingMemory.add_agent_information()      │   │
│  │      └──────────────────────────────────────────────┘   │   │
│  │      ┌── corpus_expert ─────────────────────────────┐   │   │
│  │      │  ──►  app/sub_agents/corpus.py                │   │
│  │      │  规划模式: llm → training_plan + new_sub_tasks │   │
│  │      │  普通/风格化: llm → article → WorkingMemory   │   │
│  │      └──────────────────────────────────────────────┘   │   │
│  │      ┌── question_expert ───────────────────────────┐   │   │
│  │      │  ──►  app/sub_agents/question.py              │   │
│  │      │  llm → questions 数组                         │   │
│  │      └──────────────────────────────────────────────┘   │   │
│  │      ┌── qa_expert ─────────────────────────────────┐   │   │
│  │      │  ──►  app/sub_agents/qa.py                    │   │
│  │      │  word → dictionary.py + llm                   │   │
│  │      │  free → LangChain 工具调用循环                 │   │
│  │      └──────────────────────────────────────────────┘   │   │
│  │                                                          │   │
│  │  verifier.verify(state, completed_task)                  │   │
│  │  ──►  app/orchestrator/verifier.py                       │   │
│  │    → llm_json_call(VERIFICATION_PROMPT)                  │   │
│  │    → passed=true: state.completed_results[id] = result   │   │
│  │    → passed=false: RETRY or FAILED                       │   │
│  │                                                          │   │
│  │  _inject_new_tasks(state, completed_task)                │   │
│  │    → 追加 new_sub_tasks 到 state.sub_tasks               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌── COMPLETED / FAILED ───────────────────────────────────┐   │
│  │  _finalize(state)                                        │   │
│  │    _assemble_result() → { request_id, status, results }  │   │
│  │    checkpoint.save_result(request_id, user_id, result)   │   │
│  │      └─ 写 data/users/{user_id}/results/{request_id}.json│   │
│  │    checkpoint.delete(request_id)                         │   │
│  │      └─ 删 data/users/{user_id}/checkpoints/...         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

CLIENT (轮询)
  │
  │  GET /api/result/{request_id}
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ app/api/routes/results.py :: get_result()                       │
│  1. get_current_user() → JWT 验证                               │
│  2. lookup_user_id(request_id) → 所有权校验                     │
│  3. load_result() → 读缓存结果（若已完成）                      │
│  4. load() → 读 checkpoint（若仍处理中）                        │
│  → 返回 { status: processing | completed | failed, ... }        │
└─────────────────────────────────────────────────────────────────┘
```

---

### 13.11 数据流总结

```
POST 请求 JSON
  └─ Pydantic AttemptRequest 验证
      └─ model_dump() → original_request dict
          └─ OrchestratorState（PENDING）
              └─ Planner → SubTask 列表
                  └─ Dispatcher：
                      ├─ 加载 WorkingMemory（会话记忆）
                      ├─ 加载 LongTermMemory（用户历史）
                      ├─ 加载 CorpusRepo（语料库）
                      └─ SubAgent.execute() → result dict
                          └─ Verifier 验收
                              └─ state.completed_results[task_id] = result
                                  └─ _assemble_result()
                                      └─ { request_id, status, results:{task_id: result,...} }
                                          └─ 写入 data/users/.../results/...json
                                              └─ GET /api/result 返回给客户端
```

---

### 13.12 已知问题与注意事项

| 问题 | 位置 | 说明 |
|------|------|------|
| 无用 import | `attempts.py` line 6 | `from pip._internal.network import session` 为无效导入，不影响功能但需清理 |
| pydantic.json 用法 | `diagnosis.py` line 10 | `from pydantic import json` 在 Pydantic v2 中已弃用，应改用 `import json` |
| session_id 非必填 | `AttemptRequest` | `session_id` 声明为 `str`（无默认值）但实际路由层处理 `attempt.session_id or ...`，前端建议始终传值 |
| LLM 降级无告警 | `verifier.py` | LLM 调用失败时默认 passed=true，静默通过，可能导致低质量结果流出 |
| Checkpoint 泄漏 | `checkpoint.py` | `data/request_index/` 的索引文件在 `delete()` 后不会删除，仅 checkpoint JSON 被删除 |
