"""
FastAPI 主应用 - 面向三农场景的直播电商人工智能辅助平台
启动命令: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config import FRONTEND_DIR, HOST, PORT, get_api_key
from routers.live import router as live_router, broadcast_live_updates

# 将backend目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("=" * 60)
    print("  面向三农场景的直播电商人工智能辅助平台")
    print("  AI-Powered Live Commerce Assistant for Agriculture")
    print("=" * 60)
    print(f"  访问地址: http://localhost:{PORT}")
    print(f"  API文档: http://localhost:{PORT}/docs")
    print("=" * 60)

    # API Key 检查
    if not get_api_key():
        print()
        print("  ⚠  警告：未检测到 API Key！")
        print("  ⚠  请复制 .env.example 为 .env 并填入你的 API Key")
        print("  ⚠  详见 README.md 中的配置说明")
        print()

    # 启动后台广播任务
    broadcast_task = asyncio.create_task(broadcast_live_updates())

    yield

    # 关闭时
    broadcast_task.cancel()
    from services.browser_service import browser_service
    await browser_service.stop()
    print("[平台] 服务已关闭")


app = FastAPI(
    title="面向三农场景的直播电商人工智能辅助平台",
    description="""
    ## 平台简介
    本平台是面向三农直播场景的AI辅助系统，核心功能包括：
    
    - 🎥 **直播监控**：接入抖音直播间，实时截图与AI分析
    - 🛒 **商品识别**：AI自动识别直播中的农产品信息
    - 💬 **评论分析**：实时抓取并分析直播评论
    - ⚖️ **合规检测**：直播用语合规风险提示
    - 📊 **数据记录**：直播过程数据化，生成经营画像
    - 💡 **直播建议**：AI实时给出直播优化建议
    
    > 辅助农户把直播"做对、做稳、做规范"
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(live_router)

# 静态文件
static_dir = os.path.join(FRONTEND_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """首页 - 返回前端页面"""
    index_path = os.path.join(FRONTEND_DIR, "templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>平台启动中... 请确保前端文件已就绪</h1>"


@app.get("/screenshots/{filename}")
async def get_screenshot(filename: str):
    """获取截图文件"""
    from config import SCREENSHOT_DIR
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    if os.path.exists(filepath):
        return FileResponse(filepath)
    return {"error": "截图不存在"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
