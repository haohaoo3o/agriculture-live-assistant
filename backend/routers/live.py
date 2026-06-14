"""
API路由 - 直播间控制接口
包含HTTP API和WebSocket实时通信
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional

from services.browser_service import browser_service
from services.ai_service import ai_service
from services.data_service import data_service

# AI专用线程池，避免占用默认线程池导致HTTP请求阻塞
_ai_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ai_worker")

async def ai_call(func, *args):
    """在线程池中执行AI同步调用，不阻塞事件循环"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ai_executor, func, *args)

router = APIRouter(prefix="/api/live", tags=["直播控制"])

# ===== 全局状态 =====
is_monitoring = False
auto_analysis_task = None


class LiveConnectRequest(BaseModel):
    url: str
    headless: bool = False


class ComplianceCheckRequest(BaseModel):
    text: str


class SuggestionRequest(BaseModel):
    context: dict = {}


class CommentReplyRequest(BaseModel):
    comment: str
    context: str = ""


# ===== 直播间连接 =====

@router.post("/connect")
async def connect_live(request: LiveConnectRequest):
    """连接直播间"""
    try:
        if not browser_service.is_running:
            await browser_service.start(headless=request.headless)
        result = await browser_service.navigate_to_live(request.url)
        if result["success"]:
            session_id = data_service.start_session(request.url)
            result["session_id"] = session_id
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"连接出错: {str(e)}"}


@router.post("/disconnect")
async def disconnect_live():
    """断开直播间连接"""
    global is_monitoring, auto_analysis_task
    is_monitoring = False

    # 停止自动分析任务
    if auto_analysis_task and not auto_analysis_task.done():
        auto_analysis_task.cancel()
        auto_analysis_task = None

    data_service.end_session()
    await browser_service.stop_monitoring()
    await browser_service.stop()

    await manager.broadcast({"type": "disconnected", "data": {"message": "已断开连接"}})

    return {"success": True, "message": "已断开直播间连接"}


# ===== 监控控制 =====

@router.post("/start-monitoring")
async def start_monitoring():
    """启动直播监控"""
    global is_monitoring, auto_analysis_task
    try:
        await browser_service.start_monitoring()
        is_monitoring = True

        # 启动自动分析任务
        if auto_analysis_task is None or auto_analysis_task.done():
            auto_analysis_task = asyncio.create_task(auto_analysis_loop())

        return {"success": True, "message": "监控已启动"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"启动监控出错: {str(e)}"}


@router.post("/stop-monitoring")
async def stop_monitoring():
    """停止直播监控"""
    global is_monitoring, auto_analysis_task
    try:
        is_monitoring = False

        # 停止自动分析
        if auto_analysis_task and not auto_analysis_task.done():
            auto_analysis_task.cancel()
            auto_analysis_task = None

        await browser_service.stop_monitoring()
        return {"success": True, "message": "监控已停止"}
    except Exception as e:
        return {"success": False, "message": f"停止监控出错: {str(e)}"}


# ===== 状态查询 =====

@router.get("/status")
async def get_status():
    """获取直播状态"""
    status = browser_service.get_status()
    try:
        live_info = await browser_service.get_live_info()
        status.update(live_info)
    except Exception:
        pass
    status["is_monitoring"] = is_monitoring
    return status


# ===== 截图 =====

@router.post("/screenshot")
async def take_screenshot():
    """手动截图"""
    try:
        filepath = await browser_service.take_screenshot()
        if filepath:
            return {"success": True, "filepath": filepath}
        return {"success": False, "message": "截图失败 - 可能页面未就绪或浏览器已关闭"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"截图出错: {str(e)}"}


# ===== 弹窗 =====

@router.post("/detect-popup")
async def detect_popup():
    """检测并关闭弹窗"""
    result = await browser_service.detect_and_close_popup()
    return result


# ===== 评论 =====

@router.get("/comments")
async def get_comments(count: int = 50):
    """获取评论数据"""
    comments = browser_service.get_recent_comments(count)
    return {"comments": comments, "total": len(comments)}


# ===== AI分析 =====

