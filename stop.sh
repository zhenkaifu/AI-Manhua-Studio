#!/bin/bash
# AI Manhua Studio 一键关闭
echo "🛑 关闭所有服务..."
lsof -ti:8000 | xargs kill -9 2>/dev/null && echo "   后端已关闭"
lsof -ti:5173 | xargs kill -9 2>/dev/null && echo "   前端已关闭"
lsof -ti:8188 | xargs kill -9 2>/dev/null && echo "   ComfyUI 已关闭"
echo "✅ 全部关闭，电脑可以降温了"
