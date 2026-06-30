# EduMindFlow 部署文档

> 最后更新: 2026-06-30
> 说明: GitHub 仓库名和 Python 包名仍为 `EduFlowGraph`。产品展示名称为 `EduMindFlow`。

## 1. 适用场景

本文档覆盖三类部署方式:

1. 本地开发: 同时启动 FastAPI 后端和 Next.js 前端。
2. 本地真实模型调试: 使用 OpenAI-compatible API。
3. 简单生产部署: 后端使用 Uvicorn 或 Supervisor，前端使用 Next.js 构建产物，Nginx 做反向代理。

如果只是快速查看项目，优先使用本地开发方式。

## 2. 环境要求

| 依赖 | 最低版本 | 建议版本 | 说明 |
|---|---:|---:|---|
| Python | 3.10 | 3.11+ | 后端运行时 |
| Node.js | 18 | 20+ | 前端开发和构建 |
| npm | 8 | 10+ | 前端包管理 |
| SQLite | Python 内置 | 3.40+ | 默认存储后端 |
| Git | 2.x | 2.x | 克隆和版本管理 |

支持环境:

| 系统 | 说明 |
|---|---|
| macOS | 当前主要开发环境 |
| Linux | 推荐生产环境 |
| Windows | 建议通过 WSL2 运行 |

默认端口:

| 服务 | 默认地址 |
|---|---|
| 后端 | `http://127.0.0.1:8000` |
| 前端 | `http://127.0.0.1:3000` |

## 3. 本地启动

### 3.1 克隆仓库

```bash
git clone git@github.com:pan0918/EduFlowGraph.git
cd EduFlowGraph
```

如果没有配置 SSH key，也可以使用 HTTPS:

```bash
git clone https://github.com/pan0918/EduFlowGraph.git
cd EduFlowGraph
```

### 3.2 安装 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3.3 安装前端依赖

```bash
cd web
npm install
cd ..
```

### 3.4 启动服务

```bash
.venv/bin/python scripts/start_web.py
```

启动器会:

- 启动 FastAPI 后端。
- 启动 Next.js 开发服务器。
- 检查端口可用性。
- 等待后端健康检查和前端就绪。
- 在任一子进程退出时停止另一个子进程。

启动后访问:

```text
前端: http://127.0.0.1:3000
后端: http://127.0.0.1:8000
健康检查: http://127.0.0.1:8000/api/health
```

## 4. Mock 模式和真实模型

### 4.1 Mock 模式

默认 provider 是 `mock`。不配置 API key 时，系统仍可运行完整流程:

- Chat 返回确定性模拟回复。
- Embedding 使用 32 维哈希向量。
- Reranker 使用关键词重叠评分。

Mock 模式适合本地开发、UI 调试和离线演示。

### 4.2 使用真实模型

创建本地环境文件:

```bash
cp .env.example .env
```

常见配置:

```bash
export EDUFLOW_PROVIDER="openai-compatible"
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export EDUFLOW_CHAT_MODEL="gpt-4o-mini"
export EDUFLOW_EMBEDDING_MODEL="text-embedding-3-small"
```

其他兼容服务也可以使用同一套变量，只要接口符合 OpenAI-compatible 格式。