@router.post("/analyze-screenshot")
async def analyze_screenshot():
    """AI分析当前截图"""
    screenshots = browser_service.get_recent_screenshots(1)
    if not screenshots:
        filepath = await browser_service.take_screenshot()
        if not filepath:
            return {"success": False, "message": "截图失败，无法分析"}
    else:
        filepath = screenshots[-1]["filepath"]

    live_info = await browser_service.get_live_info()
    context = f"直播时长: {live_info.get('duration', '未知')}, 观众数: {live_info.get('viewer_count', '未知')}"
    result = await ai_call(ai_service.analyze_live_screenshot, filepath, context)
    data_service.record_screenshot_analysis(result)

    # 通过WebSocket广播
    await manager.broadcast({"type": "analysis", "data": result})

    return {"success": True, "analysis": result, "screenshot": filepath}


@router.post("/detect-product")
async def detect_product():
    """AI商品识别"""
    screenshots = browser_service.get_recent_screenshots(1)
    if not screenshots:
        filepath = await browser_service.take_screenshot()
        if not filepath:
            return {"success": False, "message": "截图失败"}
    else:
        filepath = screenshots[-1]["filepath"]

    result = await ai_call(ai_service.recognize_product, filepath)
    data_service.record_product_detection(result)

    await manager.broadcast({"type": "product", "data": result})

    return {"success": True, "product": result}


# ===== 合规检测 =====

@router.post("/check-compliance")
async def check_compliance(request: ComplianceCheckRequest):
    """合规检测（纯文本，兼容旧接口）"""
    result = await ai_call(ai_service.check_compliance, request.text)
    data_service.record_compliance_check(result)

    await manager.broadcast({"type": "compliance", "data": result})

    return {"success": True, "result": result}


@router.post("/check-compliance-auto")
async def check_compliance_auto():
    """自动合规检测 - 基于当前直播截图+评论内容，无需人工输入"""
    # 获取最新截图
    screenshots = browser_service.get_recent_screenshots(1)
    if not screenshots:
        filepath = await browser_service.take_screenshot()
        if not filepath:
            return {"success": False, "message": "截图失败，无法检测"}
    else:
        filepath = screenshots[-1]["filepath"]

    # 收集文本上下文（最近的评论内容）
    text_context = ""
    if browser_service.comments:
        recent_texts = [c["content"] for c in browser_service.comments[-10:]]
        text_context = " ".join(recent_texts)

    # 调用多模态合规检测
    result = await ai_call(ai_service.check_compliance_from_screenshot, filepath, text_context)
    data_service.record_compliance_check(result)

    await manager.broadcast({"type": "compliance", "data": result})

    return {"success": True, "result": result, "screenshot": filepath}


# ===== 评论分析 =====

@router.post("/analyze-comments")
async def analyze_comments():
    """AI评论分析"""
    comments = browser_service.get_recent_comments(50)
    result = await ai_call(ai_service.analyze_comments, comments)
    data_service.record_comment_analysis(result)

    await manager.broadcast({"type": "comment_analysis", "data": result})

    return {"success": True, "analysis": result}


# ===== 评论回复建议（新功能）=====

@router.post("/comment-reply-suggestion")
async def comment_reply_suggestion(request: CommentReplyRequest):
    """AI生成评论回复建议"""
    result = await ai_call(ai_service.generate_comment_reply, request.comment, request.context)
    return {"success": True, "reply_suggestions": result}


# ===== 直播建议 =====

@router.post("/suggestions")
async def get_suggestions(request: SuggestionRequest):
    """获取直播建议"""
    live_info = await browser_service.get_live_info()
    context = {
        "duration": live_info.get("duration", "未知"),
        "viewer_count": live_info.get("viewer_count", "未知"),
        "comment_count": str(len(browser_service.comments)),
        "current_product": request.context.get("current_product", "未知"),
        "last_analysis": request.context.get("last_analysis", "无"),
    }
    result = await ai_call(ai_service.generate_live_suggestions, context)
    data_service.record_live_suggestion(result)

    await manager.broadcast({"type": "suggestions", "data": result})

    return {"success": True, "suggestions": result}


# ===== 数据查询 =====

@router.get("/session-summary")
async def get_session_summary():
    """获取会话摘要"""
    return data_service.get_session_summary()


@router.get("/business-profile")
async def get_business_profile():
    """获取经营画像"""
    return data_service.generate_business_profile()


@router.get("/screenshots")
async def get_screenshots(count: int = 10):
    """获取截图列表"""
    screenshots = browser_service.get_recent_screenshots(count)
    return {"screenshots": screenshots}


