# AI Manhua Studio

AI Manhua Studio 是一个面向国漫短剧制作的本地工作台，可将小说文本或 TXT、DOCX、EPUB 文件处理为 Story Bible、剧集规划、剧本、分镜和可执行制作包。

## 功能

- 小说导入与章节解析
- DeepSeek 驱动的 Story Bible 分析
- 自动规划剧集冲突、高潮和悬念
- 自动生成剧集剧本
- 角色、场景与分镜资产管理
- 自动生成分镜及英文视觉提示词
- ComfyUI 图片生成
- 制作进度、审核和生产包导出

## 技术栈

- 后端：Python、FastAPI、SQLAlchemy、Pydantic
- 前端：Vue 3、Vite
- 文本和剧情模型：DeepSeek（默认 `deepseek-chat`）
- 本地图像生成：ComfyUI

## 环境要求

- macOS、Linux 或 Windows（推荐 macOS）
- Python 3.11+
- Node.js 18+
- 一个 DeepSeek API Key
- 可选：ComfyUI，用于本地图片生成

## 配置 DeepSeek

复制环境模板：

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，填入自己的密钥：

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key
MANHUA_LLM_PROVIDER=deepseek
MANHUA_DEEPSEEK_MODEL=deepseek-chat
MANHUA_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

也可以直接设置进当前终端环境：

```bash
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export MANHUA_LLM_PROVIDER="deepseek"
```

`backend/.env` 已被 `.gitignore` 排除，不会上传真实密钥。

要切换回本地 Ollama：

```dotenv
MANHUA_LLM_PROVIDER=ollama
MANHUA_MODEL=qwen3:4b
MANHUA_OLLAMA_URL=http://localhost:11434/api/chat
```

## 安装

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

cd ../frontend
npm install
```

## 启动

在项目根目录运行：

```bash
./start.sh
```

访问：

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

停止：

```bash
./stop.sh
```

## 主要工作流

1. 创建项目并导入小说。
2. 由 DeepSeek 分析 Story Bible。
3. 审核并生成剧集规划。
4. 按剧集生成剧本。
5. 审核角色、场景和分镜资产。
6. 在 ComfyUI 中生成画面。
7. 导出制作包。

## 环境变量

|变量|默认值|用途|
|---|---|---|
|`DEEPSEEK_API_KEY`|空|DeepSeek API 密钥|
|`MANHUA_LLM_PROVIDER`|`deepseek`|选择 `deepseek` 或 `ollama`|
|`MANHUA_DEEPSEEK_MODEL`|`deepseek-chat`|DeepSeek 模型|
|`MANHUA_DEEPSEEK_BASE_URL`|`https://api.deepseek.com`|DeepSeek OpenAI-compatible 基址|
|`MANHUA_MODEL`|`qwen3:4b`|Ollama 模型|
|`MANHUA_OLLAMA_URL`|`http://localhost:11434/api/chat`|Ollama 聊天接口|

## 安全说明

不要把 API Key 提交到 GitHub。所有密钥应放在 `backend/.env` 或进程环境变量中。
