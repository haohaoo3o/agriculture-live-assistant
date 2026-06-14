"""
搜索抖音助农直播间 V7 - 精确查找助农分类
"""
from playwright.sync_api import sync_playwright
import time
import json
import re
import os

def find_zhunong_lives():
    live_urls = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # 拦截API响应获取直播间数据
        api_room_ids = []
        
        def handle_response(response):
            url = response.url
            if any(kw in url for kw in ["webcast/room", "live/room", "api/live"]):
                try:
                    body = response.text()
                    room_ids = re.findall(r'"room_id"\s*:\s*"(\d{10,20})"', body)
                    for rid in room_ids:
                        if rid not in api_room_ids:
                            api_room_ids.append(rid)
                except:
                    pass
        
        page.on("response", handle_response)
        
        # ===== 第1步: 访问直播频道 =====
        print("[1] 访问 live.douyin.com...")
        page.goto("https://live.douyin.com/", timeout=60000, wait_until="domcontentloaded")
        time.sleep(8)
        close_popups(page)
        
        # ===== 第2步: 查找并点击"更多直播"或分类 =====
        print("\n[2] 查找分类区域...")
        
        # 先看看页面上有什么分类标签
        categories = page.evaluate("""() => {
            const items = document.querySelectorAll('a, button, span, div');
            const cats = [];
            items.forEach(el => {
                const text = el.innerText?.trim() || '';
                if (text.length > 0 && text.length < 10 && 
                    !['全部', '推荐', '关注'].includes(text)) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        cats.push({text, tag: el.tagName, href: el.href || '', id: el.id || ''});
                    }
                }
            });
            // 去重
            const seen = new Set();
            return cats.filter(c => {
                if (seen.has(c.text)) return false;
                seen.add(c.text);
                return true;
            }).slice(0, 50);
        }""")
        print(f"  页面元素: {[c['text'] for c in categories[:30]]}")
        
        # 查找"更多直播"按钮
        more_btn = None
        for cat in categories:
            if "更多" in cat['text']:
                try:
                    more_btn = page.query_selector(f'text="{cat["text"]}"')
                    if more_btn:
                        more_btn.click()
                        print(f"  点击了 '{cat['text']}' 按钮")
                        time.sleep(3)
                        break
                except:
                    pass
        
        # 看看点击后有没有更多分类
        categories2 = page.evaluate("""() => {
            const items = document.querySelectorAll('a, span, div');
            const cats = [];
            items.forEach(el => {
                const text = el.innerText?.trim() || '';
                if (text.length > 0 && text.length < 10) {
                    cats.push(text);
                }
            });
            return [...new Set(cats)].slice(0, 80);
        }""")
        print(f"  点击后页面元素: {categories2}")
        
        # 尝试查找并点击助农相关分类
        for keyword in ["助农", "三农", "农业", "乡村", "美食", "生活"]:
            try:
                el = page.query_selector(f'a:has-text("{keyword}"), span:has-text("{keyword}"), div:has-text("{keyword}")')
                if el:
                    el.click()
                    print(f"  ✅ 点击了分类 '{keyword}'")
                    time.sleep(5)
                    break
            except:
                pass
        
        # 提取当前页面上的直播间
        extract_live_ids(page, live_urls)
        
        # 从API拦截中提取
        for rid in api_room_ids:
            url = f"https://live.douyin.com/{rid}"
            if url not in live_urls:
                live_urls.append(url)
                print(f"  API拦截发现: {rid}")
        
        # 滚动加载更多
        for i in range(5):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)
        extract_live_ids(page, live_urls)
        for rid in api_room_ids:
            url = f"https://live.douyin.com/{rid}"
            if url not in live_urls:
                live_urls.append(url)
        
        # ===== 第3步: 尝试直接搜索(需登录) - 在搜索框输入助农 =====
        if len(live_urls) < 3:
            print("\n[3] 尝试在live.douyin.com搜索...")
            try:
                # 找搜索框
                search_input = page.query_selector('input[placeholder*="搜索"], input[type="search"]')
                if search_input:
                    search_input.fill("助农")
                    search_input.press("Enter")
                    print("  输入'助农'搜索")
                    time.sleep(8)
                    extract_live_ids(page, live_urls)
            except:
                pass
        
        # ===== 第4步: 直接访问一些已知助农直播间模式 =====
        # 重新访问首页，这次专门看页面内容中有没有助农主播
        print(f"\n[4] 当前找到 {len(live_urls)} 个直播间，访问直播首页找助农...")
        page.remove_listener("response", handle_response)
        page.goto("https://live.douyin.com/", timeout=30000, wait_until="domcontentloaded")
        time.sleep(6)
        close_popups(page)
        
        # 获取所有直播间卡片中的标题文本
        cards_info = page.evaluate("""() => {
            // 找所有包含直播间信息的元素
            const items = document.querySelectorAll('[class*="card"], [class*="item"], [class*="live"], [class*="room"]');
            const results = [];
            items.forEach(el => {
                const text = el.innerText?.substring(0, 200) || '';
                const links = el.querySelectorAll('a[href*="live.douyin.com"]');
                if (links.length > 0) {
                    results.push({
                        text: text.substring(0, 100),
                        href: links[0].href
                    });
                }
            });
            return results;
        }""")
        
        for card in cards_info:
            if any(kw in card['text'] for kw in ['助农', '三农', '农业', '农产品', '水果', '蜂蜜', '茶叶', '土特产', '果园']):
                print(f"  🟢 助农卡片: {card['text'][:60]} -> {card['href']}")
                m = re.search(r'live\.douyin\.com/(\d+)', card['href'])
                if m:
                    url = f"https://live.douyin.com/{m.group(1)}"
                    if url not in live_urls:
                        live_urls.append(url)
        
        # 提取首页所有直播间
        extract_live_ids(page, live_urls)
        
        print(f"\n总计找到 {len(live_urls)} 个候选直播间")
        
        # ===== 验证直播间 =====
        verified_urls = []
        for url in live_urls[:15]:
            try:
                print(f"\n[验证] {url}")
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                time.sleep(5)
                close_popups(page)
                
                title = page.title()
                result = page.evaluate("""() => {
                    const text = document.body?.innerText?.substring(0, 3000) || '';
                    const hasLive = ['直播间', '聊天', '发言', '点赞', '关注', '分享', '购物车', '主播'].some(k => text.includes(k));
                    const isError = ['服务器开小差', '页面不存在', '直播已结束'].some(k => text.includes(k));
                    const isZhunong = ['助农', '三农', '农产品', '农村', '果园', '蜂蜜', '茶叶', '土特产', '水果', '蔬菜', '乡', '农', '特产'].some(k => text.includes(k));
                    return { hasLive, isError, isZhunong, snippet: text.substring(0, 120) };
                }""")
                
                if result["hasLive"] and not result["isError"]:
                    tag = "🟢助农" if result["isZhunong"] else "🔵普通"
                    verified_urls.append({
                        "url": url, 
                        "title": title,
                        "is_zhunong": result["isZhunong"]
                    })
                    print(f"  ✅ {tag}在线: {title}")
                else:
                    print(f"  ❌ 离线: {result['snippet'][:60]}")
            except Exception as e:
                print(f"  ❌ 访问失败: {str(e)[:60]}")
        
        browser.close()
        
        # 输出
        print("\n" + "="*60)
        if verified_urls:
            zhunong = [v for v in verified_urls if v["is_zhunong"]]
            others = [v for v in verified_urls if not v["is_zhunong"]]
            
            if zhunong:
                print("🟢 助农直播间:")
                for i, item in enumerate(zhunong):
                    print(f"  {i+1}. {item['url']} - {item['title']}")
            if others:
                print("🔵 其他在线直播间:")
                for i, item in enumerate(others):
                    print(f"  {i+1}. {item['url']} - {item['title']}")
            
            with open("data/live_rooms.json", "w", encoding="utf-8") as f:
                json.dump(verified_urls, f, ensure_ascii=False, indent=2)
            
            best = zhunong[0] if zhunong else others[0]
            print(f"\n🎯 推荐使用: {best['url']} ({best['title']})")
        else:
            print("❌ 未找到在线直播间")
        
        return verified_urls


def close_popups(page):
    try:
        page.evaluate("""() => {
            document.querySelectorAll('[class*="close"], [class*="Close"], [class*="modal-close"]').forEach(el => {
                try { el.click(); } catch(e) {}
            });
            document.querySelectorAll('[class*="overlay"], [class*="mask"]').forEach(el => {
                try { el.style.display = 'none'; } catch(e) {}
            });
        }""")
    except:
        pass


def extract_live_ids(page, live_urls):
    content = page.content()
    for rid in re.findall(r'live\.douyin\.com/(\d{6,20})', content):
        url = f"https://live.douyin.com/{rid}"
        if url not in live_urls:
            live_urls.append(url)
            print(f"  发现直播间: {rid}")
    try:
        for link in page.query_selector_all('a[href*="live.douyin.com"]'):
            href = link.get_attribute("href") or ""
            m = re.search(r'live\.douyin\.com/(\d{6,20})', href)
            if m:
                url = f"https://live.douyin.com/{m.group(1)}"
                if url not in live_urls:
                    live_urls.append(url)
                    print(f"  链接发现: {m.group(1)}")
    except:
        pass


if __name__ == "__main__":
    os.makedirs("screenshots", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    find_zhunong_lives()
