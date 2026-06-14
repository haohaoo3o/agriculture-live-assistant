"""综合测试脚本 - 测试所有核心功能"""
import asyncio
import sys
import os
import time

# 修复Windows终端编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Python 3.14+ 默认使用ProactorEventLoop，Playwright需要它来创建子进程
# 不再设置 WindowsSelectorEventLoopPolicy


async def test_all():
    from services.browser_service import browser_service
    from services.ai_service import ai_service
    from services.data_service import data_service

    results = []

    def record(name, ok, detail=""):
        status = "[OK]" if ok else "[FAIL]"
        results.append((name, ok))
        print(f"  {status} {name}" + (f" - {detail}" if detail else ""))

    # 1. 浏览器启动
    print("\n[1/12] 浏览器启动...")
    try:
        await browser_service.start(headless=False)
        record("浏览器启动", True)
    except Exception as e:
        record("浏览器启动", False, str(e))
        return

    # 2. 连接直播间
    print("\n[2/12] 连接直播间...")
    try:
        result = await browser_service.navigate_to_live('https://live.douyin.com/338473718519')
        record("直播间连接", result["success"], result.get("message", ""))
    except Exception as e:
        record("直播间连接", False, str(e))

    # 等待页面加载
    await asyncio.sleep(5)

    # 3. 截图
    print("\n[3/12] 截图功能...")
    try:
        filepath = await browser_service.take_screenshot()
        record("截图功能", filepath is not None, filepath or "失败")
    except Exception as e:
        record("截图功能", False, str(e))
        filepath = None

    # 4. 获取直播间信息
    print("\n[4/12] 获取直播间信息...")
    try:
        info = await browser_service.get_live_info()
        record("直播间信息", bool(info), str(info)[:80])
    except Exception as e:
        record("直播间信息", False, str(e))

    # 5. AI画面分析
    print("\n[5/12] AI画面分析...")
    if filepath:
        try:
            analysis = ai_service.analyze_live_screenshot(filepath, "测试上下文")
            record("AI画面分析", bool(analysis), list(analysis.keys())[:3].__str__())
        except Exception as e:
            record("AI画面分析", False, str(e))
    else:
        record("AI画面分析", False, "无截图")

    # 6. 商品识别
    print("\n[6/12] 商品识别...")
    if filepath:
        try:
            product = ai_service.recognize_product(filepath)
            record("商品识别", bool(product), product.get("product_name", "未知"))
        except Exception as e:
            record("商品识别", False, str(e))
    else:
        record("商品识别", False, "无截图")

    # 7. 合规检测
    print("\n[7/12] 合规检测...")
    try:
        compliance = ai_service.check_compliance("这是我们最好的苹果，100%有机，绝对包治百病")
        record("合规检测", bool(compliance), f"风险等级: {compliance.get('risk_level', '未知')}")
    except Exception as e:
        record("合规检测", False, str(e))

    # 8. 评论分析
    print("\n[8/12] 评论分析...")
    try:
        test_comments = [
            {"user": "小明", "content": "这个苹果多少钱一斤？", "time": "12:00"},
            {"user": "小红", "content": "看起来很好吃！", "time": "12:01"},
            {"user": "老王", "content": "包邮吗？", "time": "12:02"},
        ]
        analysis = ai_service.analyze_comments(test_comments)
        record("评论分析", bool(analysis), f"情绪: {analysis.get('sentiment_analysis', {}).get('overall_sentiment', '未知')}")
    except Exception as e:
        record("评论分析", False, str(e))

    # 9. 直播建议
    print("\n[9/12] 直播建议...")
    try:
        suggestions = ai_service.generate_live_suggestions({
            "duration": "01:30:00",
            "viewer_count": "500",
            "comment_count": "30",
        })
        record("直播建议", bool(suggestions), f"内容建议数: {len(suggestions.get('content_suggestions', []))}")
    except Exception as e:
        record("直播建议", False, str(e))

    # 10. 评论回复建议（新功能）
    print("\n[10/12] 评论回复建议...")
    try:
        replies = ai_service.generate_comment_reply("这个苹果多少钱一斤？发货到北京吗？", "直播间卖苹果")
        record("评论回复建议", bool(replies) and len(replies) >= 2, f"建议数: {len(replies)}")
    except Exception as e:
        record("评论回复建议", False, str(e))

    # 11. 弹窗检测
    print("\n[11/12] 弹窗检测与关闭...")
    try:
        popup_result = await browser_service.detect_and_close_popup()
        record("弹窗检测", True, f"关闭: {popup_result.get('count', 0)}个")
    except Exception as e:
        record("弹窗检测", False, str(e))

    # 12. 数据记录
    print("\n[12/12] 数据记录...")
    try:
        session_id = data_service.start_session("https://live.douyin.com/test")
        summary = data_service.get_session_summary()
        record("数据记录", bool(summary), f"会话ID: {session_id[:8]}...")
    except Exception as e:
        record("数据记录", False, str(e))

    # 关闭浏览器
    await browser_service.stop()

    # 统计结果
    print("\n" + "=" * 50)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"  测试结果: {passed}/{total} 通过")
    if passed == total:
        print("  >>> 全部测试通过! <<<")
    else:
        failed = [name for name, ok in results if not ok]
        print(f"  失败项: {', '.join(failed)}")
    print("=" * 50)


asyncio.run(test_all())
