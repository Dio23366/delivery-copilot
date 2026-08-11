# Delivery Copilot 启动指南

本文档适用于 Windows PowerShell。本项目使用 Docker Compose 启动 FastAPI 后端和 PostgreSQL，使用 Vite 启动 React 前端。

## 1. 环境要求

- Docker Desktop
- Docker Compose
- Node.js 与 npm
- Git（可选）

在项目根目录执行以下命令确认环境：

```powershell
docker --version
docker compose version
node --version
npm --version
```

## 2. 配置环境变量

如果项目根目录还没有 `.env`，可以从示例文件创建：

```powershell
Copy-Item .env.example .env
```

如需调用真实 LLM 或 Embedding 服务，请在本地 `.env` 中配置对应参数。

> `.env` 可能包含 API Key，不要将它提交到 GitHub。

## 3. 启动后端与数据库

打开第一个 PowerShell 窗口，进入项目根目录：

```powershell
docker compose up -d --build
```

查看容器状态：

```powershell
docker compose ps
```

查看后端最近的日志：

```powershell
docker compose logs backend --tail 100
```

持续查看后端日志：

```powershell
docker compose logs -f backend
```

检查后端健康状态：

```powershell
Invoke-RestMethod http://localhost:8000/health
```

成功时应返回包含 `ok` 或正常状态的响应。

后端地址：

```text
http://localhost:8000
```

FastAPI 接口文档：

```text
http://localhost:8000/docs
```

## 4. 启动前端

打开第二个 PowerShell 窗口，在项目根目录执行：

```powershell
Set-Location frontend
npm ci
npm run dev
```

Vite 启动后会显示实际访问地址，通常为：

```text
http://localhost:5173
```

如果 `5173` 已被占用，Vite 可能自动使用 `5174` 或其他端口。请以终端中显示的 `Local` 地址为准。

## 5. 常用验证命令

验证 Agent UI：

```powershell
Set-Location frontend
npm run validate:agent-ui
```

验证前端生产构建：

```powershell
Set-Location frontend
npm run build
```

检查 Docker Compose 配置：

```powershell
docker compose config
```

## 6. 停止服务

停止前端：

```text
在运行 npm run dev 的 PowerShell 窗口中按 Ctrl+C
```

停止后端和数据库容器，但保留数据库数据：

```powershell
docker compose down
```

仅暂停容器：

```powershell
docker compose stop
```

重新启动已创建的容器：

```powershell
docker compose start
```

> 不要随意执行 `docker compose down -v`。`-v` 会删除项目的 Docker 数据卷和数据库数据。

## 7. 推荐启动顺序

1. 启动 Docker Desktop。
2. 在项目根目录运行 `docker compose up -d --build`。
3. 用 `/health` 确认后端正常。
4. 在第二个 PowerShell 窗口进入 `frontend`。
5. 运行 `npm ci` 和 `npm run dev`。
6. 打开 Vite 显示的 `Local` 地址。

## 8. 快速启动命令

后端窗口：

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

前端窗口：

```powershell
Set-Location frontend
npm ci
npm run dev
```
