# ReadWise AI

ReadWise AI 是一个基于 FastAPI 构建的智能英语学习系统，采用多 Agent 架构，为中国高考英语备考提供智能诊断、内容生成和问答支持。

---

## 目录

- [项目简介](#项目简介)
- [项目结构](#项目结构)
- [API 接口文档](#api-接口文档)
  - [认证接口](#认证接口)
  - [用户信息接口](#用户信息接口)
  - [POST /api/attempt — 提交请求](#post-apiattempt--提交请求)
  - [GET /api/result/{request_id} — 查询结果](#get-apiresultrequest_id--查询结果)
  - [POST /internal/callback/{request_id} — 内部回调](#post-internalcallbackrequest_id--内部回调)
- [记忆管理模块](#记忆管理模块)
- [管理员命令行工具](#管理员命令行工具)
- [外部 API 调用分析](#外部-api-调用分析)
  - [LLM API（OpenAI / DeepSeek）](#llm-apiopenai--deepseek)
  - [有道词典 API](#有道词典-api)
- [请求处理流程](#请求处理流程)
- [Sub-Agent 说明](#sub-agent-说明)
- [配置与环境变量](#配置与环境变量)
- [快速开始](#快速开始)

---

## 项目简介

**ReadWise AI** 的核心功能：

- **错误诊断**：分析学生英语阅读理解的错误，生成相似练习题。
- **语料生成**：按难度（L1–L4）和体裁（议论文/说明文/记叙文）生成高质量英文文章。
- **题目生成**：根据文章生成高考风格选择题及解析。
- **智能问答**：支持单词查询、句子解析、语法讲解和翻译，通过 LangChain 工具自主访问记忆。
- **用户管理**：基于邀请码的注册系统，JWT 身份认证，用户名+密码登录，密码修改，用户信息管理。
- **记忆管理**：按用户隔离的工作记忆（会话级）和长期记忆（错题本、遗忘曲线）。

---

## 项目结构

```
readwiseAI/
├── app/
│   ├── main.py                    # FastAPI 应用入口（v0.2.0）
│   ├── auth/                      # 认证模块
│   │   ├── __init__.py
│   │   ├── jwt_handler.py         # JWT 生成/验证（PyJWT，7天有效期）
│   │   ├── dependencies.py        # FastAPI 依赖注入（get_current_user）
│   │   ├── models.py              # 认证请求/响应 Pydantic 模型
│   │   └── password.py            # bcrypt 密码哈希与验证
│   ├── api/routes/
│   │   ├── auth.py                # POST /api/auth/*（注册/登录/登出/刷新）
│   │   ├── users.py               # GET/PUT /api/users/*（用户信息）
│   │   ├── attempts.py            # POST /api/attempt
│   │   ├── results.py             # GET  /api/result/{request_id}
│   │   └── callback.py            # POST /internal/callback/{request_id}
│   ├── models/
│   │   ├── state.py               # Orchestrator 状态定义
│   │   ├── user.py                # User 数据模型 + UserStore（JSON文件存储）含 password_hash 字段
│   │   ├── invite.py              # InviteCode 数据模型 + InviteStore
│   │   ├── working_memory.py      # 会话级工作记忆（按 user_id/session_id 隔离）
│   │   ├── long_term_memory.py    # 用户长期记忆（错题、遗忘曲线、战力值）
│   │   ├── mistakes.py            # 错题本（MistakeEntry + MistakeBook）
│   │   └── forgetting.py         # SM-2 遗忘曲线算法
│   ├── orchestrator/
│   │   ├── agent.py               # Orchestrator 主控循环
│   │   ├── planner.py             # 任务分解（Planner）
│   │   ├── verifier.py            # 结果验证（Verifier）
│   │   ├── dispatcher.py          # 任务分发（注入工作记忆+长期记忆+语料库）
│   │   └── checkpoint.py          # 状态持久化
│   ├── services/
│   │   ├── llm_service.py         # LLM 调用封装
│   │   └── user_service.py        # 用户服务层（注册、登录、密码修改、CRUD、邀请码管理）
│   ├── sub_agents/
│   │   ├── base.py                # BaseSubAgent 抽象类（含 load_prompt()）
│   │   ├── diagnosis.py           # 错误诊断 Agent
│   │   ├── corpus.py              # 语料生成 Agent
│   │   ├── question.py            # 题目生成 Agent（支持连续出题）
│   │   └── qa.py                  # 问答 Agent（LangChain 工具调用）
│   └── tools/
│       ├── dictionary.py          # 有道词典 API 封装
│       ├── grammar.py             # 语法规则库
│       ├── vocabulary.py          # 词汇等级检查
│       ├── constraints.py         # 难度约束规则
│       ├── corpus_repo.py         # 语料库检索
│       └── memory_tools.py        # LangChain 记忆工具集（6个@tool函数）
├── admin_cli/                     # 管理员 CLI 模块
│   ├── __init__.py
│   ├── utils.py                   # 工具函数（表格输出、确认提示）
│   └── commands/
│       ├── invite.py              # 邀请码管理命令
│       ├── user.py                # 用户管理命令
│       ├── memory.py              # 记忆管理命令
│       └── system.py              # 系统统计/备份/健康检查
├── admin.py                       # 管理员 CLI 入口
├── tests/
│   ├── test_agent.py              # Agent 集成测试
│   ├── test_memory.py             # 记忆模块测试
│   ├── test_auth.py               # 认证模块测试
│   ├── test_user_service.py       # 用户服务测试
│   └── test_admin_cli.py          # 管理员 CLI 测试
├── data/
│   ├── prompts/                   # Sub-agent 提示词（.txt，热更新）
│   ├── corpus/                    # 语料库（文章 + index.json）
│   ├── working/sessions/{user_id}/# 工作记忆（按用户隔离）
│   ├── long_term/{user_id}/       # 长期记忆（按用户隔离）
│   ├── users/users.json           # 用户数据
│   ├── invites/invites.json       # 邀请码数据
│   └── results/                   # 最终结果存档
├── requirements.txt
├── pytest.ini
├── UserDesign.md                  # 用户与记忆管理模块构建任务书
├── MemoryDesign.md                # 记忆管理模块构建任务书
└── DesignRoof.md
```

---

## API 接口文档

### 认证接口

#### POST /api/auth/verify-invite — 验证邀请码

**认证：** 无

```json
// 请求
{ "invite_code": "ABC12345" }

// 响应
{ "valid": true, "message": "邀请码有效" }
```

#### POST /api/auth/register — 注册

**认证：** 无  
**说明：** 必须先持有有效邀请码，注册成功后返回 JWT Token。

```json
// 请求
{
    "invite_code": "ABC12345",
    "username": "张三",
    "password": "password123",
    "confirm_password": "password123",
    "exam_region": "全国I卷",
    "grade": "高三",
    "school": "示范高中"
}

// 响应 (201)
{
    "user_id": "uuid-xxxx",
    "username": "张三",
    "access_token": "eyJ...",
    "token_type": "bearer"
}
```

**密码规则：** 8–20 位，两次输入须一致。

#### POST /api/auth/login — 登录

**认证：** 无  
**说明：** 使用用户名（或手机号/邮箱）与密码登录，返回 JWT Token。

```json
// 请求
{
    "login_id": "张三",
    "password": "password123"
}

// 响应 (200)
{
    "user_id": "uuid-xxxx",
    "username": "张三",
    "access_token": "eyJ...",
    "token_type": "bearer"
}
```

#### POST /api/auth/logout — 登出

**认证：** 无（客户端清除 Token 即可）

#### POST /api/auth/refresh — 刷新 Token

**认证：** ✅ Bearer Token

```json
// 响应
{ "access_token": "eyJ...", "token_type": "bearer" }
```

---

### 用户信息接口

所有接口需要在 Header 中携带：`Authorization: Bearer <token>`

#### GET /api/users/me — 获取当前用户信息

```json
{
    "id": "uuid-xxxx",
    "username": "张三",
    "exam_region": "全国I卷",
    "grade": "高三",
    "school": "示范高中",
    "role": "user",
    "status": "active",
    "created_at": "2024-04-04T00:00:00",
    "last_login_at": "2024-04-04T12:00:00"
}
```

#### PUT /api/users/me — 更新用户信息

可修改字段：`username`、`exam_region`、`grade`、`school`

#### PUT /api/users/password — 修改密码

**认证：** ✅ Bearer Token

```json
// 请求
{
    "old_password": "oldPass12",
    "new_password": "newPass12",
    "confirm_password": "newPass12"
}

// 响应
{ "message": "密码修改成功，请重新登录" }
```

#### GET /api/users/stats — 获取用户统计

```json
{
    "user_id": "uuid-xxxx",
    "mistake_count": 15,
    "due_for_review": 3,
    "latest_power": 85.5,
    "power_records": 12
}
```

---

### POST /api/attempt — 提交请求

提交用户的学习请求，支持四种类型：错误诊断（`attempt`）、语料生成（`corpus`）、题目生成（`question`）、智能问答（`qa`）。

**请求方式：** `POST`  
**路径：** `/api/attempt`  
**认证：** 无（内测期间）  
**处理方式：** 异步（后台任务）

#### 请求体（JSON）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 用户 ID |
| `request_type` | string | ✅ | `attempt` / `corpus` / `question` / `qa` |
| `paragraph` | string | attempt | 阅读文段 |
| `question_text` | string | attempt | 题目内容 |
| `options` | object | attempt | 选项 `{"A": ..., "B": ..., "C": ..., "D": ...}` |
| `user_answer` | string | attempt | 学生作答 |
| `correct_answer` | string | attempt | 正确答案 |
| `time_spent` | int | attempt | 答题用时（秒） |
| `difficulty` | string | corpus/question | 难度等级 `L1` / `L2` / `L3` / `L4` |
| `genre` | string | corpus | 文章体裁 `argumentative` / `expository` / `narrative` |
| `topic` | string | corpus | 文章主题 |
| `word_count` | int | corpus | 目标字数 |
| `article` | string | question | 用于出题的完整文章 |
| `question_types` | array | question | 题型列表 `["detail", "inference", "vocabulary", "main_idea"]` |
| `count` | int | question | 生成题目数量 |
| `query_type` | string | qa | `word` / `sentence` / `grammar` / `translate` / `free` |
| `content` | string | qa | 查询内容 |
| `context_sentence` | string | qa（word） | 单词所在句子上下文 |
| `session_id` | string | 否 | 会话 ID（用于工作记忆） |

#### 响应示例

```json
{
    "request_id": "req_xxxxxxxxxxxxxx",
    "status": "processing",
    "result_url": "/api/result/req_xxxxxxxxxxxxxx"
}
```

---

### GET /api/result/{request_id} — 查询结果

轮询获取请求的处理状态和结果。

**请求方式：** `GET`  
**路径：** `/api/result/{request_id}`  
**认证：** 无

**完成响应：**
```json
{
    "request_id": "req_xxxxxxxxxxxxxx",
    "status": "completed",
    "results": {
        "sub_001": { ... }
    }
}
```

---

### POST /internal/callback/{request_id} — 内部回调

供 Sub-Agent 在异步完成任务后通知 Orchestrator，**仅供内部使用**。

---

## 记忆管理模块

### 存储路径规范

```
data/
├── prompts/                          # Sub-agent 提示词（热更新）
│   ├── diagnosis_prompt.txt
│   ├── corpus_prompt.txt
│   ├── question_prompt.txt
│   └── qa_prompt.txt
├── corpus/                           # 公共语料库
│   ├── articles/gk_2024_001.md       # 高考真题（Markdown格式）
│   └── index.json                    # 按难度/体裁索引
├── working/sessions/{user_id}/       # 工作记忆（按用户隔离）
│   └── {session_id}.json
├── long_term/{user_id}/              # 长期记忆（按用户隔离）
│   ├── mistakes.json                 # 错题本
│   ├── forgetting.json               # SM-2 遗忘曲线状态
│   ├── power_history.json            # 战力值历史
│   └── training.json                 # 训练记录
├── users/users.json                  # 用户数据
└── invites/invites.json              # 邀请码数据
```

### LangChain 记忆工具（问答专家可调用）

| 工具名 | 功能 | 使用场景 |
|--------|------|---------|
| `get_current_article` | 获取当前文章全文 | 学生问"文章里提到..." |
| `get_current_questions` | 获取当前题目列表 | 学生问"第几题..." |
| `search_mistakes` | 搜索错题本 | 学生问"我以前错过..." |
| `search_corpus` | 搜索语料库示例 | 需要真题风格参考时 |
| `lookup_word` | 查询单词释义 | 学生问某单词意思 |
| `get_grammar_rule` | 获取语法规则 | 学生问语法点用法 |

---

## 管理员命令行工具

独立命令行脚本，直接操作数据文件，无需启动 Web 服务。

```bash
# 邀请码管理
python admin.py invite create --max-uses 10 --note "北京内测"
python admin.py invite list
python admin.py invite show ABC12345
python admin.py invite revoke ABC12345

# 用户管理
python admin.py user list --status active
python admin.py user show <user_id>
python admin.py user disable <user_id>
python admin.py user enable <user_id>
python admin.py user update <user_id> --grade 高三 --school 示范中学
python admin.py user delete <user_id> --force

# 记忆管理
python admin.py memory list <user_id>
python admin.py memory export <user_id> --output backup.json
python admin.py memory import <user_id> --file backup.json
python admin.py memory clear <user_id> --confirm

# 系统管理
python admin.py stats
python admin.py backup --output backup_20240404.zip
python admin.py health
```

---

## 外部 API 调用分析

### LLM API（OpenAI / DeepSeek）

**用途：** 任务规划、结果验证、内容生成（诊断/语料/题目/问答）

**调用位置：**

| 调用方 | 用途 |
|--------|------|
| `orchestrator/planner.py` | 将用户请求分解为子任务 |
| `orchestrator/verifier.py` | 验证子任务结果是否满足接受标准 |
| `sub_agents/diagnosis.py` | 生成错误分析报告和相似题 |
| `sub_agents/corpus.py` | 按难度和体裁生成英文文章 |
| `sub_agents/question.py` | 生成阅读理解选择题和解析 |
| `sub_agents/qa.py` | 解析句子、讲解语法、翻译内容、工具调用 |

**API 封装：** `app/services/llm_service.py`（基于 LangChain `ChatOpenAI`）

**配置切换：**

```
# 使用 OpenAI
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini       # 默认

# 使用 DeepSeek
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

---

### 有道词典 API

**用途：** 英语单词的中文释义和音标查询

**调用位置：** `app/tools/dictionary.py` → `lookup_word()`  
**触发条件：** QA Agent 处理 `query_type="word"` 请求时

| 属性 | 值 |
|------|-----|
| 接口地址 | `https://openapi.youdao.com/api` |
| 请求方式 | GET |
| 超时时间 | 10 秒 |

**错误处理：** 若未配置凭据，自动回退到桩实现。

---

## 请求处理流程

```
POST /api/attempt
       │
       ▼
  生成 request_id，保存 Checkpoint（PENDING）
       │
       ▼
  [后台任务] Orchestrator._run()  ← 最多 20 次迭代
       │
       ├── PENDING → PLANNING：Planner 分解任务为子任务列表
       │
       ├── WAITING → 执行：Dispatcher 调用 Sub-Agent
       │              ├── 注入工作记忆 + 长期记忆 + 语料库
       │              ├── Verifier 验证结果
       │              ├── 通过：标记子任务完成
       │              └── 失败：标记为 RETRY
       │
       ├── RETRY → 重规划：调整输入参数，重新执行（最多重试 2 次）
       │
       └── COMPLETED / FAILED：持久化最终结果
              │
              ▼
       GET /api/result/{request_id}  ← 客户端轮询
```

**请求状态枚举：** `PENDING` → `PLANNING` → `WAITING` → `RETRY` → `COMPLETED` / `FAILED`

---

## Sub-Agent 说明

| Agent | 模块 | 功能 |
|-------|------|------|
| `diagnosis_expert` | `sub_agents/diagnosis.py` | 错误分析、相似题生成 |
| `corpus_expert` | `sub_agents/corpus.py` | 英文文章生成（L1–L4 难度，3 种体裁） |
| `question_expert` | `sub_agents/question.py` | 阅读理解题目生成（支持连续出多题） |
| `qa_expert` | `sub_agents/qa.py` | 单词查询（有道）、句子解析、语法讲解、翻译、LangChain 工具调用 |

所有 Sub-Agent 继承自 `BaseSubAgent`，通过 `load_prompt(name)` 加载提示词文件，通过 `_call_llm(prompt)` 调用 LLM。

---

## 配置与环境变量

| 环境变量 | 说明 | 必填 |
|----------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key | 与 DeepSeek 二选一 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 与 OpenAI 二选一 |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | 使用 DeepSeek 时必填 |
| `LLM_MODEL` | 模型名称，默认 `gpt-4o-mini` | 否 |
| `YOUDAO_APP_KEY` | 有道词典应用 ID | 否（缺失时单词查询降级） |
| `YOUDAO_APP_SECRET` | 有道词典应用密钥 | 否（缺失时单词查询降级） |
| `JWT_SECRET_KEY` | JWT 签名密钥 | **生产环境必填** |

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export OPENAI_API_KEY=sk-...
export JWT_SECRET_KEY=your-secret-key-change-in-production
export YOUDAO_APP_KEY=...
export YOUDAO_APP_SECRET=...

# 生成内测邀请码
python admin.py invite create --max-uses 10 --note "内测用户"

# 启动服务
uvicorn app.main:app --reload

# 运行测试
pytest
```

**示例：注册新用户**

```bash
# 1. 验证邀请码
curl -X POST http://localhost:8000/api/auth/verify-invite \
  -H "Content-Type: application/json" \
  -d '{"invite_code": "ABC12345"}'

# 2. 注册
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "invite_code": "ABC12345",
    "username": "张三",
    "exam_region": "全国I卷",
    "grade": "高三"
  }'
```

**示例：提交错误诊断请求**

```bash
curl -X POST http://localhost:8000/api/attempt \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "student_001",
    "request_type": "attempt",
    "paragraph": "The industrial revolution changed society...",
    "question_text": "What is the main idea of this passage?",
    "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
    "user_answer": "A",
    "correct_answer": "C",
    "time_spent": 45
  }'
```

**示例：查询处理结果**

```bash
curl http://localhost:8000/api/result/req_xxxxxxxxxxxxxx
```
