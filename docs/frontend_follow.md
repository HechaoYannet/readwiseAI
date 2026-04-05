# ReadWise AI – 前端开发文档

> 本文档面向前端开发者，涵盖认证流程、所有 API 端点的请求/响应格式、错误规范及常见开发场景。

---

## 目录

1. [基础信息](#1-基础信息)
2. [认证机制](#2-认证机制)
3. [Auth API – 认证与注册](#3-auth-api--认证与注册)
4. [Users API – 用户管理](#4-users-api--用户管理)
5. [Attempt API – 提交答题](#5-attempt-api--提交答题)
6. [Result API – 轮询结果](#6-result-api--轮询结果)
7. [Memory API – 长期记忆](#7-memory-api--长期记忆)
   - [训练记录](#71-训练记录)
   - [错题本](#72-错题本)
   - [遗忘曲线（SM-2）](#73-遗忘曲线sm-2)
   - [战力值历史](#74-战力值历史)
8. [Sessions API – 工作记忆会话](#8-sessions-api--工作记忆会话)
9. [错误码规范](#9-错误码规范)
10. [典型开发场景示例](#10-典型开发场景示例)
11. [request_type 速查表](#11-request_type-速查表)
12. [环境变量与部署](#12-环境变量与部署)
13. [POST /api/attempt 深度分析与调用流程](#13-post-apiattempt-深度分析与调用流程)

---

## 1. 基础信息

| 项目       | 值                                  |
|-----------|-------------------------------------|
| 基础 URL   | `http://localhost:8000`             |
| API 前缀   | `/api`                              |
| 内部前缀   | `/internal`                         |
| 数据格式   | `application/json`                  |
| 认证方式   | Bearer JWT（Authorization Header）  |
| 字符集     | UTF-8                               |

---

## 2. 认证机制

所有需要登录的接口都需要在 HTTP Header 中携带 JWT Token：

```http
Authorization: Bearer <access_token>
```

### Token 生命周期

- 有效期：**7 天**
- 建议在剩余有效期 **< 3 天** 时调用 `/api/auth/refresh` 刷新 Token
- Token 中包含 `user_id` 和 `role`（`user` 或 `admin`），无需额外传递

---

## 3. Auth API – 认证与注册

### 3.1 验证邀请码

**POST** `/api/auth/verify-invite`

```json
// Request
{ "invite_code": "INV-XXXX" }

// Response 200
{ "valid": true, "message": "邀请码有效" }

// Response 200 (invalid)
{ "valid": false, "message": "邀请码已过期" }
```

### 3.2 注册

**POST** `/api/auth/register`

```json
// Request
{
  "invite_code": "INV-XXXX",
  "username": "张三",
  "password": "password123",
  "confirm_password": "password123",
  "exam_region": "全国I卷",
  "grade": "高三",
  "school": "示范中学"
}

// Response 201
{
  "user_id": "uuid-...",
  "username": "张三",
  "access_token": "eyJ...",
  "token_type": "bearer"
}

// Response 400（注册失败）
{ "detail": "用户名已被占用" }
```

**字段说明：**
- `grade`、`school`：可选
- `password` 长度须为 8–20 位
- 注册成功后 Token 直接返回，无需再次登录

### 3.3 登录

**POST** `/api/auth/login`

```json
// Request（支持用户名/手机/邮箱登录）
{ "login_id": "张三", "password": "password123" }

// Response 200
{
  "user_id": "uuid-...",
  "username": "张三",
  "access_token": "eyJ...",
  "token_type": "bearer"
}

// Response 401
{ "detail": "用户名或密码错误" }
```

### 3.4 登出

**POST** `/api/auth/logout`

> 客户端丢弃 Token 即可。服务端无状态。

```json
// Response 200
{ "message": "已退出登录" }
```

### 3.5 刷新 Token

**POST** `/api/auth/refresh` `🔐 需要 Token`

```json
// Response 200
{ "access_token": "eyJ...", "token_type": "bearer" }
```

---

## 4. Users API – 用户管理

### 4.1 获取当前用户信息

**GET** `/api/users/me` `🔐`

```json
// Response 200
{
  "id": "uuid-...",
  "username": "张三",
  "exam_region": "全国I卷",
  "grade": "高三",
  "school": "示范中学",
  "role": "user",
  "status": "active",
  "created_at": "2025-01-01T00:00:00+00:00",
  "last_login_at": "2025-04-01T12:00:00+00:00"
}
```

### 4.2 更新用户信息

**PUT** `/api/users/me` `🔐`

```json
// Request（所有字段可选，传空字符串则不更新）
{
  "username": "新名字",
  "exam_region": "北京卷",
  "grade": "高二",
  "school": "某中学"
}

// Response 200 – 同 GET /me 格式
```

### 4.3 修改密码

**PUT** `/api/users/password` `🔐`

```json
// Request
{
  "old_password": "oldPass123",
  "new_password": "newPass456",
  "confirm_password": "newPass456"
}

// Response 200
{ "message": "密码修改成功，请重新登录" }

// Response 401（旧密码错误）
{ "detail": "旧密码错误" }
```

### 4.4 获取用户统计

**GET** `/api/users/stats` `🔐`

```json
// Response 200
{
  "user_id": "uuid-...",
  "mistake_count": 42,
  "due_for_review": 5,
  "latest_power": 1280.5,
  "power_records": 15
}
```

### 4.5 获取当前训练会话（废弃，建议用 Sessions API）

**GET** `/api/users/train/currSession` `🔐`

> ⚠️ 此接口已有更完善的替代方案：`GET /api/sessions/current`，建议使用新接口。

---

## 5. Attempt API – 提交答题

核心接口。提交用户的作答，系统在后台异步处理（AI 分析、生成文章、出题等）。

**POST** `/api/attempt` `🔐`

```json
// Request 通用字段
{
  "session_id": "session_abc123",    // 可选，不传则自动生成
  "request_type": "attempt",         // 见 §11 request_type 速查表
  // ...各 request_type 专属字段
}

// Response 200（立即返回，异步处理中）
{
  "request_id": "req_abc123456789",
  "session_id": "session_abc123",
  "status": "processing",
  "result_url": "/api/result/req_abc123456789"
}
```

各 `request_type` 的专属字段请参见 [§11 request_type 速查表](#11-request_type-速查表)。

---

## 6. Result API – 轮询结果

**GET** `/api/result/{request_id}` `🔐`

> 建议每 **2–3 秒**轮询一次，处理时间通常为 3–15 秒（取决于 AI 响应速度）。

```json
// 处理中
{ "request_id": "req_...", "status": "processing" }

// 完成
{
  "request_id": "req_...",
  "status": "completed",
  "results": {
    "sub_001": {
      // 根据 request_type 不同，results 结构不同，详见各场景示例
    }
  }
}

// 失败
{
  "request_id": "req_...",
  "status": "failed",
  "error_log": ["错误原因..."]
}

// 未找到（request_id 无效或已过期）
{ "status": "not_found" }
```

**HTTP 状态码：**
- `200` – 正常（包括 processing / not_found）
- `403` – 请求属于其他用户，禁止访问

---

## 7. Memory API – 长期记忆

所有接口均需 `🔐` Token，且只能访问当前用户自己的数据。

### 7.1 训练记录

#### 获取训练记录列表

**GET** `/api/memory/training?limit=20`

```json
// Response 200
{
  "user_id": "uuid-...",
  "total": 8,
  "records": [
    {
      "session_id": "session_xxx",
      "article_count": 4,
      "question_count": 16,
      "correct_count": 12,
      "total_time_seconds": 1800,
      "difficulty": "L2",
      "score": 75.0,
      "note": "第一次训练",
      "recorded_at": "2025-04-01T09:00:00"
    }
  ]
}
```

#### 添加训练记录

**POST** `/api/memory/training`

```json
// Request
{
  "session_id": "session_xxx",
  "article_count": 4,
  "question_count": 16,
  "correct_count": 12,
  "total_time_seconds": 1800,
  "difficulty": "L2",
  "score": 75.0,
  "note": "第一次正式训练"
}

// Response 201
{ "message": "训练记录已保存", "record": { ... } }
```

**字段说明（均可选）：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 关联的会话 ID |
| `article_count` | int | 本次训练文章数 |
| `question_count` | int | 总题目数 |
| `correct_count` | int | 答对题数 |
| `total_time_seconds` | int | 用时（秒） |
| `difficulty` | string | 难度级别 L1-L4 |
| `score` | float | 综合得分 |
| `note` | string | 备注 |

---

### 7.2 错题本

#### 获取错题列表

**GET** `/api/memory/mistakes`

| 查询参数 | 类型 | 说明 |
|---------|------|------|
| `keyword` | string | 关键词（搜索题目文本/文章摘要） |
| `error_category` | string | 错误类型（词汇理解/推理判断/细节查找/主旨理解） |
| `question_type` | string | 题型（detail/inference/vocabulary/main_idea） |
| `difficulty` | string | 难度（L1/L2/L3/L4） |
| `limit` | int | 返回条数，默认 20，最大 100 |

```json
// Response 200
{
  "user_id": "uuid-...",
  "total": 42,
  "returned": 20,
  "mistakes": [
    {
      "mistake_id": "mis_20250401_001",
      "question_text": "What is the main idea of the passage?",
      "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
      "correct_answer": "B",
      "user_answer": "A",
      "article_excerpt": "...",
      "error_category": "主旨理解",
      "explanation": "...",
      "question_type": "main_idea",
      "difficulty": "L3",
      "review_count": 2,
      "next_review_at": "2025-04-08T09:00:00",
      "created_at": "2025-04-01T09:00:00"
    }
  ]
}
```

#### 获取待复习错题

**GET** `/api/memory/mistakes/due?limit=10`

```json
// Response 200
{
  "user_id": "uuid-...",
  "due_count": 5,
  "mistakes": [ { /* 同上格式 */ } ]
}
```

#### 获取单条错题

**GET** `/api/memory/mistakes/{mistake_id}`

```json
// Response 200 – 单条错题对象
// Response 404 – { "detail": "错题不存在" }
```

#### 添加错题

**POST** `/api/memory/mistakes`

```json
// Request
{
  "mistake_id": "mis_20250401_001",
  "question_text": "What is the author's attitude?",
  "options": { "A": "Positive", "B": "Negative", "C": "Neutral", "D": "Uncertain" },
  "correct_answer": "A",
  "user_answer": "C",
  "article_excerpt": "The author enthusiastically argues...",
  "error_category": "推理判断",
  "explanation": "文章第二段关键词 enthusiastically 表明作者态度积极",
  "question_type": "inference",
  "difficulty": "L3"
}

// Response 201
{ "message": "错题已记录", "mistake_id": "mis_20250401_001" }
```

#### 更新错题

**PUT** `/api/memory/mistakes/{mistake_id}`

```json
// Request（仅传需要更新的字段）
{
  "review_count": 3,
  "next_review_at": "2025-04-10T09:00:00",
  "explanation": "更新后的解析..."
}

// Response 200
{ "message": "错题已更新", "mistake_id": "..." }
```

#### 删除错题

**DELETE** `/api/memory/mistakes/{mistake_id}`

```json
// Response 200
{ "message": "错题已删除", "mistake_id": "..." }

// Response 404
{ "detail": "错题不存在" }
```

---

### 7.3 遗忘曲线（SM-2）

SM-2 算法根据复习质量自动计算下次复习时间，quality 参数含义：

| quality | 含义 |
|---------|------|
| 5 | 完美记忆，毫不犹豫 |
| 4 | 正确，但有少许犹豫 |
| 3 | 经努力后正确（通过阈值） |
| 2 | 错误，但提示后想起来了 |
| 1 | 错误，正确答案看起来很简单 |
| 0 | 完全不记得 |

#### 获取遗忘曲线概况

**GET** `/api/memory/curve`

```json
// Response 200
{
  "user_id": "uuid-...",
  "total_items": 42,
  "due_count": 7
}
```

#### 获取待复习条目

**GET** `/api/memory/curve/due?limit=10`

```json
// Response 200
{
  "user_id": "uuid-...",
  "due_count": 7,
  "items": [
    {
      "item_id": "mis_20250401_001",
      "easiness": 2.36,
      "interval_days": 6,
      "repetitions": 2,
      "next_review_at": "2025-04-07T09:00:00",
      "last_reviewed_at": "2025-04-01T09:00:00"
    }
  ]
}
```

#### 获取单个条目状态

**GET** `/api/memory/curve/{item_id}`

```json
// Response 200 – SM2Item 对象（同上格式）
// Response 404 – { "detail": "条目不存在" }
```

#### 提交复习结果

**POST** `/api/memory/curve/{item_id}/review`

```json
// Request
{ "quality": 4 }

// Response 200
{
  "message": "复习结果已记录",
  "item_id": "mis_20250401_001",
  "next_review_at": "2025-04-07T09:00:00",
  "interval_days": 6,
  "repetitions": 3,
  "easiness": 2.5
}
```

---

### 7.4 战力值历史

#### 获取战力值历史

**GET** `/api/memory/power?limit=30`

```json
// Response 200
{
  "user_id": "uuid-...",
  "total_records": 15,
  "latest_score": 1350.5,
  "history": [
    {
      "score": 1350.5,
      "reason": "完成第3组训练，正确率 87.5%",
      "recorded_at": "2025-04-01T09:30:00"
    }
  ]
}
```

#### 添加战力值记录

**POST** `/api/memory/power`

```json
// Request
{
  "score": 1350.5,
  "reason": "完成第3组训练，正确率 87.5%"
}

// Response 201
{ "message": "战力值已记录", "score": 1350.5 }
```

---

## 8. Sessions API – 工作记忆会话

工作记忆存储单次学习会话的上下文（文章、题目、对话）。

### 8.1 获取会话列表

**GET** `/api/sessions?session_type=training` `🔐`

| 参数 | 值 | 说明 |
|------|----|------|
| `session_type` | `training` \| `chatting` | 会话类型，默认 training |

```json
// Response 200
{
  "user_id": "uuid-...",
  "session_type": "training",
  "session_ids": ["session_abc123", "session_xyz456"],
  "count": 2
}
```

### 8.2 获取最近会话

**GET** `/api/sessions/current?session_type=training` `🔐`

```json
// Response 200 – 完整 WorkingMemory 对象
{
  "session_id": "session_abc123",
  "session_type": "training",
  "user_id": "uuid-...",
  "articles": [ { "title": "...", "content": "...", "difficulty": "L2" } ],
  "question_queue": [ [ { "question_text": "...", "options": {...}, "correct_answer": "A" } ] ],
  "conversation_history": [ { "role": "user", "content": "..." } ],
  "agent_information": [ { "corpus_expert_planning": {...} } ],
  "created_at": "2025-04-01T09:00:00",
  "updated_at": "2025-04-01T10:30:00"
}

// Response 404 – { "detail": "没有找到正在进行中的会话" }
```

### 8.3 获取指定会话详情

**GET** `/api/sessions/{session_id}` `🔐`

> 返回格式同 §8.2

### 8.4 获取会话文章列表

**GET** `/api/sessions/{session_id}/articles` `🔐`

```json
// Response 200
{
  "session_id": "session_abc123",
  "article_count": 4,
  "articles": [
    {
      "title": "Ocean Plastic Pollution",
      "content": "Every year...",
      "difficulty": "L2",
      "genre": "expository",
      "key_vocabulary": ["biodegradable", "microplastics"]
    }
  ]
}
```

### 8.5 获取会话题目队列

**GET** `/api/sessions/{session_id}/questions` `🔐`

```json
// Response 200
{
  "session_id": "session_abc123",
  "question_sets": 4,
  "questions": [
    [
      {
        "question_text": "What is the main problem described?",
        "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
        "correct_answer": "B",
        "explanation": "...",
        "evidence": "...",
        "type": "main_idea"
      }
    ]
  ]
}
```

### 8.6 获取会话对话历史

**GET** `/api/sessions/{session_id}/history?limit=40` `🔐`

```json
// Response 200
{
  "session_id": "session_abc123",
  "total_messages": 10,
  "returned": 10,
  "history": [
    { "role": "user", "content": "这道题为什么选B？" },
    { "role": "assistant", "content": "根据原文第三段..." }
  ]
}
```

### 8.7 获取 Agent 运行信息

**GET** `/api/sessions/{session_id}/agent-info` `🔐`

```json
// Response 200
{
  "session_id": "session_abc123",
  "agent_info_count": 3,
  "agent_information": [
    { "corpus_expert_planning": { "training_plan": [...] } },
    { "diagnosis_A1": { "error_category": "推理判断", "explanation": "..." } }
  ]
}
```

### 8.8 删除会话

**DELETE** `/api/sessions/{session_id}` `🔐`

```json
// Response 200
{ "message": "会话已删除", "session_id": "session_abc123" }

// Response 404
{ "detail": "会话 'session_abc123' 不存在" }
```

---

## 9. 错误码规范

| HTTP 状态码 | 含义 | 常见场景 |
|------------|------|---------|
| `200` | 成功 | 查询、轮询 |
| `201` | 创建成功 | POST 添加数据 |
| `400` | 请求参数错误 | 字段格式不对、密码不符合规则 |
| `401` | 未认证 | 缺少/过期/无效 Token |
| `403` | 无权限 | 访问他人数据、需要 admin 角色 |
| `404` | 资源不存在 | 错题/会话/request_id 不存在 |
| `422` | 数据校验失败 | Pydantic 校验未通过（如 quality 超范围） |
| `500` | 服务器内部错误 | AI 调用失败、文件系统问题 |

所有错误响应格式：
```json
{ "detail": "错误原因描述" }
```

---

## 10. 典型开发场景示例

### 场景 A：用户提交答题并获取诊断

```javascript
// 1. 提交答题
const { request_id } = await post('/api/attempt', {
  request_type: 'attempt',
  session_id: 'session_abc',
  paragraph: '...原文...',
  question_text: '...题目...',
  options: { A: '...', B: '...', C: '...', D: '...' },
  user_answer: 'A',
  correct_answer: 'B',
  time_spent: 45,
  question_number: 'A1'
});

// 2. 轮询结果（每 2 秒）
let result;
while (true) {
  result = await get(`/api/result/${request_id}`);
  if (result.status !== 'processing') break;
  await sleep(2000);
}

// 3. 读取诊断结果
const diagnosis = result.results.sub_001.diagnosis;
// { error_category, explanation, evidence_sentence, suggestion }
```

### 场景 B：生成完整训练题组

```javascript
// 1. 触发 training_set 规划（异步）
const { request_id } = await post('/api/attempt', {
  request_type: 'training_set',
  session_id: 'session_train_001',
  user_level: 'L2'
});

// 2. 轮询（training_set 通常需要 15-60 秒）
let result;
while (true) {
  result = await get(`/api/result/${request_id}`);
  if (result.status !== 'processing') break;
  await sleep(3000);
}

// 3. 读取4篇文章和对应题目
// result.results 中包含：
// - sub_000: 训练规划（training_plan）
// - dyn_c1/c2/c3/c4: 4篇生成文章
// - dyn_q1/q2/q3/q4: 对应题目组
```

### 场景 C：复习错题流程

```javascript
// 1. 获取今日待复习错题（从 SM-2 曲线）
const { mistakes } = await get('/api/memory/mistakes/due?limit=10');

// 2. 用户答题后，记录复习质量（0-5）
await post(`/api/memory/curve/${mistake_id}/review`, { quality: 4 });

// 3. 可选：更新错题的 review_count
await put(`/api/memory/mistakes/${mistake_id}`, {
  review_count: mistake.review_count + 1
});
```

### 场景 D：问答（查词/长难句/语法）

```javascript
// 查词
await post('/api/attempt', {
  request_type: 'qa',
  session_id: 'session_chat_001',
  query_type: 'word',
  content: 'biodegradable',
  context_sentence: '...包含该词的句子...'
});

// 长难句拆解
await post('/api/attempt', {
  request_type: 'qa',
  session_id: 'session_chat_001',
  query_type: 'sentence',
  content: 'Not until the 20th century did scientists fully understand...'
});

// 语法解释
await post('/api/attempt', {
  request_type: 'qa',
  query_type: 'grammar',
  content: '倒装句的用法',
  session_id: 'session_chat_001'
});
```

---

## 11. request_type 速查表

| request_type | 用途 | 必填字段 | 可选字段 |
|-------------|------|---------|---------|
| `attempt` | 提交答题，触发错因分析 | `paragraph`, `question_text`, `options`, `user_answer`, `correct_answer` | `time_spent`, `question_number` |
| `corpus` | 生成单篇文章 | – | `difficulty`(L1-L4), `genre`, `topic`, `word_count`, `reference_id` |
| `question` | 为文章出题 | `article` | `question_type`, `question_types`, `difficulty`, `count` |
| `qa` | 问答（查词/句/语法/翻译/自由） | `query_type`, `content` | `context_sentence` |
| `training_set` | 生成完整训练题组（4篇文章+题目） | – | `user_level`(L1-L4) |

### request_type = `qa` 的 query_type 说明

| query_type | 功能 | content 填什么 |
|-----------|------|--------------|
| `word` | 查词义 | 单词 |
| `sentence` | 长难句拆解 | 英语句子 |
| `grammar` | 语法解释 | 语法问题描述 |
| `translate` | 翻译英文 | 英文文本 |
| `free` | 自由问答（支持工具调用） | 任意问题 |

---

## 12. 环境变量与部署

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥（**生产环境必须设置**） | dev 默认值（不安全）|
| `OPENAI_API_KEY` | OpenAI API Key | 无 |
| `OPENAI_BASE_URL` | 自定义 API 地址（如代理） | OpenAI 官方地址 |
| `OPENAI_MODEL` | 使用的模型名 | `gpt-4o` |

### 启动开发服务器

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 查看交互式 API 文档

启动后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

*本文档对应 ReadWise AI v0.2.0，如有 API 变更请同步更新此文档。*

---

## 13. POST /api/attempt 深度分析与调用流程

> 本节面向前端开发者，逐层解析 `POST /api/attempt` 从 HTTP 请求到返回结果的完整执行过程，帮助理解各字段的作用时机、数据结构变化和异步处理机制。

---

### 13.1 接口生命周期概览

`POST /api/attempt` 是一个**异步接口**，遵循"提交 → 轮询"模式：

```
前端
  ├─ 1. POST /api/attempt       → 立即得到 request_id（< 200ms）
  ├─ 2. 每隔 2-3s 轮询           → GET /api/result/{request_id}
  │      ├─ status: "processing"  → 继续等待
  │      ├─ status: "completed"   → 读取 results
  │      └─ status: "failed"      → 读取 error_log 展示错误
  └─ 3. 总处理时间：3-20s（取决于 AI 响应速度和任务数量）
```

**背后实际执行了什么：**

| 阶段 | 描述 | 大约耗时 |
|------|------|---------|
| 请求接收 | JWT 验证、生成 request_id、保存初始状态 | < 50ms |
| Planner | LLM 分析请求，生成子任务列表 | 1–3s |
| Sub-Agent 执行 | 每个子任务调用 LLM 完成实际工作 | 2–10s/任务 |
| Verifier | LLM 验收每个任务结果 | 1–2s/任务 |
| 结果写入磁盘 | 将最终结果持久化 | < 50ms |

---

### 13.2 请求字段的完整作用说明

**通用字段（所有 request_type 均适用）：**

| 字段 | 是否必填 | 作用 |
|------|---------|------|
| `request_type` | 是 | 决定 Planner 分配哪种 Sub-Agent（见下表） |
| `session_id` | 建议传 | 关联工作记忆（WorkingMemory）；不传则自动生成新 session |
| `question_number` | 否 | 诊断结果存入记忆时的 key（如 "A1" → key: `diagnosis_A1`） |

**按 request_type 的专属字段：**

| request_type | 字段 | 用途 |
|---|---|---|
| `attempt` | `paragraph` | 原文段落，传给 DiagnosisExpert 进行分析 |
| | `question_text` | 题目文本 |
| | `options` | `{"A":"...","B":"...","C":"...","D":"..."}` |
| | `user_answer` | 学生实际选择（"A"/"B"/"C"/"D"） |
| | `correct_answer` | 正确答案 |
| | `time_spent` | 用时秒数（可选，用于分析） |
| `corpus` | `difficulty` | L1/L2/L3/L4（L1最易） |
| | `genre` | `argumentative`/`expository`/`narrative` |
| | `topic` | 文章主题（自然语言描述） |
| | `word_count` | 目标词数 |
| | `reference_id` | 语料库文章 ID，触发风格化模式 |
| `question` | `article` | 文章正文（字符串） |
| | `question_type` | 单一题型：`detail`/`inference`/`vocabulary`/`main_idea` |
| | `question_types` | 题型列表（与 count 配合出多题） |
| | `count` | 出题数量，默认 3 |
| `qa` | `query_type` | `word`/`sentence`/`grammar`/`translate`/`free` |
| | `content` | 查询内容（单词/句子/问题） |
| | `context_sentence` | 提供上下文（查词时辅助理解含义） |
| `training_set` | `user_level` | 用户整体水平（L1-L4），指导规划器选择难度 |

---

### 13.3 结果数据结构（按 request_type）

所有结果通过 GET /api/result 的 `results` 字段返回，结构为：

```json
{
  "results": {
    "sub_001": { /* 子任务结果 */ }
  }
}
```

**request_type = `attempt`（错题诊断）：**

```json
{
  "results": {
    "sub_001": {
      "diagnosis": {
        "error_category": "推理判断",
        "explanation": "该题考查深层推理，学生误选细节答案...",
        "evidence_sentence": "Scientists have found that...",
        "suggestion": "建议加强推理题解题逻辑训练",
        "confidence": 0.92
      },
      "similar_question": {
        "paragraph": "A new study suggests...",
        "question": "What can be inferred from the passage?",
        "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
        "correct_answer": "B",
        "explanation": "根据第二段..."
      },
      "metadata": { "latency_ms": 2100, "agent": "diagnosis_expert" }
    }
  }
}
```

**request_type = `corpus`（文章生成）：**

```json
{
  "results": {
    "sub_001": {
      "article": {
        "title": "The Future of Renewable Energy",
        "content": "As the world faces...",
        "word_count": 312,
        "difficulty_actual": "L2",
        "genre_actual": "expository",
        "key_vocabulary": ["renewable", "sustainable", "emission"],
        "grammar_highlights": ["被动语态", "定语从句"]
      },
      "validation": { "passed": true, "issues": [] },
      "metadata": { "attempts": 1, "latency_ms": 3200 }
    }
  }
}
```

**request_type = `question`（出题）：**

```json
{
  "results": {
    "sub_001": {
      "questions": [
        {
          "question_text": "What is the main idea of the passage?",
          "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
          "correct_answer": "C",
          "explanation": "文章第一段明确指出...",
          "evidence": "The primary goal of the program is...",
          "type": "main_idea"
        }
      ],
      "metadata": { "latency_ms": 1800, "agent": "question_expert", "count": 3 }
    }
  }
}
```

**request_type = `qa`（问答）：**

```json
{
  "results": {
    "sub_001": {
      "query_type": "word",
      "content": "biodegradable",
      "answer": {
        "word": "biodegradable",
        "phonetic": "/ˌbaɪoʊdɪˈɡreɪdəbl/",
        "definitions": ["可生物降解的"],
        "context_meaning": "在文中指可被自然分解的材料",
        "examples": ["biodegradable packaging"]
      }
    }
  }
}
```

**request_type = `training_set`（完整训练题组）：**

```json
{
  "results": {
    "sub_000": {
      "training_plan": [
        { "idx": 1, "topic": "科技与环保", "difficulty": "L2", "word_count": 300, "genre": "expository" },
        { "idx": 2, "topic": "社会与文化", "difficulty": "L2", "word_count": 320, "genre": "argumentative" },
        { "idx": 3, "topic": "历史与人物", "difficulty": "L3", "word_count": 350, "genre": "narrative" },
        { "idx": 4, "topic": "科学与探索", "difficulty": "L3", "word_count": 340, "genre": "expository" }
      ],
      "metadata": { "mode": "planning" }
    },
    "dyn_c1": { "article": { /* 文章1 */ } },
    "dyn_c2": { "article": { /* 文章2 */ } },
    "dyn_c3": { "article": { /* 文章3 */ } },
    "dyn_c4": { "article": { /* 文章4 */ } },
    "dyn_q1": { "questions": [ /* 文章1的题目 */ ] },
    "dyn_q2": { "questions": [ /* 文章2的题目 */ ] },
    "dyn_q3": { "questions": [ /* 文章3的题目 */ ] },
    "dyn_q4": { "questions": [ /* 文章4的题目 */ ] }
  }
}
```

---

### 13.4 后台处理的完整调用链（技术细节）

```
POST /api/attempt（HTTP 请求）
    │
    ├─ JWT 验证（app/auth/dependencies.py）
    │    └─ 解析 Bearer Token → 提取 user_id（前端不需要传）
    │
    ├─ 生成 request_id（格式：req_[12位hex]）
    ├─ 创建 OrchestratorState（status: PENDING）
    ├─ 保存到磁盘（data/users/{user_id}/checkpoints/{request_id}.json）
    │
    ├─ 注册后台任务（FastAPI BackgroundTasks）
    └─ ← 立即返回 { request_id, session_id, status, result_url }

─── 后台异步执行 ────────────────────────────────────────────────────

Orchestrator._run()（最多20次循环迭代）
    │
    ├─ [PLANNING] Planner.plan()
    │    ├─ 优先：调用 LLM 进行任务分解
    │    └─ 回退：按 request_type 做规则匹配，生成 SubTask 列表
    │
    ├─ [WAITING] Dispatcher.dispatch_all_pending()
    │    │
    │    ├─ 解析跨任务输入（article_task_id → 取上游文章）
    │    │
    │    ├─ 注入记忆上下文：
    │    │    ├─ WorkingMemory（当前 session 的文章/题目/对话历史）
    │    │    ├─ LongTermMemory（用户错题本/遗忘曲线/训练记录/战力值）
    │    │    └─ CorpusRepo（语料库文章索引）
    │    │
    │    └─ 调用 Sub-Agent：
    │         ├─ DiagnosisExpert：分析错误 + 生成同类题（写入 WorkingMemory）
    │         ├─ CorpusExpert：生成文章（写入 WorkingMemory）
    │         ├─ QuestionExpert：生成题目
    │         └─ QAExpert：回答问题（可调用6个 LangChain 工具）
    │
    ├─ Verifier.verify()
    │    └─ LLM 验收结果 → 通过则存入 completed_results，失败则重试
    │
    ├─ 动态注入新子任务（training_set 场景：corpus 规划后注入8个任务）
    │
    └─ 最终结果写入磁盘（data/users/{user_id}/results/{request_id}.json）

─── 前端轮询 ────────────────────────────────────────────────────────

GET /api/result/{request_id}
    ├─ JWT 验证 + 所有权校验（防止越权访问他人结果）
    ├─ 优先读取 results/{request_id}.json（已完成时）
    ├─ 回退读取 checkpoints/{request_id}.json（处理中时）
    └─ 返回 { status, results } 或 { status: "processing" }
```

---

### 13.5 session_id 的作用与最佳实践

`session_id` 是工作记忆（WorkingMemory）的键，建议前端按以下规则管理：

| 场景 | 建议的 session_id |
|------|-----------------|
| 一次完整训练（含文章+题目） | 固定一个值，如 `session_train_20250401` |
| 对话/问答模式 | 独立的会话 ID，如 `session_chat_20250401` |
| 每次刷新页面重新开始 | 生成新的 session_id |
| 继续上次会话 | 使用之前的 session_id（可从 GET /api/sessions 获取） |

**不传 session_id 的后果：** 服务端自动生成一个随机 session_id，当次请求完成后无法通过 Session API 找回该 session 下的文章和题目。

---

### 13.6 错误场景与前端处理建议

| 场景 | GET /api/result 返回 | 前端处理建议 |
|------|---------------------|-------------|
| 正常处理中 | `{ "status": "processing" }` | 继续轮询 |
| 处理完成 | `{ "status": "completed", "results": {...} }` | 展示结果 |
| AI 分析失败 | `{ "status": "failed", "error_log": [...] }` | 展示"处理失败，请重试" |
| request_id 不存在 | `{ "status": "not_found" }` | 展示"请求已过期" |
| 越权访问 | HTTP 403 | 展示"无权访问" |
| 网络超时 | （轮询请求超时） | 重试轮询，最多10次 |

**推荐轮询策略：**

```javascript
async function pollResult(requestId, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2500));  // 等待 2.5s
    const res = await fetch(`/api/result/${requestId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    const data = await res.json();

    if (data.status === 'completed') return data.results;
    if (data.status === 'failed') throw new Error(data.error_log?.join(', '));
    if (data.status === 'not_found') throw new Error('请求已过期');
    // status === 'processing' → 继续循环
  }
  throw new Error('等待超时，请刷新页面重试');
}
```

---

### 13.7 WorkingMemory 与 Session API 的关系

每次 Sub-Agent 执行后会自动更新 WorkingMemory。前端可通过 Session API 读取本次会话中积累的数据：

| Session API | 读取内容 | 典型使用场景 |
|---|---|---|
| `GET /api/sessions/{id}/articles` | 本次 session 生成的所有文章 | 训练结束后展示文章列表 |
| `GET /api/sessions/{id}/questions` | 本次 session 生成的所有题目 | 组题练习 |
| `GET /api/sessions/{id}/history` | 对话历史 | QA 模式下展示聊天记录 |
| `GET /api/sessions/{id}/agent-info` | Agent 运行信息（含诊断结果） | 调试或展示诊断详情 |

**完整训练流程的数据关联：**

```
POST /api/attempt (request_type=training_set, session_id="s1")
  → 后台生成 4 篇文章 + 4 组题目，全部写入 WorkingMemory(session_id="s1")

GET /api/sessions/s1/articles  → 返回 4 篇文章
GET /api/sessions/s1/questions → 返回 4 组题目（与文章对应）
```
