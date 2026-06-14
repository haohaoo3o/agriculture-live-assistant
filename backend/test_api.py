"""全功能综合测试"""
import httpx
import asyncio
import time

async def test():
    base = 'http://localhost:8000/api/live'
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        print("=" * 60)
        print("  全功能综合测试 - 面向三农场景的直播电商AI辅助平台")
        print("=" * 60)
        
        # 1. 状态API
        print("\n[1] 状态查询...")
        r = await client.get(f'{base}/status')
        print(f"  ✅ Status: {r.status_code} - is_running={r.json().get('is_running')}")
        
        # 2. 连接直播间
        print("\n[2] 连接直播间（headless）...")
        r = await client.post(f'{base}/connect', json={'url':'https://live.douyin.com/338473718519','headless':True})
        result = r.json()
        print(f"  {'✅' if result.get('success') else '❌'} Connect: {result.get('message', '')}")
        if not result.get('success'):
            print("  连接失败，终止测试")
            return
        
        await asyncio.sleep(5)
        
        # 3. 截图
        print("\n[3] 截图测试...")
        start = time.time()
        r = await client.post(f'{base}/screenshot', timeout=30.0)
        elapsed = time.time() - start
        sr = r.json()
        print(f"  {'✅' if sr.get('success') else '❌'} Screenshot: elapsed={elapsed:.1f}s")
        
        # 4. AI画面分析
        print("\n[4] AI画面分析...")
        start = time.time()
        r = await client.post(f'{base}/analyze-screenshot', timeout=120.0)
        elapsed = time.time() - start
        ar = r.json()
        print(f"  {'✅' if ar.get('success') else '❌'} Analysis: elapsed={elapsed:.1f}s")
        if ar.get('analysis'):
            a = ar['analysis']
            print(f"    场景: {(a.get('scene_analysis','')[:60])}...")
            print(f"    主播: {(a.get('anchor_status','')[:60])}...")
            print(f"    商品: {(a.get('product_display','')[:60])}...")
        
        # 5. 商品识别
        print("\n[5] 商品识别...")
        start = time.time()
        r = await client.post(f'{base}/detect-product', timeout=120.0)
        elapsed = time.time() - start
        pr = r.json()
        print(f"  {'✅' if pr.get('success') else '❌'} Product: elapsed={elapsed:.1f}s")
        if pr.get('product'):
            p = pr['product']
            print(f"    商品: {p.get('product_name','未知')}")
            print(f"    分类: {p.get('category','未知')}")
        
        # 6. 合规检测
        print("\n[6] 合规检测...")
        start = time.time()
        r = await client.post(f'{base}/check-compliance', json={'text':'这个苹果是最便宜的，绝对100%纯天然，包治百病'}, timeout=120.0)
        elapsed = time.time() - start
        cr = r.json()
        print(f"  {'✅' if cr.get('success') else '❌'} Compliance: elapsed={elapsed:.1f}s")
        if cr.get('result'):
            c = cr['result']
            print(f"    风险等级: {c.get('risk_level','未知')}")
            print(f"    评估: {(c.get('overall_assessment','')[:60])}...")
            if c.get('local_keywords_matched'):
                print(f"    本地匹配: {c['local_keywords_matched']}")
        
        # 7. 直播建议
        print("\n[7] 直播建议...")
        start = time.time()
        r = await client.post(f'{base}/suggestions', json={'context':{}}, timeout=120.0)
        elapsed = time.time() - start
        sg = r.json()
        print(f"  {'✅' if sg.get('success') else '❌'} Suggestions: elapsed={elapsed:.1f}s")
        if sg.get('suggestions'):
            s = sg['suggestions']
            if s.get('content_suggestions'):
                print(f"    内容建议: {s['content_suggestions'][0][:50]}...")
        
        # 8. 评论回复建议
        print("\n[8] 评论回复建议...")
        start = time.time()
        r = await client.post(f'{base}/comment-reply-suggestion', json={'comment':'这个苹果多少钱一斤？包邮吗？','context':'用户:小明'}, timeout=120.0)
        elapsed = time.time() - start
        rr = r.json()
        print(f"  {'✅' if rr.get('success') else '❌'} Reply: elapsed={elapsed:.1f}s")
        if rr.get('reply_suggestions'):
            for reply in rr['reply_suggestions'][:3]:
                print(f"    [{reply.get('type','')}] {reply.get('text','')}")
        
        # 9. 开始监控
        print("\n[9] 开始监控...")
        r = await client.post(f'{base}/start-monitoring')
        mr = r.json()
        print(f"  {'✅' if mr.get('success') else '❌'} Monitoring: {mr.get('message','')}")
        
        # 等待监控采集一些数据
        print("  等待10秒让监控采集数据...")
        await asyncio.sleep(10)
        
        # 10. 获取评论
        print("\n[10] 获取评论...")
        r = await client.get(f'{base}/comments?count=10')
        comments = r.json()
        print(f"  ✅ Comments: total={comments.get('total',0)}")
        
        # 11. 会话摘要
        print("\n[11] 会话摘要...")
        r = await client.get(f'{base}/session-summary')
        summary = r.json()
        stats = summary.get('stats', {})
        print(f"  ✅ Session: screenshots={stats.get('screenshots_analyzed',0)}, products={stats.get('products_detected',0)}")
        
        # 12. 经营画像
        print("\n[12] 经营画像...")
        r = await client.get(f'{base}/business-profile')
        profile = r.json()
        print(f"  ✅ Profile: type={profile.get('profile_type','')}")
        
        # 13. 停止监控
        print("\n[13] 停止监控...")
        r = await client.post(f'{base}/stop-monitoring')
        print(f"  {'✅' if r.json().get('success') else '❌'} Stop monitoring")
        
        # 14. 断开
        print("\n[14] 断开连接...")
        r = await client.post(f'{base}/disconnect')
        print(f"  {'✅' if r.json().get('success') else '❌'} Disconnect")
        
        print("\n" + "=" * 60)
        print("  全功能测试完成！")
        print("=" * 60)

asyncio.run(test())
