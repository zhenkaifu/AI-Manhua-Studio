#!/bin/bash
# AI Manhua Studio 一键启动
cd "$(dirname "$0")"

echo "🚀 启动后端 (FastAPI, 端口 8000)..."
cd backend
nohup .venv/bin/python main.py > /tmp/manhua_backend.log 2>&1 &
cd ..

echo "🎨 启动前端 (Vite, 端口 5173)..."
cd frontend
nohup npm run dev > /tmp/manhua_frontend.log 2>&1 &
cd ..

sleep 8
echo ""
echo "✅ 启动完成！"
echo "   打开浏览器访问: http://localhost:5173"
echo ""
echo "💡 ComfyUI 不用手动启动，生成图片时会自动拉起"
echo "   关闭项目: 运行 ./stop.sh"