# ===== 自动分析循环 =====

async def auto_analysis_loop():
    """
    统一调度循环 - 整合截图、评论采集、弹窗检测和AI分析
    消除重复截图和Playwright线程池竞争问题
    
    调度节奏：
    - 每30秒：截图 + 评论采集 + 弹窗检测 + AI画面分析
    - 每2轮：商品识别 + 合规检测
    - 每3轮：直播建议
    - 每4轮：评论分析
    
    防卡机制：
    - Playwright操作20秒超时保护
    - AI调用90秒超时保护
    - 连续5次截图失败自动暂停60秒恢复
    - 每步独立try/except，单步失败不影响后续
    """
    import base64
    
    cycle_count = 0
    last_screenshot_path = None
    consecutive_failures = 0
    MAX_FAILURES = 5
    
    while True:
        try:
            if not browser_service.is_running or not browser_service.page:
                await asyncio.sleep(5)
                continue

            cycle_count += 1
            print(f"[调度] #{cycle_count} 开始...")

            # 1. 截图（20秒超时）
            filepath = None
            try:
                filepath = await asyncio.wait_for(browser_service.take_screenshot(), timeout=20)
                if filepath:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    print(f"[调度] 截图返回None ({consecutive_failures}/{MAX_FAILURES})")
            except asyncio.TimeoutError:
                consecutive_failures += 1
                print(f"[调度] 截图超时 ({consecutive_failures}/{MAX_FAILURES})")
            except Exception as e:
                consecutive_failures += 1
                print(f"[调度] 截图异常: {e}")
            
            if consecutive_failures >= MAX_FAILURES:
                print(f"[调度] 连续{MAX_FAILURES}次失败，暂停60秒...")
                await manager.broadcast({
                    "type": "system_warning",
                    "data": {"message": f"截图连续失败{MAX_FAILURES}次，暂停60秒等待恢复", "level": "warning"}
                })
                await asyncio.sleep(60)
                consecutive_failures = 0
                continue
            
            # 2. 评论采集（15秒超时）
            try:
                new_comments = await asyncio.wait_for(browser_service.scrape_comments(), timeout=15)
                if new_comments:
                    await manager.broadcast({"type": "new_comments", "data": new_comments})
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"[调度] 评论采集: {e}")
            
            # 3. 弹窗检测（每3轮）
            if cycle_count % 3 == 0:
                try:
                    await asyncio.wait_for(browser_service.detect_and_close_popup(), timeout=10)
                except Exception:
                    pass

            # 4. AI画面分析（90秒超时，含Base64编码）
            if filepath:
                last_screenshot_path = filepath
                
                live_info = {}
                try:
                    li = await asyncio.wait_for(browser_service.get_live_info(), timeout=10)
                    if li: live_info = li
                except Exception:
                    pass
                
                img_base64 = ""
                try:
                    with open(filepath, "rb") as f:
                        img_base64 = base64.b64encode(f.read()).decode("utf-8")
                except Exception:
                    pass

                try:
                    context = f"直播时长: {live_info.get('duration', '未知')}, 观众数: {live_info.get('viewer_count', '未知')}"
                    analysis = await asyncio.wait_for(
                        ai_call(ai_service.analyze_live_screenshot, filepath, context), timeout=90)
                    if analysis:
                        data_service.record_screenshot_analysis(analysis)
                        await manager.broadcast({
                            "type": "auto_screenshot",
                            "data": {
                                "filepath": filepath,
                                "filename": filepath.split("\\").pop().split("/").pop(),
                                "image_base64": img_base64,
                                "analysis": analysis,
                            }
                        })
                except asyncio.TimeoutError:
                    print("[调度] AI画面分析超时(90s)")
                except Exception as e:
                    print(f"[调度] AI画面分析: {e}")

            # 5. 商品识别（每2轮，90秒超时）
            if cycle_count % 2 == 0 and last_screenshot_path:
                try:
                    product = await asyncio.wait_for(
                        ai_call(ai_service.recognize_product, last_screenshot_path), timeout=90)
                    if product:
                        data_service.record_product_detection(product)
                        await manager.broadcast({"type": "product", "data": product})
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"[调度] 商品识别: {e}")

            # 6. 合规检测（每2轮，90秒超时）
            if cycle_count % 2 == 0 and last_screenshot_path:
                try:
                    text_ctx = ""
                    if browser_service.comments:
                        text_ctx = " ".join([c["content"] for c in browser_service.comments[-10:]])
                    cr = await asyncio.wait_for(
                        ai_call(ai_service.check_compliance_from_screenshot, last_screenshot_path, text_ctx), timeout=90)
                    if cr:
                        data_service.record_compliance_check(cr)
                        await manager.broadcast({"type": "compliance", "data": cr})
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"[调度] 合规检测: {e}")

            # 7. 直播建议（每3轮，90秒超时）
            if cycle_count % 3 == 0:
                live_info = {}
                try:
                    li = await asyncio.wait_for(browser_service.get_live_info(), timeout=10)
                    if li: live_info = li
                except Exception:
                    pass
                try:
                    sctx = {
                        "duration": live_info.get("duration", "未知"),
                        "viewer_count": live_info.get("viewer_count", "未知"),
                        "comment_count": str(len(browser_service.comments)),
                        "current_product": "当前直播商品",
                        "last_analysis": "来自自动分析",
                    }
                    suggestions = await asyncio.wait_for(
                        ai_call(ai_service.generate_live_suggestions, sctx), timeout=90)
                    if suggestions:
                        data_service.record_live_suggestion(suggestions)
                        await manager.broadcast({"type": "suggestions", "data": suggestions})
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"[调度] 直播建议: {e}")

            # 8. 评论分析（每4轮，90秒超时）
            if cycle_count % 4 == 0 and browser_service.comments:
                try:
                    ca = await asyncio.wait_for(
                        ai_call(ai_service.analyze_comments, browser_service.comments[-50:]), timeout=90)
                    if ca:
                        data_service.record_comment_analysis(ca)
                        await manager.broadcast({"type": "comment_analysis", "data": ca})
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"[调度] 评论分析: {e}")

            # 广播实时状态
            status = browser_service.get_status()
            try:
                li = await asyncio.wait_for(browser_service.get_live_info(), timeout=8)
                if li: status.update(li)
            except Exception:
                pass
            status["is_monitoring"] = is_monitoring
            status["recent_comments"] = browser_service.get_recent_comments(5)
            await manager.broadcast({"type": "live_update", "data": status})

            print(f"[调度] #{cycle_count} 完成")

            if cycle_count % 3 == 0:
                data_service._flush_if_dirty()

            await asyncio.sleep(30)

        except asyncio.CancelledError:
            print("[调度] 已取消")
            break
        except Exception as e:
            print(f"[调度] 严重错误: {e}")
            import traceback; traceback.print_exc()
            consecutive_failures += 1
            await asyncio.sleep(20)


