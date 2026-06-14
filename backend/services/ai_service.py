"""
AI多模态分析服务 - 支持多种大模型接入（阿里云百炼/OpenAI/其他兼容接口）
支持图片+文本输入，提供直播分析、商品识别、合规检测等功能
"""
import base64
import json
import os
import time
from typing import Optional
from openai import OpenAI

from config import get_api_key, get_base_url, MODEL_NAME


class AIService:
    """AI服务封装类 - 统一管理所有大模型调用"""

    def __init__(self):
        api_key = get_api_key()
        base_url = get_base_url()

        if not api_key:
            print("[AI服务] 警告：未设置API Key，AI功能将不可用")
            print("[AI服务] 请设置环境变量: DASHSCOPE_API_KEY / OPENAI_API_KEY / LLM_API_KEY")

        self.client = OpenAI(
            api_key=api_key or "sk-placeholder",
            base_url=base_url,
            timeout=120.0,
            max_retries=1,
        )
        self.model = MODEL_NAME
        # 分析历史记录
        self.analysis_history = []
        # 合规词库
        self.compliance_keywords = self._load_compliance_keywords()

    def _load_compliance_keywords(self) -> list:
        """加载合规敏感词库"""
        return [
            # 广告法违禁词
            "最便宜", "最好", "最佳", "最优", "第一", "顶级", "极品", "绝无仅有",
            "万能", "100%", "绝对", "永远", "无与伦比", "独一无二",
            # 食品安全相关
            "治疗", "治愈", "药效", "处方", "包治", "根除", "疗效",
            # 价格违规
            "仅此一天", "最后机会", "错过再无", "限时秒杀",
        ]

    def _encode_image(self, image_path: str) -> str:
        """将本地图片编码为base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _parse_json_result(self, result: str, fallback: dict = None) -> dict:
        """统一JSON解析，从AI返回文本中提取JSON"""
        try:
            if "```json" in result:
                json_str = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                json_str = result.split("```")[1].split("```")[0].strip()
            elif "{" in result and "}" in result:
                start = result.index("{")
                end = result.rindex("}") + 1
                json_str = result[start:end]
            else:
                json_str = result
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return fallback or {"raw": result}

    def _call_model_with_retry(
        self,
        text_prompt: str,
        image_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
    ) -> str:
        """
        调用qwen3.5-omni-plus模型（带重试机制）
        支持纯文本和图片+文本两种模式
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return self._call_model(text_prompt, image_path, system_prompt)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"[AI] 调用失败，{wait}秒后重试(第{attempt+1}次): {e}")
                    time.sleep(wait)
        return f"AI调用失败(已重试{max_retries}次): {str(last_error)}"

    def _call_model(
        self,
        text_prompt: str,
        image_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        调用qwen3.5-omni-plus模型
        支持纯文本和图片+文本两种模式
        """
        content = []

        # 添加图片输入
        if image_path and os.path.exists(image_path):
            base64_image = self._encode_image(image_path)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                },
            })

        # 添加文本输入
        content.append({"type": "text", "text": text_prompt})

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            modalities=["text"],
            stream=True,
            stream_options={"include_usage": True},
        )

        result_text = ""
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                result_text += chunk.choices[0].delta.content

        return result_text.strip() if result_text else "分析完成，但未获取到文本结果"

    def _call_text_only(
        self,
        text_prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
    ) -> str:
        """纯文本模式调用模型（带重试机制）"""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": text_prompt})

                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    modalities=["text"],
                    stream=True,
                    stream_options={"include_usage": True},
                )

                result_text = ""
                for chunk in completion:
                    if chunk.choices and chunk.choices[0].delta.content:
                        result_text += chunk.choices[0].delta.content

                return result_text.strip() if result_text else "分析完成"
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = 2 ** attempt
                    print(f"[AI] 文本调用失败，{wait}秒后重试(第{attempt+1}次): {e}")
                    time.sleep(wait)
        return f"AI调用失败(已重试{max_retries}次): {str(last_error)}"

    def analyze_live_screenshot(self, image_path: str, context: str = "") -> dict:
        """
        分析直播截图 - 核心功能
        返回直播内容描述、商品信息、主播表现等分析结果
        """
        prompt = f"""你是一个专业的直播电商分析助手，专门面向三农直播场景。请仔细分析这张直播截图，从以下维度给出详细分析：

1. **直播场景分析**：描述当前直播间的场景布置、背景环境、光线条件等
2. **主播状态**：主播的着装、表情、动作姿态、专业度等
3. **商品展示**：识别画面中的农产品，描述其外观特征、展示方式、包装情况
4. **画面质量**：画面清晰度、构图合理性、视觉吸引力等
5. **互动元素**：画面中是否有价格标签、促销信息、字幕等互动元素
6. **改进建议**：针对当前画面给出3条具体可操作的优化建议

{"额外上下文信息：" + context if context else ""}

请用JSON格式返回结果，字段如下：
{{
    "scene_analysis": "场景分析内容",
    "anchor_status": "主播状态描述",
    "product_display": "商品展示分析",
    "visual_quality": "画面质量评价",
    "interaction_elements": "互动元素识别",
    "improvement_suggestions": ["建议1", "建议2", "建议3"]
}}"""

        system_prompt = "你是面向三农直播电商的专业AI分析助手，擅长从直播画面中提取有价值的信息并给出实用建议。请始终用中文回答。"

        result = self._call_model_with_retry(prompt, image_path, system_prompt)

        parsed = self._parse_json_result(result, {
            "scene_analysis": result[:200] if len(result) > 200 else result,
            "anchor_status": "解析中...",
            "product_display": "解析中...",
            "visual_quality": "解析中...",
            "interaction_elements": "解析中...",
            "improvement_suggestions": ["暂无建议"],
            "raw_response": result,
        })

        # 记录分析历史
        self.analysis_history.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "screenshot_analysis",
            "image": image_path,
            "result": parsed,
        })

        return parsed

    def detect_popup(self, image_path: str) -> dict:
        """
        检测直播间是否有弹窗需要关闭
        返回弹窗检测结果和关闭建议
        """
        prompt = """请分析这张直播网页截图，判断是否存在以下类型的弹窗或遮挡元素：

1. 登录/注册弹窗
2. 下载APP提示弹窗
3. 关注/订阅弹窗
4. 广告弹窗
5. 系统通知弹窗
6. 其他遮挡直播内容的弹窗

请用JSON格式返回：
{
    "has_popup": true/false,
    "popup_type": "弹窗类型描述（如无弹窗则为none）",
    "popup_description": "弹窗内容描述",
    "close_button_position": "关闭按钮的大致位置描述（如右上角/底部等）",
    "urgency": "high/medium/low"
}"""

        result = self._call_model_with_retry(prompt, image_path, "你是网页弹窗检测专家。请准确判断弹窗位置和类型。用中文回答。")
        return self._parse_json_result(result, {
            "has_popup": False, "popup_type": "unknown",
            "popup_description": result[:100], "close_button_position": "unknown", "urgency": "low"
        })

    def recognize_product(self, image_path: str) -> dict:
        """
        商品识别与信息提取
        识别直播中展示的农产品，返回商品信息
        """
        prompt = """你是农产品识别专家。请仔细分析这张直播截图中的农产品，尽可能识别以下信息：

请用JSON格式返回：
{
    "product_name": "产品名称",
    "category": "农产品分类（如水果/蔬菜/粮食/茶叶/中药材/畜牧/水产等）",
    "appearance": "外观描述（颜色、大小、新鲜度等）",
    "origin_guess": "可能的产地推测",
    "selling_points": ["卖点1", "卖点2", "卖点3"],
    "price_range_guess": "预估价格范围",
    "storage_advice": "储存建议",
    "compliance_info": {
        "required_labels": ["需要标注的信息如生产日期等"],
        "food_safety_notes": "食品安全注意事项"
    }
}

如画面中没有农产品，请返回 product_name 为 "未检测到农产品"。"""

        result = self._call_model_with_retry(prompt, image_path, "你是专业的农产品识别与信息分析专家。用中文回答。")
        return self._parse_json_result(result, {
            "product_name": "识别失败", "category": "未知", "appearance": result[:150],
            "origin_guess": "未知", "selling_points": [], "price_range_guess": "未知",
            "storage_advice": "", "compliance_info": {"required_labels": [], "food_safety_notes": ""},
        })

    def generate_live_suggestions(self, context: dict) -> dict:
        """
        生成直播建议
        基于当前直播状态和历史数据，给出实时直播建议
        """
        prompt = f"""你是一个面向三农直播的专业顾问，请根据以下直播数据给出实时建议：

当前直播状态：
- 直播时长: {context.get('duration', '未知')}
- 观众人数: {context.get('viewer_count', '未知')}
- 评论数量: {context.get('comment_count', '未知')}
- 当前商品: {context.get('current_product', '未知')}
- 最近截图分析: {context.get('last_analysis', '无')}

请给出以下建议，用JSON格式返回：
{{
    "content_suggestions": [
        "直播内容建议1（如：接下来可以展示产品的XX特点）",
        "直播内容建议2",
        "直播内容建议3"
    ],
    "interaction_tips": [
        "互动技巧1（如：可以和观众聊聊XX话题）",
        "互动技巧2",
        "互动技巧3"
    ],
    "sales_techniques": [
        "销售技巧1（如：可以推出XX优惠组合）",
        "销售技巧2",
        "销售技巧3"
    ],
    "timing_advice": "当前时间段的直播节奏建议",
    "energy_level": "high/medium/low - 建议的直播状态"
}}"""

        result = self._call_text_only(
            prompt, "你是三农直播顾问，擅长给出实用、接地气的直播建议。请用中文回答，建议要具体可操作。")
        return self._parse_json_result(result, {
            "content_suggestions": [result[:200]], "interaction_tips": ["与观众积极互动"],
            "sales_techniques": ["突出产品特色"], "timing_advice": "保持当前节奏", "energy_level": "medium",
        })

    def check_compliance(self, text: str) -> dict:
        """
        合规与风险检测（纯文本版）
        检查直播用语、商品描述等是否合规
        """
        # 先做本地关键词匹配
        found_keywords = []
        for kw in self.compliance_keywords:
            if kw in text:
                found_keywords.append(kw)

        prompt = f"""你是直播电商合规审核专家。请检查以下直播相关文本是否存在合规风险：

待审核文本：
{text}

请检查以下维度：
1. 是否违反《广告法》（虚假宣传、绝对化用语等）
2. 是否违反《食品安全法》（食品功效宣传等）
3. 是否存在价格欺诈风险
4. 是否有不当承诺
5. 是否缺少必要信息披露

请用JSON格式返回：
{{
    "risk_level": "high/medium/low/safe",
    "violations": [
        {{"type": "违规类型", "content": "具体内容", "suggestion": "修改建议"}}
    ],
    "local_keywords_matched": {found_keywords},
    "overall_assessment": "整体合规评估",
    "recommendations": ["改进建议1", "改进建议2"]
}}"""

        result = self._call_text_only(
            prompt, "你是专业的直播电商合规审核员，熟悉中国广告法、食品安全法等法规。用中文回答。")
        parsed = self._parse_json_result(result, {
            "risk_level": "unknown", "violations": [], "overall_assessment": result[:200], "recommendations": [],
        })
        parsed["local_keywords_matched"] = found_keywords
        return parsed

    def check_compliance_from_screenshot(self, image_path: str, text_context: str = "") -> dict:
        """
        基于直播截图的自动合规检测（多模态）
        直接分析截图中的文字、标签、价格、宣传语等，无需人工输入
        """
        # 先做本地关键词匹配（如果有文本上下文）
        found_keywords = []
        if text_context:
            for kw in self.compliance_keywords:
                if kw in text_context:
                    found_keywords.append(kw)

        prompt = f"""你是直播电商合规审核专家，专门面向三农直播场景。请仔细检查这张直播截图，识别画面中所有可能存在合规风险的内容。

请重点检查：
1. 画面中的文字（标题、字幕、价格标签、促销信息、商品名称等）是否违反《广告法》（如"最好""最强""第一"等绝对化用语）
2. 画面中的食品宣传是否违反《食品安全法》（如暗示治疗功效、虚假宣传等）
3. 价格标注是否存在欺诈风险（如虚假原价、误导性折扣等）
4. 商品标签是否缺少必要信息（如生产日期、产地、许可证号等）
5. 画面中是否有不当承诺或夸大宣传

{"额外文本上下文（来自直播评论等）：" + text_context if text_context else ""}

请用JSON格式返回：
{{
    "risk_level": "high/medium/low/safe",
    "violations": [
        {{"type": "违规类型", "content": "画面中看到的具体违规内容", "suggestion": "修改建议"}}
    ],
    "detected_text": "画面中识别到的所有文字内容",
    "local_keywords_matched": {found_keywords},
    "overall_assessment": "整体合规评估",
    "recommendations": ["改进建议1", "改进建议2"]
}}

如果画面中没有发现合规风险，risk_level应为"safe"，violations为空数组。"""

        result = self._call_model_with_retry(
            prompt, image_path,
            "你是专业的直播电商合规审核员，熟悉中国广告法、食品安全法等法规，特别擅长识别直播画面中的违规内容。用中文回答。")
        parsed = self._parse_json_result(result, {
            "risk_level": "unknown", "violations": [], "detected_text": "",
            "overall_assessment": result[:200], "recommendations": [],
        })
        parsed["local_keywords_matched"] = found_keywords
        return parsed

    def analyze_comments(self, comments: list) -> dict:
        """
        分析直播间评论
        提取观众情绪、热门问题、购买意向等信息
        """
        if not comments:
            return {
                "total_count": 0,
                "sentiment": "无评论",
                "hot_topics": [],
                "purchase_intentions": [],
                "suggestions": [],
            }

        comments_text = "\n".join(
            [f"- [{c.get('time', '')}] {c.get('user', '匿名')}: {c.get('content', '')}"
             for c in comments[-50:]]  # 只分析最近50条
        )

        prompt = f"""请分析以下直播间评论数据，提取关键信息：

评论列表：
{comments_text}

请用JSON格式返回：
{{
    "total_count": {len(comments)},
    "sentiment_analysis": {{
        "positive_ratio": "积极评论占比",
        "negative_ratio": "消极评论占比",
        "neutral_ratio": "中性评论占比",
        "overall_sentiment": "整体情绪倾向描述"
    }},
    "hot_topics": [
        {{"topic": "话题", "count": "出现次数", "sentiment": "情绪倾向"}}
    ],
    "purchase_intentions": ["购买意向表达1", "购买意向表达2"],
    "common_questions": ["常见问题1", "常见问题2"],
    "key_user_feedback": "核心用户反馈总结",
    "actionable_suggestions": ["基于评论的直播调整建议1", "建议2"]
}}"""

        result = self._call_text_only(
            prompt, "你是直播数据分析专家，擅长从评论中提取有价值的信息。用中文回答。")
        return self._parse_json_result(result, {
            "total_count": len(comments), "sentiment_analysis": {"overall_sentiment": result[:200]},
            "hot_topics": [], "purchase_intentions": [], "common_questions": [],
            "key_user_feedback": "", "actionable_suggestions": [],
        })

    def generate_comment_reply(self, comment: str, context: str = "") -> list:
        """
        生成评论回复建议
        针对直播间观众的评论，生成3条适合主播回复的建议
        """
        prompt = f"""你是三农直播间的互动助手。观众在直播间发了以下评论，请为主播生成3条合适的回复建议。

观众评论：{comment}
{"相关上下文：" + context if context else ""}

要求：
1. 回复要亲切自然，符合三农直播的接地气风格
2. 回复要能引导观众互动、促进转化
3. 一条简短有力（10字以内，适合快速念出）
4. 一条详细解释型（适合详细介绍产品）
5. 一条互动引导型（引导观众关注、下单、分享）

请用JSON格式返回：
{{
    "replies": [
        {{"type": "简短有力", "text": "回复内容", "tip": "使用场景提示"}},
        {{"type": "详细解释", "text": "回复内容", "tip": "使用场景提示"}},
        {{"type": "互动引导", "text": "回复内容", "tip": "使用场景提示"}}
    ],
    "comment_sentiment": "positive/neutral/negative/question",
    "reply_priority": "high/medium/low"
}}"""

        result = self._call_text_only(
            prompt, "你是面向农户的直播互动顾问，擅长用接地气的语言和观众互动。回复要自然、真诚、有感染力。用中文回答。")
        parsed = self._parse_json_result(result, {
            "replies": [
                {"type": "简短有力", "text": "感谢支持！", "tip": "通用回复"},
                {"type": "详细解释", "text": result[:100] if result else "欢迎！", "tip": "AI回复"},
                {"type": "互动引导", "text": "关注不迷路！", "tip": "通用回复"},
            ],
            "comment_sentiment": "neutral", "reply_priority": "medium",
        })
        return parsed.get("replies", parsed.get("replies", [
            {"type": "简短有力", "text": "感谢支持！", "tip": "通用回复"},
            {"type": "详细解释", "text": result[:100], "tip": "AI回复"},
            {"type": "互动引导", "text": "关注不迷路！", "tip": "通用回复"},
        ]))

    def generate_content_framework(self, product_info: dict) -> dict:
        """
        直播内容与表达辅助
        根据农产品类型生成直播内容框架
        """
        prompt = f"""你是三农直播内容策划专家。请根据以下农产品信息，为农户生成一份直播内容框架：

产品信息：
{json.dumps(product_info, ensure_ascii=False, indent=2)}

请生成直播内容框架，用JSON格式返回：
{{
    "opening_script": "开场白建议（30秒内）",
    "product_introduction": {{
        "key_points": ["要点1", "要点2", "要点3"],
        "suggested_order": ["先讲XX", "再讲XX", "最后讲XX"],
        "storytelling_angle": "故事化表达角度建议"
    }},
    "selling_points_script": [
        {{"point": "卖点", "script": "推荐话术", "demo_action": "演示动作建议"}}
    ],
    "interaction_design": [
        {{"timing": "时间点", "action": "互动动作", "script": "话术"}}
    ],
    "closing_script": "收尾话术建议",
    "compliance_reminders": ["合规提醒1", "合规提醒2"],
    "taboo_expressions": ["禁用词1", "禁用词2"]
}}"""

        result = self._call_text_only(
            prompt, "你是面向农户的直播内容策划专家，建议要通俗易懂、接地气。用中文回答。")
        return self._parse_json_result(result, {
            "opening_script": "大家好，欢迎来到直播间！",
            "product_introduction": {"key_points": [result[:200]]},
            "selling_points_script": [], "interaction_design": [],
            "closing_script": "", "compliance_reminders": [], "taboo_expressions": [],
        })


# 全局AI服务实例
ai_service = AIService()
