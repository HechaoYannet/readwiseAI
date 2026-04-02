# ReadWise AI

ReadWise AI 是一个基于 FastAPI 构建的智能英语学习系统，采用多 Agent 架构，为中国高考英语备考提供智能诊断、内容生成和问答支持。

---

## 目录

- [项目简介](#项目简介)
- [项目结构](#项目结构)
- [API 接口文档](#api-接口文档)
  - [POST /api/attempt — 提交请求](#post-apiattempt--提交请求)
  - [GET /api/result/{request_id} — 查询结果](#get-apiresultrequest_id--查询结果)
  - [POST /internal/callback/{request_id} — 内部回调](#post-internalcallbackrequest_id--内部回调)
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
- **智能问答**：支持单词查询、句子解析、语法讲解和翻译。

---

## 项目结构

```
readwiseAI/
├── app/
│   ├── main.py                    # FastAPI 应用入口
│   ├── api/routes/
│   │   ├── attempts.py            # POST /api/attempt
│   │   ├── results.py             # GET  /api/result/{request_id}
│   │   └── callback.py            # POST /internal/callback/{request_id}
│   ├── models/
│   │   └── state.py               # 数据模型定义
│   ├── orchestrator/
│   │   ├── agent.py               # Orchestrator 主控循环
│   │   ├── planner.py             # 任务分解（Planner）
│   │   ├── verifier.py            # 结果验证（Verifier）
│   │   ├── dispatcher.py          # 任务分发与执行
│   │   └── checkpoint.py          # 状态持久化
│   ├── services/
│   │   └── llm_service.py         # LLM 调用封装
│   ├── sub_agents/
│   │   ├── base.py                # BaseSubAgent 抽象类
│   │   ├── diagnosis.py           # 错误诊断 Agent
│   │   ├── corpus.py              # 语料生成 Agent
│   │   ├── question.py            # 题目生成 Agent
│   │   └── qa.py                  # 问答 Agent
│   └── tools/
│       ├── dictionary.py          # 有道词典 API 封装
│       ├── grammar.py             # 语法规则库
│       ├── vocabulary.py          # 词汇等级检查
│       └── constraints.py         # 难度约束规则
├── tests/
│   └── test_agent.py
├── data/
│   ├── checkpoints/               # 请求状态存档（处理中）
│   └── results/                   # 最终结果存档（完成后）
├── requirements.txt
├── pytest.ini
└── DesignRoof.md
```

---

## API 接口文档

### POST /api/attempt — 提交请求

提交用户的学习请求，支持四种类型：错误诊断（`attempt`）、语料生成（`corpus`）、题目生成（`question`）、智能问答（`qa`）。

**请求方式：** `POST`  
**路径：** `/api/attempt`  
**认证：** 无  
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
| `question_type` | string | question | `detail` / `inference` / `vocabulary` |
| `count` | int | question | 生成题目数量 |
| `query_type` | string | qa | `word` / `sentence` / `grammar` / `translate` |
| `content` | string | qa | 查询内容 |
| `context_sentence` | string | qa（word） | 单词所在句子上下文 |

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

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | 由 `/api/attempt` 返回的请求 ID |

#### 响应示例

**处理中：**
```json
{
    "request_id": "req_xxxxxxxxxxxxxx",
    "status": "processing"
}
```

**完成：**
```json
{
    "request_id": "req_xxxxxxxxxxxxxx",
    "status": "completed",
    "results": {
        "sub_001": { ... }
    }
}
```

**失败：**
```json
{
    "request_id": "req_xxxxxxxxxxxxxx",
    "status": "failed",
    "error_log": ["错误信息 1", "错误信息 2"]
}
```

**未找到：**
```json
{
    "status": "not_found"
}
```

---

### POST /internal/callback/{request_id} — 内部回调

供 Sub-Agent 在异步完成任务后通知 Orchestrator，**仅供内部使用**，不对外暴露。

**请求方式：** `POST`  
**路径：** `/internal/callback/{request_id}`

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `request_id` | string | Orchestrator 的请求 ID |

#### 请求体（JSON）

```json
{
    "task_id": "sub_001",
    "result": { ... }
}
```

#### 响应

```json
{ "status": "ok" }
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
| `sub_agents/qa.py` | 解析句子、讲解语法、翻译内容 |

**API 封装：** `app/services/llm_service.py`（基于 LangChain `ChatOpenAI`）

**认证方式：** Bearer Token（API Key）

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

**请求特征：**
- 每个用户请求会触发多次 LLM 调用（规划阶段 1 次 + 每个子任务 1–2 次）
- 结果以纯文本返回，解析为 JSON
- 若未配置 API Key，自动回退到桩（stub）实现

---

### 有道词典 API

**用途：** 英语单词的中文释义和音标查询

**调用位置：** `app/tools/dictionary.py` → `lookup_word()`  
**触发条件：** QA Agent 处理 `query_type="word"` 请求时

**接口详情：**

| 属性 | 值 |
|------|-----|
| 接口地址 | `https://openapi.youdao.com/api` |
| 请求方式 | GET |
| 超时时间 | 10 秒 |

**请求参数：**

| 参数 | 说明 |
|------|------|
| `q` | 查询单词 |
| `from` | 源语言：`en` |
| `to` | 目标语言：`zh-CHS` |
| `appKey` | 应用 ID（`YOUDAO_APP_KEY`） |
| `salt` | 时间戳（毫秒） |
| `sign` | HMAC-SHA256 签名 |
| `signType` | 签名版本：`v3` |
| `curtime` | 当前时间戳（秒） |

**签名算法（`signType=v3`）：**

```
签名字符串 = appKey + truncate(q) + salt + curtime + appSecret
sign = SHA256(签名字符串).hexdigest()

truncate(q):
  若 len(q) <= 20，返回 q
  否则返回 q[:10] + str(len(q)) + q[-10:]
```

**响应结构：**

```json
{
    "errorCode": "0",
    "basic": {
        "phonetic": "wɜːrd",
        "explains": ["n. 单词；话语", "v. 用词表达"]
    },
    "web": [
        { "value": ["word processing", "文字处理"] }
    ]
}
```

**错误处理：** `errorCode != "0"` 或请求异常时，返回空结果；若未配置凭据，自动回退到桩实现。

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
       ├── WAITING → 执行：Dispatcher 调用 Sub-Agent，Verifier 验证结果
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
| `question_expert` | `sub_agents/question.py` | 阅读理解题目生成（细节/推断/词义） |
| `qa_expert` | `sub_agents/qa.py` | 单词查询（有道）、句子解析、语法讲解、翻译 |

所有 Sub-Agent 继承自 `BaseSubAgent`，通过 `_call_llm(prompt)` 调用 LLM，由 Dispatcher 同步执行(仅内测期间)。

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

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export OPENAI_API_KEY=sk-...
export YOUDAO_APP_KEY=...
export YOUDAO_APP_SECRET=...

# 启动服务
uvicorn app.main:app --reload

# 运行测试
pytest
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
