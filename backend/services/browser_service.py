"""
浏览器自动化服务 - 基于Playwright (同步API + 线程池)
负责直播间页面控制、截图采集、评论抓取、弹窗关闭

关键设计：使用 playwright.sync_api 在独立线程中运行，
通过 concurrent.futures 提交任务，避免与 uvicorn 的 SelectorEventLoop 冲突
"""
import asyncio
import os
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

from config import SCREENSHOT_DIR, SCREENSHOT_QUALITY, SCREENSHOT_INTERVAL, POPUP_CHECK_INTERVAL


class BrowserService:
    """浏览器自动化服务 - 控制Playwright浏览器实例（同步线程池模式）"""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)  # 单线程执行器，确保Playwright操作串行

        # 线程安全的状态
        self.is_running = False
        self.live_url = ""
        self.screenshots = []
        self.comments = []
        self.session_start_time = None
        self.viewer_count = "0"
        self.like_count = "0"

    @property
    def page(self):
        """公开page属性，供外部检查页面是否存在"""
        return self._page

    async def _run_sync(self, func, *args, timeout=15, **kwargs):
        """在线程池中运行同步Playwright函数，带超时保护
        默认15秒超时，防止Playwright操作卡死拖累整个事件循环
        """
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(self._executor, func, *args, **kwargs)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[浏览器服务] 操作超时({timeout}s): {func.__name__ if hasattr(func, '__name__') else func}")
            return None

    def _sync_start(self, headless: bool = False):
        """同步启动浏览器（在线程池中调用）"""
        if self._browser:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--window-size=1280,800',
            ]
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="zh-CN",
        )
        self._page = self._context.new_page()
        self.is_running = True
        print("[浏览器服务] 浏览器已启动")

    def _sync_stop(self):
        """同步停止浏览器（在线程池中调用）"""
        self.is_running = False

        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        print("[浏览器服务] 浏览器已关闭")

    async def start(self, headless: bool = False):
        """启动浏览器"""
        await self._run_sync(self._sync_start, headless)

    async def stop(self):
        """停止浏览器并清理资源"""
        self.is_running = False
        await self._run_sync(self._sync_stop)

    async def navigate_to_live(self, url: str):
        """导航到直播间页面"""
        if not self._page:
            await self.start()

        self.live_url = url
        self.session_start_time = time.time()

        def _navigate():
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                print(f"[浏览器服务] 已导航到: {url}")
                return {"success": True, "message": f"已连接到直播间: {url}"}
            except Exception as e:
                print(f"[浏览器服务] 导航失败: {e}")
                return {"success": False, "message": f"连接失败: {str(e)}"}

        return await self._run_sync(_navigate)

    async def take_screenshot(self) -> Optional[str]:
        """截取当前页面截图"""
        if not self._page:
            return None

        def _screenshot():
            try:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.jpg"
                filepath = os.path.join(SCREENSHOT_DIR, filename)

                self._page.screenshot(
                    path=filepath,
                    type="jpeg",
                    quality=SCREENSHOT_QUALITY,
                    full_page=False,
                    timeout=10000,  # 10秒内必须完成截图
                )

                with self._lock:
                    self.screenshots.append({
                        "filename": filename,
                        "filepath": filepath,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "url": self._page.url if self._page else "",
                    })

                    if len(self.screenshots) > 100:
                        old = self.screenshots.pop(0)
                        try:
                            os.remove(old["filepath"])
                        except OSError:
                            pass

                print(f"[浏览器服务] 截图已保存: {filename}")
                return filepath

            except Exception as e:
                print(f"[浏览器服务] 截图失败: {e}")
                return None

        return await self._run_sync(_screenshot)

    async def detect_and_close_popup(self) -> dict:
        """检测并关闭弹窗"""
        if not self._page:
            return {"closed": False, "message": "页面未就绪"}

        def _detect_popup():
            closed_popups = []
            try:
                close_selectors = [
                    'button[class*="close"]',
                    'div[class*="close"]',
                    '[class*="modal"] [class*="close"]',
                    '[class*="dialog"] [class*="close"]',
                    'svg[class*="close"]',
                    '[aria-label="关闭"]',
                    '[aria-label="Close"]',
                    'div[class*="login-guide"] [class*="close"]',
                    'div[class*="DYAppDownload"] [class*="close"]',
                    'div[class*="follow"] [class*="close"]',
                    'div[data-e2e="live-chat-follow-guide-close"]',
                    'div[class*="popup"] [class*="close"]',
                    '.close-btn',
                    '.close-button',
                    '[class*="icon-close"]',
                    '[class*="IconClose"]',
                    'button[class*="dismiss"]',
                ]

                for selector in close_selectors:
                    try:
                        elements = self._page.query_selector_all(selector)
                        for el in elements:
                            try:
                                if el.is_visible():
                                    el.click()
                                    closed_popups.append(selector)
                                    time.sleep(0.5)
                            except Exception:
                                continue
                    except Exception:
                        continue

                # JS注入关闭弹窗
                try:
                    popup_closed = self._page.evaluate("""
                        () => {
                            let closed = [];
                            const closeButtons = document.querySelectorAll(
                                '[class*="close"], [class*="Close"], [class*="dismiss"], [aria-label="关闭"], [aria-label="Close"]'
                            );
                            closeButtons.forEach(btn => {
                                try {
                                    const rect = btn.getBoundingClientRect();
                                    const parent = btn.closest('[class*="modal"], [class*="dialog"], [class*="popup"], [class*="overlay"]');
                                    if (parent && rect.width > 0 && rect.height > 0) {
                                        btn.click();
                                        closed.push(btn.className);
                                    }
                                } catch(e) {}
                            });
                            return closed;
                        }
                    """)
                    if popup_closed:
                        closed_popups.extend(popup_closed)
                except Exception:
                    pass

                if closed_popups:
                    print(f"[浏览器服务] 关闭了 {len(closed_popups)} 个弹窗")
                    return {"closed": True, "count": len(closed_popups), "selectors": closed_popups}
                else:
                    return {"closed": False, "message": "未检测到弹窗"}

            except Exception as e:
                return {"closed": False, "message": f"弹窗检测出错: {str(e)}"}

        return await self._run_sync(_detect_popup)

    async def scrape_comments(self) -> list:
        """抓取直播间评论"""
        if not self._page:
            return []

        def _scrape():
            new_comments = []
            try:
                # 方法1: JS注入方式 - 最可靠，直接在页面JS中查找
                try:
                    js_comments = self._page.evaluate("""() => {
                        const results = [];
                        // 抖音直播间评论区选择器（多版本兼容）
                        const itemSelectors = [
                            'div.webcast-chatroom___item',
                            'div.webcast-chatroom___item_new',
                            '.webcast-chatroom___item-wrapper',
                            'div[class*="chatroom___item"]',
                            'div[data-e2e="chat-message"]',
                            'div[class*="ChatRoom"] div[class*="message"]',
                            'div[class*="chatroom"] div[class*="item"]',
                            // 2025新版本选择器
                            'div[class*="im-message"]',
                            'div[class*="chat-msg"]',
                        ];
                        for (const sel of itemSelectors) {
                            try {
                                const els = document.querySelectorAll(sel);
                                if (els.length > 0) {
                                    for (const el of els) {
                                        const text = el.innerText || el.textContent || '';
                                        if (text.trim()) {
                                            results.push(text.trim());
                                        }
                                    }
                                    break;  // 找到匹配的选择器后停止
                                }
                            } catch(e) {}
                        }
                        
                        // 备选：如果上述选择器都失败，尝试更宽泛的搜索
                        if (results.length === 0) {
                            try {
                                // 查找聊天区域容器
                                const chatroom = document.querySelector(
                                    'div[class*="chatroom"], div[data-e2e="chatroom"], div[class*="ChatRoom"]'
                                );
                                if (chatroom) {
                                    const items = chatroom.querySelectorAll('div[class*="item"], div[class*="message"], div[class*="msg"]');
                                    items.forEach(el => {
                                        const text = (el.innerText || el.textContent || '').trim();
                                        if (text && text.length > 1 && text.length < 200) {
                                            results.push(text);
                                        }
                                    });
                                }
                            } catch(e) {}
                        }
                        
                        return results.slice(-30);
                    }""")
                    print(f"[评论采集] JS采集到 {len(js_comments) if js_comments else 0} 条评论")

                    if js_comments:
                        for text in js_comments:
                            parts = text.split("：", 1)
                            if len(parts) == 2:
                                user, content = parts
                            else:
                                user = "匿名"
                                content = text

                            comment_data = {
                                "user": user.strip(),
                                "content": content.strip(),
                                "time": time.strftime("%H:%M:%S"),
                                "timestamp": time.time(),
                            }

                            with self._lock:
                                existing_contents = [c["content"] for c in self.comments[-100:]]
                                if content.strip() not in existing_contents:
                                    self.comments.append(comment_data)
                                    new_comments.append(comment_data)
                except Exception as e:
                    print(f"[浏览器服务] JS评论采集出错: {e}")

                # 方法2: Playwright选择器兜底（JS失败时使用）
                if not new_comments:
                    comment_selectors = [
                        'div.webcast-chatroom___item',
                        'div.webcast-chatroom___item_new',
                        '[data-e2e="chat-message"]',
                        'div[class*="chat-message"]',
                        'div[class*="ChatMessage"]',
                        'div[class*="chatroom-content"] div[class*="message"]',
                        'div[class*="comment-item"]',
                    ]

                    for selector in comment_selectors:
                        try:
                            elements = self._page.query_selector_all(selector)
                            if elements:
                                for el in elements:
                                    try:
                                        text = el.inner_text()
                                        if text and text.strip():
                                            parts = text.strip().split("：", 1)
                                            if len(parts) == 2:
                                                user, content = parts
                                            else:
                                                user = "匿名"
                                                content = text.strip()

                                            comment_data = {
                                                "user": user.strip(),
                                                "content": content.strip(),
                                                "time": time.strftime("%H:%M:%S"),
                                                "timestamp": time.time(),
                                            }

                                            with self._lock:
                                                existing_contents = [c["content"] for c in self.comments[-100:]]
                                                if content.strip() not in existing_contents:
                                                    self.comments.append(comment_data)
                                                    new_comments.append(comment_data)

                                    except Exception:
                                        continue
                                break
                        except Exception:
                            continue

                with self._lock:
                    if len(self.comments) > 500:
                        self.comments = self.comments[-500:]

                if new_comments:
                    print(f"[评论采集] 新增 {len(new_comments)} 条评论，总计 {len(self.comments)} 条")

            except Exception as e:
                print(f"[浏览器服务] 评论抓取出错: {e}")

            return new_comments

        return await self._run_sync(_scrape)

    async def get_live_info(self) -> dict:
        """获取直播间基本信息"""
        if not self._page:
            return {}

        def _get_info():
            info = {
                "url": self._page.url if self._page else "",
                "title": "",
                "duration": "",
                "viewer_count": "0",
                "like_count": "0",
            }

            try:
                info["title"] = self._page.title()
            except Exception:
                pass

            try:
                viewer_selectors = [
                    '[class*="viewer"]',
                    '[class*="watching"]',
                    '[data-e2e="live-viewer-count"]',
                    'div[class*="user-count"]',
                ]
                for selector in viewer_selectors:
                    try:
                        el = self._page.query_selector(selector)
                        if el:
                            text = el.inner_text()
                            if text and text.strip():
                                info["viewer_count"] = text.strip()
                                self.viewer_count = text.strip()
                                break
                    except Exception:
                        continue
            except Exception:
                pass

            if self.session_start_time:
                elapsed = int(time.time() - self.session_start_time)
                hours, remainder = divmod(elapsed, 3600)
                minutes, seconds = divmod(remainder, 60)
                info["duration"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            return info

        return await self._run_sync(_get_info)

    async def start_monitoring(self):
        """启动直播监控（不再启动独立循环，由auto_analysis_loop统一调度）"""
        self.is_running = True
        print("[浏览器服务] 监控已启动（统一调度模式）")

    async def stop_monitoring(self):
        """停止监控"""
        self.is_running = False
        print("[浏览器服务] 监控已停止")

    def get_status(self) -> dict:
        """获取当前服务状态"""
        duration = ""
        if self.session_start_time:
            elapsed = int(time.time() - self.session_start_time)
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return {
            "is_running": self.is_running,
            "browser_active": self._browser is not None,
            "live_url": self.live_url,
            "duration": duration,
            "screenshot_count": len(self.screenshots),
            "comment_count": len(self.comments),
            "viewer_count": self.viewer_count,
        }

    def get_recent_screenshots(self, count: int = 10) -> list:
        """获取最近的截图记录"""
        with self._lock:
            return self.screenshots[-count:]

    def get_recent_comments(self, count: int = 50) -> list:
        """获取最近的评论"""
        with self._lock:
            return self.comments[-count:]


# 全局浏览器服务实例
browser_service = BrowserService()
