"""
数据记录与分析服务
负责直播数据的持久化存储、统计分析和经营画像生成
"""
import json
import os
import time
from datetime import datetime
from typing import Optional

from config import DATA_DIR


class DataService:
    """数据记录与分析服务"""

    def __init__(self):
        self.session_data = {
            "session_id": "",
            "start_time": "",
            "end_time": "",
            "live_url": "",
            "duration_seconds": 0,
            "screenshot_analyses": [],
            "product_detections": [],
            "compliance_checks": [],
            "comment_analyses": [],
            "live_suggestions": [],
            "viewer_count_history": [],
            "summary": {},
        }
        self.data_file = os.path.join(DATA_DIR, "session_data.json")
        self._dirty = False  # 脏标记，标记是否有未保存的数据
        self._last_save_time = 0  # 上次保存时间

    def start_session(self, live_url: str):
        """开始新的直播会话记录"""
        self.session_data = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": "",
            "live_url": live_url,
            "duration_seconds": 0,
            "screenshot_analyses": [],
            "product_detections": [],
            "compliance_checks": [],
            "comment_analyses": [],
            "live_suggestions": [],
            "viewer_count_history": [],
            "summary": {},
        }
        self._save_session()
        return self.session_data["session_id"]

    def end_session(self):
        """结束直播会话"""
        self.session_data["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start = datetime.strptime(self.session_data["start_time"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(self.session_data["end_time"], "%Y-%m-%d %H:%M:%S")
        self.session_data["duration_seconds"] = int((end - start).total_seconds())
        self._generate_summary()
        self._save_session()

    def record_screenshot_analysis(self, analysis: dict):
        """记录截图分析结果"""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "analysis": analysis,
        }
        self.session_data["screenshot_analyses"].append(entry)
        self._save_session()

    def record_product_detection(self, product: dict):
        """记录商品识别结果"""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "product": product,
        }
        self.session_data["product_detections"].append(entry)
        self._save_session()

    def record_compliance_check(self, result: dict):
        """记录合规检查结果"""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "result": result,
        }
        self.session_data["compliance_checks"].append(entry)
        self._save_session()

    def record_comment_analysis(self, analysis: dict):
        """记录评论分析结果"""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "analysis": analysis,
        }
        self.session_data["comment_analyses"].append(entry)
        self._save_session()

    def record_live_suggestion(self, suggestion: dict):
        """记录直播建议"""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "suggestion": suggestion,
        }
        self.session_data["live_suggestions"].append(entry)
        self._save_session()

    def record_viewer_count(self, count: str):
        """记录观众人数变化"""
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count": count,
        }
        self.session_data["viewer_count_history"].append(entry)

    def _generate_summary(self):
        """生成直播会话总结"""
        data = self.session_data
        self.session_data["summary"] = {
            "total_screenshots_analyzed": len(data["screenshot_analyses"]),
            "total_products_detected": len(data["product_detections"]),
            "total_compliance_checks": len(data["compliance_checks"]),
            "total_comment_analyses": len(data["comment_analyses"]),
            "total_suggestions": len(data["live_suggestions"]),
            "compliance_risk_summary": self._summarize_compliance(),
            "product_summary": self._summarize_products(),
            "key_improvements": self._extract_key_improvements(),
        }

    def _summarize_compliance(self) -> dict:
        """合规风险汇总"""
        checks = self.session_data["compliance_checks"]
        high_risk = sum(1 for c in checks if c.get("result", {}).get("risk_level") == "high")
        medium_risk = sum(1 for c in checks if c.get("result", {}).get("risk_level") == "medium")
        low_risk = sum(1 for c in checks if c.get("result", {}).get("risk_level") == "low")
        return {
            "total_checks": len(checks),
            "high_risk_count": high_risk,
            "medium_risk_count": medium_risk,
            "low_risk_count": low_risk,
            "overall_risk": "high" if high_risk > 0 else ("medium" if medium_risk > 0 else "low"),
        }

    def _summarize_products(self) -> list:
        """商品识别汇总"""
        products = []
        seen = set()
        for p in self.session_data["product_detections"]:
            name = p.get("product", {}).get("product_name", "未知")
            if name not in seen and name != "未检测到农产品" and name != "识别失败":
                products.append(p.get("product", {}))
                seen.add(name)
        return products

    def _extract_key_improvements(self) -> list:
        """提取关键改进建议"""
        improvements = []
        for a in self.session_data["screenshot_analyses"][-5:]:
            suggestions = a.get("analysis", {}).get("improvement_suggestions", [])
            improvements.extend(suggestions)
        # 去重并保留最近的建议
        seen = set()
        unique = []
        for imp in reversed(improvements):
            if imp not in seen:
                unique.append(imp)
                seen.add(imp)
        return unique[:10]

    def _save_session(self):
        """标记数据为脏，延迟保存（避免每次记录都写文件阻塞）"""
        self._dirty = True
    
    def _flush_if_dirty(self):
        """如果有脏数据则写入文件，由定时任务调用"""
        if not self._dirty:
            return
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.session_data, f, ensure_ascii=False, indent=2)
            self._dirty = False
            self._last_save_time = time.time()
        except Exception as e:
            print(f"[数据服务] 保存失败: {e}")
    
    def force_save(self):
        """强制立即保存"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.session_data, f, ensure_ascii=False, indent=2)
            self._dirty = False
            self._last_save_time = time.time()
        except Exception as e:
            print(f"[数据服务] 强制保存失败: {e}")

    def load_session(self) -> dict:
        """加载上次会话数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return self.session_data

    def get_session_summary(self) -> dict:
        """获取当前会话摘要"""
        return {
            "session_id": self.session_data.get("session_id", ""),
            "start_time": self.session_data.get("start_time", ""),
            "duration_seconds": self.session_data.get("duration_seconds", 0),
            "stats": {
                "screenshots_analyzed": len(self.session_data.get("screenshot_analyses", [])),
                "products_detected": len(self.session_data.get("product_detections", [])),
                "compliance_checks": len(self.session_data.get("compliance_checks", [])),
                "comment_analyses": len(self.session_data.get("comment_analyses", [])),
                "suggestions_generated": len(self.session_data.get("live_suggestions", [])),
            },
            "summary": self.session_data.get("summary", {}),
        }

    def generate_business_profile(self) -> dict:
        """
        生成农户经营画像
        用于向机构展示农户的直播经营能力
        """
        data = self.session_data
        products = self._summarize_products()
        compliance = self._summarize_compliance()

        return {
            "profile_type": "农户直播经营画像",
            "session_id": data.get("session_id", ""),
            "live_url": data.get("live_url", ""),
            "duration": data.get("duration_seconds", 0),
            "products_showcased": products,
            "compliance_record": compliance,
            "analysis_frequency": len(data.get("screenshot_analyses", [])),
            "engagement_indicators": {
                "comment_analysis_count": len(data.get("comment_analyses", [])),
                "viewer_count_records": len(data.get("viewer_count_history", [])),
            },
            "key_improvements": self._extract_key_improvements(),
            "overall_assessment": self._generate_overall_assessment(),
        }

    def _generate_overall_assessment(self) -> str:
        """生成总体评估"""
        data = self.session_data
        compliance = self._summarize_compliance()

        if compliance["overall_risk"] == "high":
            return "合规风险较高，需要重点关注直播用语的规范性"
        elif compliance["overall_risk"] == "medium":
            return "合规状况一般，建议持续关注直播内容规范性"
        else:
            return "合规状况良好，直播行为较为规范"


# 全局数据服务实例
data_service = DataService()