# ===== WebSocket 实时通信 =====

class ConnectionManager:
    """WebSocket连接管理器"""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket实时数据推送"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command", "")

            if command == "get_status":
                status = browser_service.get_status()
                try:
                    live_info = await browser_service.get_live_info()
                    status.update(live_info)
                except Exception:
                    pass
                status["is_monitoring"] = is_monitoring
                await websocket.send_json({"type": "status", "data": status})

            elif command == "get_comments":
                comments = browser_service.get_recent_comments(20)
                await websocket.send_json({"type": "comments", "data": comments})

            elif command == "take_screenshot":
                filepath = await browser_service.take_screenshot()
                await websocket.send_json({"type": "screenshot", "data": {"filepath": filepath}})

            elif command == "analyze":
                filepath = await browser_service.take_screenshot()
                if filepath:
                    live_info = await browser_service.get_live_info()
                    context = f"直播时长: {live_info.get('duration', '未知')}"
                    result = await ai_call(ai_service.analyze_live_screenshot, filepath, context)
                    data_service.record_screenshot_analysis(result)
                    await websocket.send_json({"type": "analysis", "data": result})

    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def broadcast_live_updates():
    """定期广播直播更新（由主应用调用）
    注意：主要的状态广播已移入auto_analysis_loop统一调度，
    此处仅作为轻量级心跳保活，频率降低到10秒
    """
    while True:
        if browser_service.is_running and browser_service.page:
            try:
                # 轻量级心跳：只广播基本状态，不触发Playwright操作
                status = browser_service.get_status()
                status["is_monitoring"] = is_monitoring
                await manager.broadcast({"type": "live_update", "data": status})
            except Exception:
                pass

        await asyncio.sleep(10)
