# EduFlowGraph 部署文档

> **版本**: 1.0 · **最后更新**: 2026-06-29 · **维护者**: EduFlowGraph Contributors

---

## 目录

1. [环境要求](#1-环境要求)
2. [快速启动（一键运行）](#2-快速启动一键运行)
3. [手动安装与部署](#3-手动安装与部署)
4. [环境变量配置](#4-环境变量配置)
5. [存储后端选择](#5-存储后端选择)
6. [数据迁移指南](#6-数据迁移指南)
7. [数据导出与回滚](#7-数据导出与回滚)
8. [生产环境部署建议](#8-生产环境部署建议)
9. [故障排查](#9-故障排查)
10. [脚本参考](#10-脚本参考)

---

## 1. 环境要求

### 1.1 基础环境

| 依赖 | 最低版本 | 推荐版本 | 说明 |
|------|----------|----------|------|
| Python | 3.10 | 3.11+ | 后端运行时 |
| Node.js | 18.0 | 20+ | 前端构建与开发服务器 |
| npm | 8.0 | 10+ | 前端包管理器 |
| SQLite | 3.35+ | 3.40+ | 嵌入式数据库（Python 内置） |
| Git | 2.0 | — | 版本控制 |

### 1.2 操作系统兼容性

| 操作系统 | 状态 | 备注 |
|----------|------|------|
| macOS 12+ | ✅ 完全支持 | 主要开发环境 |
| Ubuntu 20.04+ | ✅ 完全支持 | 推荐生产环境 |
| Windows 10+ | ⚠️ 实验性 | 需 WSL2 或原生 Python |

### 1.3 网络要求

| 用途 | 端口 | 协议 |
|------|------|------|
| FastAPI 后端 | 8000（可配置） | HTTP |
| Next.js 前端 | 3000（可配置） | HTTP |
| OpenAI-compatible API | 443 | HTTPS（出站） |

---

## 2. 快速启动（一键运行）

### 2.1 克隆与启动

```bash
# 克隆仓库
git clone https://github.com/pan0918/EduFlowGraph.git
cd EduFlowGraph

# 一键启动（自动安装依赖、选择端口、启动前后端）
.venv/bin/python scripts/start_web.py
```

> **注意**：首次运行前需先完成 [手动安装](#3-手动安装与部署) 中的 Python 环境和前端依赖步骤。

### 2.2 启动脚本行为

`scripts/start_web.py` 执行以下操作：

1. **端口选择**：从 8000（后端）和 3000（前端）开始扫描，自动选择可用端口
2. **依赖检查**：若 `web/node_modules` 不存在，自动创建符号链接
3. **后端启动**：通过 `uvicorn` 启动 FastAPI 应用
4. **前端启动**：通过 `npm run dev` 启动 Next.js 开发服务器
5. **健康检查**：等待后端 `/api/health` 和前端就绪
6. **进程监控**：任一进程退出时自动终止另一个

### 2.3 启动后访问

```
前端界面: http://127.0.0.1:3000
后端 API: http://127.0.0.1:8000
健康检查: http://127.0.0.1:8000/api/health
```

### 2.4 Mock 模式

系统默认以 **Mock 模式**运行，无需任何 API Key：

- LLM 调用返回确定性的中文模拟回复
- 嵌入向量使用 32 维哈希生成
- 重排序使用关键词重叠评分

所有功能（对话、Episode 提取、概念识别、技能蒸馏、画像更新）均可在 Mock 模式下完整运行。

---

## 3. 手动安装与部署

### 3.1 Python 环境

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 安装 Python 依赖
pip install -r requirements.txt
```

### 3.2 前端依赖

```bash
# 进入前端目录
cd web

# 安装 Node.js 依赖
npm install

# 返回项目根目录
cd ..
```

### 3.3 环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件（可选，Mock 模式下无需配置）
```

### 3.4 验证安装

```bash
# 运行端到端冒烟测试
.venv/bin/python scripts/smoke_run.py

# 预期输出：5 轮对话的摘要、Episode 节点 ID、仪表盘统计
```

---

## 4. 环境变量配置

### 4.1 完整变量列表

| 变量 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `OPENAI_API_KEY` | string | — | OpenAI-compatible API Key |
| `OPENAI_BASE_URL` | string | `https://api.openai.com/v1` | API 基础 URL |
| `EDUFLOW_PROVIDER` | string | `mock` | 提供者模式 |
| `EDUFLOW_CHAT_MODEL` | string | `gpt-4o-mini` | 聊天模型 ID |
| `EDUFLOW_EMBEDDING_MODEL` | string | `text-embedding-3-small` | 嵌入模型 ID |
| `EDUFLOW_RERANKER_MODEL` | string | — | 重排序模型 ID（可选） |
| `EDUFLOW_EXTRACTION_TURNS` | int | `4` | Episode 提取触发轮次数 |
| `EDUFLOW_DATA_DIR` | string | `data` | 数据目录路径 |
| `EDUFLOW_STORAGE_BACKEND` | string | `sqlite` | 存储后端 |
| `EDUFLOW_DATABASE_PATH` | string | — | SQLite 数据库路径（可选） |

### 4.2 使用真实模型

```bash
# OpenAI 官方 API
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export EDUFLOW_PROVIDER="openai-compatible"
export EDUFLOW_CHAT_MODEL="gpt-4o-mini"
export EDUFLOW_EMBEDDING_MODEL="text-embedding-3-small"

# DeepSeek API
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export EDUFLOW_PROVIDER="openai-compatible"
export EDUFLOW_CHAT_MODEL="deepseek-chat"
export EDUFLOW_EMBEDDING_MODEL="text-embedding-v2"

# SiliconFlow API
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1"
export EDUFLOW_PROVIDER="openai-compatible"
export EDUFLOW_CHAT_MODEL="Qwen/Qwen2.5-7B-Instruct"
export EDUFLOW_EMBEDDING_MODEL="BAAI/bge-large-zh-v1.5"

# 本地 Ollama
export OPENAI_API_KEY="ollama"
export OPENAI_BASE_URL="http://localhost:11434/v1"
export EDUFLOW_PROVIDER="openai-compatible"
export EDUFLOW_CHAT_MODEL="qwen2.5:7b"
export EDUFLOW_EMBEDDING_MODEL="nomic-embed-text"
```

### 4.3 前端运行时配置

除环境变量外，模型配置也可通过前端 Settings 页面实时修改，无需重启后端。前端配置优先级高于环境变量。

---

## 5. 存储后端选择

### 5.1 SQLite（默认，推荐）

```bash
export EDUFLOW_STORAGE_BACKEND=sqlite
# 可选：自定义数据库路径
export EDUFLOW_DATABASE_PATH=data/eduflowgraph.db
```

**特性**：
- WAL 模式：支持并发读取和后台写入
- 事务一致性：`BEGIN IMMEDIATE` 保证写入原子性
- 外键约束：图完整性由数据库层保证
- 自动 Schema 迁移：v1 → v2 → v3 自动升级
- 零配置：无需外部数据库服务器

### 5.2 JSON/JSONL（遗留后端）

```bash
export EDUFLOW_STORAGE_BACKEND=json
export EDUFLOW_DATA_DIR=data
```

**特性**：
- 人类可读：所有数据以 JSON/JSONL 格式存储在磁盘
- 零依赖：无需 SQLite 或其他数据库
- 开发友好：可直接查看和编辑数据文件

**数据文件结构**（JSON 后端）：

```
data/
├── conversations/
│   └── session_demo.jsonl        # 对话日志
├── memory_flow.jsonl              # 记忆事件日志
├── graph_nodes.json               # 图节点
├── graph_edges.json               # 图边
├── learner_profile.json           # 学习者画像
└── skill_adaptation.json          # 技能适配证据
```

---

## 6. 数据迁移指南

### 6.1 JSON → SQLite 迁移

> **重要**：迁移前请停止 Web 服务。

```bash
# 步骤 1：预览迁移（不修改任何文件）
.venv/bin/python scripts/migrate_storage.py \
  --data-dir data \
  --dry-run

# 步骤 2：执行迁移
.venv/bin/python scripts/migrate_storage.py \
  --data-dir data \
  --apply

# 步骤 3：验证迁移完整性
.venv/bin/python scripts/migrate_storage.py \
  --data-dir data \
  --verify
```

### 6.2 覆盖已存在的空数据库

若 SQLite 数据库已存在但业务表为空：

```bash
.venv/bin/python scripts/migrate_storage.py \
  --data-dir data \
  --apply \
  --replace-empty
```

### 6.3 迁移注意事项

- 迁移**不会修改**原始 JSON/JSONL 文件
- 迁移后需将 `EDUFLOW_STORAGE_BACKEND` 设为 `sqlite`
- 迁移包含数据验证步骤，确保节点、边、画像的完整性

---

## 7. 数据导出与回滚

### 7.1 SQLite → JSON 导出

```bash
# 导出到带时间戳的目录
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data-export-$(date +%Y%m%d-%H%M%S)
```

### 7.2 回滚到 JSON 后端

```bash
# 1. 停止 Web 服务
# 2. 导出当前 SQLite 数据
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data-rollback

# 3. 切换到 JSON 后端
export EDUFLOW_STORAGE_BACKEND=json
export EDUFLOW_DATA_DIR=data-rollback

# 4. 重新启动
.venv/bin/python scripts/start_web.py
```

---

## 8. 生产环境部署建议

### 8.1 进程管理

使用 `systemd` 或 `supervisor` 管理后端进程：

```ini
# /etc/supervisor/conf.d/eduflowgraph.conf
[program:eduflowgraph]
command=/opt/EduFlowGraph/.venv/bin/python -m uvicorn EduFlowGraph.web_app:app --host 0.0.0.0 --port 8000
directory=/opt/EduFlowGraph
environment=EDUFLOW_STORAGE_BACKEND="sqlite",EDUFLOW_DATA_DIR="/var/lib/eduflowgraph/data"
autostart=true
autorestart=true
stderr_logfile=/var/log/eduflowgraph/error.log
stdout_logfile=/var/log/eduflowgraph/access.log
```

### 8.2 前端构建

```bash
cd web
npm run build    # 生产构建
npm start        # 启动生产服务器
```

### 8.3 反向代理（Nginx）

```nginx
server {
    listen 80;
    server_name eduflowgraph.example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;           # SSE 流式需要关闭缓冲
        proxy_cache off;
    }
}
```

### 8.4 数据备份

```bash
# 定期备份 SQLite 数据库
cp data/eduflowgraph.db data/backup/eduflowgraph_$(date +%Y%m%d).db

# 或导出为 JSON
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data/backup/json_$(date +%Y%m%d)
```

### 8.5 安全建议

- **API Key 管理**：使用环境变量或 secrets manager，不要硬编码
- **CORS 配置**：生产环境中限制 `allow_origins` 为实际域名
- **HTTPS**：通过反向代理启用 TLS
- **数据目录权限**：确保 SQLite 数据库文件权限为 `600`

---

## 9. 故障排查

### 9.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `ModuleNotFoundError: EduFlowGraph` | PYTHONPATH 未设置 | 使用 `scripts/start_web.py` 启动，或手动设置 `PYTHONPATH=.` |
| `Port already in use` | 端口被占用 | 启动脚本会自动选择下一个可用端口 |
| `no such table: sessions` | 数据库未初始化 | 删除 `data/eduflowgraph.db` 后重启 |
| `FOREIGN KEY constraint failed` | 图边引用了不存在的节点 | 运行 `PRAGMA quick_check` 检查数据库完整性 |
| 前端白屏 | API 连接失败 | 检查后端是否运行，确认 `NEXT_PUBLIC_API_BASE` 配置 |
| Mock 模式下无响应 | LLM mock 未触发 | 确认 `EDUFLOW_PROVIDER=mock` |

### 9.2 诊断端点

```bash
# 健康检查
curl http://127.0.0.1:8000/api/health

# 模型连接测试
curl -X POST http://127.0.0.1:8000/api/diagnostics/model-test \
  -H "Content-Type: application/json" \
  -d '{"kind": "llm"}'
```

### 9.3 日志查看

```bash
# 后端日志（uvicorn）
tail -f /var/log/eduflowgraph/access.log

# 前端日志
# 查看浏览器开发者工具 Console
```

---

## 10. 脚本参考

### 10.1 `scripts/start_web.py` — 统一启动器

**功能**：同时启动后端（uvicorn）和前端（npm dev），自动选择可用端口。

**环境变量**：

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `BACKEND_PORT` | `0`（自动） | 后端端口 |
| `FRONTEND_PORT` | `0`（自动） | 前端端口 |

**用法**：

```bash
.venv/bin/python scripts/start_web.py
```

### 10.2 `scripts/migrate_storage.py` — 数据迁移

**功能**：JSON/JSONL → SQLite 数据迁移。

**参数**：

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--data-dir` | Path | `data` | 源数据目录 |
| `--database-path` | Path | `{data-dir}/eduflowgraph.db` | 目标数据库路径 |
| `--replace-empty` | flag | — | 覆盖已存在的空数据库 |
| `--dry-run` | flag | — | 仅预览，不修改文件 |
| `--apply` | flag | — | 执行迁移 |
| `--verify` | flag | — | 验证迁移完整性 |

**用法**：

```bash
.venv/bin/python scripts/migrate_storage.py --data-dir data --dry-run
.venv/bin/python scripts/migrate_storage.py --data-dir data --apply
.venv/bin/python scripts/migrate_storage.py --data-dir data --verify
```

### 10.3 `scripts/export_storage.py` — 数据导出

**功能**：SQLite → JSON 数据导出。

**参数**：

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--database-path` | Path | `data/eduflowgraph.db` | 源数据库路径 |
| `--output-dir` | Path | —（必填） | 导出目标目录 |

**用法**：

```bash
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data-export-$(date +%Y%m%d-%H%M%S)
```

### 10.4 `scripts/smoke_run.py` — 端到端冒烟测试

**功能**：使用 Mock 提供者运行完整的 5 轮对话测试，验证以下流程：

1. 对话日志记录
2. Episode 边界检测
3. 概念提取
4. 技能蒸馏
5. 画像更新
6. 仪表盘聚合

**用法**：

```bash
.venv/bin/python scripts/smoke_run.py
```

**预期输出**：

```
Turn 1: answer=... episode=episode_xxx
Turn 2: answer=... episode=episode_xxx
Turn 3: answer=... episode=episode_xxx
Turn 4: answer=... episode=episode_xxx
Turn 5: answer=... episode=episode_xxx
Dashboard: memory_events=N, concepts=N, episodes=N, skills=N, edges=N
```