## 5. 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EDUFLOW_PROVIDER` | `mock` | `mock` 或 `openai-compatible` |
| `OPENAI_API_KEY` | 空 | 模型服务 API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 模型服务 base URL |
| `EDUFLOW_CHAT_MODEL` | `gpt-4o-mini` | 聊天模型 |
| `EDUFLOW_EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型 |
| `EDUFLOW_RERANKER_MODEL` | 空 | 重排序模型 |
| `EDUFLOW_EXTRACTION_TURNS` | `4` | 触发片段抽取的轮次数 |
| `EDUFLOW_DATA_DIR` | `data` | 运行时数据目录 |
| `EDUFLOW_STORAGE_BACKEND` | `sqlite` | `sqlite` 或 `json` |
| `EDUFLOW_DATABASE_PATH` | `data/eduflowgraph.db` | SQLite 数据库路径 |

前端 Settings 页面也可以传入运行时模型配置。请求体中的配置优先于环境变量。

## 6. 存储后端

### 6.1 SQLite

SQLite 是默认后端:

```bash
export EDUFLOW_STORAGE_BACKEND=sqlite
export EDUFLOW_DATABASE_PATH=data/eduflowgraph.db
```

特点:

- 不需要外部数据库服务。
- 支持 WAL 模式。
- 支持事务写入。
- 自动执行 schema 迁移。
- 运行数据默认位于 `data/`，该目录已被 Git 忽略。

### 6.2 JSON/JSONL

遗留 JSON 后端仍可使用:

```bash
export EDUFLOW_STORAGE_BACKEND=json
```

它适合调试和迁移回滚，不建议作为长期生产存储。

## 7. 数据迁移和导出

### 7.1 JSON 到 SQLite

预览迁移:

```bash
.venv/bin/python scripts/migrate_storage.py --data-dir data --dry-run
```

执行迁移:

```bash
.venv/bin/python scripts/migrate_storage.py --data-dir data --apply
```

验证迁移:

```bash
.venv/bin/python scripts/migrate_storage.py --data-dir data --verify
```

### 7.2 SQLite 导出为 JSON

```bash
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data-export
```

导出结果可用于备份、调试或回滚到 JSON 后端。

## 8. 生产部署建议

### 8.1 后端

后端可以直接通过 Uvicorn 启动:

```bash
PYTHONPATH=. .venv/bin/python -m uvicorn EduFlowGraph.web_app:app \
  --host 0.0.0.0 \
  --port 8000
```

Supervisor 示例:

```ini
[program:edumindflow-api]
command=/opt/EduFlowGraph/.venv/bin/python -m uvicorn EduFlowGraph.web_app:app --host 0.0.0.0 --port 8000
directory=/opt/EduFlowGraph
environment=PYTHONPATH=".",EDUFLOW_STORAGE_BACKEND="sqlite",EDUFLOW_DATA_DIR="/var/lib/edumindflow/data"
autostart=true
autorestart=true
stderr_logfile=/var/log/edumindflow/error.log
stdout_logfile=/var/log/edumindflow/access.log
```

### 8.2 前端

构建前端:

```bash
cd web
npm install
npm run build
npm run start
```

Next.js 默认监听 `3000`。如果使用进程管理器，请单独管理前端进程。

### 8.3 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name edumindflow.example.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

生产环境还需要配置 HTTPS、日志轮转和访问控制。

## 9. 备份

SQLite 备份示例:

```bash
mkdir -p data/backup
cp data/eduflowgraph.db data/backup/eduflowgraph_$(date +%Y%m%d).db
```

也可以导出为 JSON:

```bash
.venv/bin/python scripts/export_storage.py \
  --database-path data/eduflowgraph.db \
  --output-dir data/backup/export_$(date +%Y%m%d)
```

备份前建议暂停写入流量，或在低流量窗口执行。

## 10. 故障排查

| 现象 | 常见原因 | 处理 |
|---|---|---|
| `ModuleNotFoundError: EduFlowGraph` | 未从仓库根目录启动或缺少 `PYTHONPATH` | 在根目录运行命令，或设置 `PYTHONPATH=.` |
| 前端无法访问 API | 后端未启动或端口不同 | 检查 `/api/health` 和启动日志 |
| 模型请求失败 | API key、base URL 或模型名错误 | 使用 `/api/diagnostics/model-test` 检查 |
| SQLite 表不存在 | 数据库未初始化或路径错误 | 检查 `EDUFLOW_DATABASE_PATH`，必要时删除空库后重启 |
| SSE 没有持续输出 | 代理缓冲或连接被中断 | 检查 Nginx 配置和浏览器网络面板 |

常用诊断命令:

```bash
curl http://127.0.0.1:8000/api/health
curl -X POST http://127.0.0.1:8000/api/diagnostics/model-test \
  -H "Content-Type: application/json" \
  -d '{"kind":"llm","provider":"mock"}'
```

## 11. 发布前检查

建议在提交或部署前运行:

```bash
.venv/bin/python -m unittest discover -s tests
node --test $(rg --files web -g '*.test.mjs')
cd web && npm run build
```
