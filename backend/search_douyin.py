"""搜索抖音助农直播间 - 处理弹窗版"""
import asyncio
from playwright.async_api import async_playwright


async def close_popups(page):
    """关闭抖音页面上的弹窗"""
    close_selectors = [
        # 登录弹窗关闭按钮
        'div[id*="login"] [class*="close"]',
        'div[class*="login"] [class*="close"]',
        '[id*="login-full-panel"] [class*="close"]',
        'div[class*="DYAppDownload"] [class*="close"]',
        # 通用关闭按钮
        '[class*="closeBtn"]',
        '[class*="close-btn"]',
        'button[class*="close"]',
        '[aria-label="关闭"]',
    ]
    for sel in close_selectors:
        try:
            btns = await page.query_selector_all(sel)
            for btn in btns:
                try:
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.3)
                        print(f"  关闭了弹窗: {sel}")
                except:
                    pass
        except:
            pass

    # 通过JS关闭弹窗
    try:
        await page.evaluate("""
            () => {
                // 关闭登录弹窗
                const loginPanel = document.querySelector('[id*="login-full-panel"]');
                if (loginPanel) loginPanel.style.display = 'none';
                const loginModal = document.querySelector('[class*="login-guide"]');
                if (loginModal) loginModal.remove();
                // 点击所有可见的关闭按钮
                document.querySelectorAll('[class*="close"], [class*="Close"]').forEach(el => {
                    try { if (el.offsetParent !== null) el.click(); } catch(e) {}
                });
            }
        """)
    except:
        pass


async def search_douyin():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="zh-CN",
    )
    page = await context.new_page()

    try:
        # 直接访问抖音直播间主页
        print("[1] 正在打开抖音直播主页...")
        await page.goto("https://live.douyin.com", timeout=30000)
        await asyncio.sleep(4)

        # 关闭弹窗
        print("[2] 关闭弹窗...")
        await close_popups(page)
        await asyncio.sleep(1)

        # 截图
        await page.screenshot(path="d:/Desktop/大学/比赛/第十六届三创赛/live-assist-platform/screenshots/douyin_live_home.png")
        print("[3] 直播主页截图已保存")

        # 获取直播间链接
        live_urls = set()
        all_links = await page.query_selector_all("a")
        print(f"[4] 页面共 {len(all_links)} 个链接")

        for link in all_links:
            try:
                href = await link.get_attribute("href")
                if href:
                    href = str(href)
                    # 匹配直播间链接格式：https://live.douyin.com/数字ID
                    if "live.douyin.com/" in href:
                        parts = href.split("live.douyin.com/")
                        if len(parts) > 1 and parts[1].strip("/").split("?")[0].isdigit():
                            if not href.startswith("http"):
                                if href.startswith("//"):
                                    href = "https:" + href
                            if href not in live_urls:
                                live_urls.add(href)
                                print(f"   找到直播间: {href}")
            except:
                continue

        # 如果主页没找到，尝试搜索页
        if not live_urls:
            print("[5] 主页未找到直播间，尝试搜索页...")
            await page.goto("https://www.douyin.com/search/%E5%8A%A9%E5%86%9C?type=live", timeout=30000)
            await asyncio.sleep(4)
            await close_popups(page)
            await asyncio.sleep(1)

            # 尝试点击搜索
            try:
                await page.keyboard.press("Escape")  # 先关闭弹窗
                await asyncio.sleep(0.5)
            except:
                pass

            await page.screenshot(path="d:/Desktop/大学/比赛/第十六届三创赛/live-assist-platform/screenshots/douyin_search.png")

            all_links = await page.query_selector_all("a")
            for link in all_links:
                try:
                    href = await link.get_attribute("href")
                    if href and "live.douyin.com/" in str(href):
                        full_url = str(href)
                        if not full_url.startswith("http"):
                            if full_url.startswith("//"):
                                full_url = "https:" + full_url
                            elif full_url.startswith("/"):
                                full_url = "https://www.douyin.com" + full_url
                        parts = full_url.split("live.douyin.com/")
                        if len(parts) > 1 and parts[1].strip("/").split("?")[0].isdigit():
                            live_urls.add(full_url)
                            print(f"   搜索结果直播间: {full_url}")
                except:
                    continue

        # 如果还是没找到，使用一个通用的测试URL
        if not live_urls:
            print("[6] 未找到具体直播间链接，将使用抖音直播首页作为测试")
            live_urls.add("https://live.douyin.com")

        print(f"\n[结果] 找到 {len(live_urls)} 个直播间链接:")
        for i, url in enumerate(live_urls):
            print(f"  {i+1}. {url}")

        # 保存结果
        import json
        result_list = list(live_urls)
        with open("d:/Desktop/大学/比赛/第十六届三创赛/live-assist-platform/data/douyin_live_urls.json", "w", encoding="utf-8") as f:
            json.dump(result_list, f, ensure_ascii=False, indent=2)

        # 进入一个直播间进行测试
        if result_list:
            test_url = result_list[0]
            print(f"\n[测试] 进入直播间: {test_url}")
            await page.goto(test_url, timeout=30000)
            await asyncio.sleep(4)
            await close_popups(page)
            await asyncio.sleep(1)
            await page.screenshot(path="d:/Desktop/大学/比赛/第十六届三创赛/live-assist-platform/screenshots/test_live_room.png")
            print("[测试] 直播间截图已保存")
            print(f"[测试] 当前URL: {page.url}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await browser.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(search_douyin())
