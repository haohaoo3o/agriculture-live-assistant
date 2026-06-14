"""
全局配置 — 面向三农场景的直播电商AI辅助平台

配置加载优先级（从高到低）：
1. 环境变量（DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, MODEL_NAME 等）
2. .env 文件（项目根目录）
3. 本文件中的默认值（仅非敏感配置）

API Key 配置方式详见 README.md
"""
import os
import sys

# ===== 自动检测项目路径 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)


def _load_env_file():
    """从项目根目录的 .env 文件加载环境变量（如存在）"""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value


_load_env_file()


def _env(key: str, default: str = "") -> str:
    """获取环境变量，带默认值"""
    return os.environ.get(key, default)


# ============================================================
# AI 模型配置 — 支持多种大模型接入
# ============================================================

# 模型名称（可通过 MODEL_NAME 环境变量覆盖）
MODEL_NAME = _env("MODEL_NAME", "qwen3.5-omni-plus")

# API Key — 必须通过环境变量或 .env 文件设置
# 不同提供商的 Key 设置方式：
#   阿里云百炼:   export DASHSCOPE_API_KEY="sk-xxx"
#   OpenAI:       export OPENAI_API_KEY="sk-xxx"
#   其他兼容接口:  export LLM_API_KEY="xxx"
DASHSCOPE_API_KEY = _env("DASHSCOPE_API_KEY", "")
OPENAI_API_KEY = _env("OPENAI_API_KEY", "")
LLM_API_KEY = _env("LLM_API_KEY", "")

# Base URL — 支持自定义API端点
#   阿里云百炼默认:  https://dashscope.aliyuncs.com/compatible-mode/v1
#   OpenAI默认:      https://api.openai.com/v1
#   其他代理/私有部署: 自定义
DASHSCOPE_BASE_URL = _env(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 获取当前有效的 API Key 和 Base URL
def get_api_key() -> str:
    """按优先级返回可用的 API Key"""
    for key in [DASHSCOPE_API_KEY, OPENAI_API_KEY, LLM_API_KEY]:
        if key:
            return key
    return ""


def get_base_url() -> str:
    """返回对应的 Base URL"""
    if DASHSCOPE_API_KEY:
        return DASHSCOPE_BASE_URL
    if OPENAI_API_KEY:
        return _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    if LLM_API_KEY:
        return _env("LLM_BASE_URL", "https://api.openai.com/v1")
    return DASHSCOPE_BASE_URL


# AI调用最大重试次数
MAX_AI_RETRIES = int(_env("MAX_AI_RETRIES", "2"))

# ============================================================
# 服务配置
# ============================================================
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8000"))
DEBUG = _env("DEBUG", "true").lower() in ("1", "true", "yes")

# ============================================================
# 路径配置
# ============================================================
SCREENSHOT_DIR = os.path.join(PROJECT_ROOT, "screenshots")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

# 确保必要目录存在
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
# 截图配置
# ============================================================
SCREENSHOT_INTERVAL = int(_env("SCREENSHOT_INTERVAL", "5"))  # 截图间隔（秒）
SCREENSHOT_QUALITY = int(_env("SCREENSHOT_QUALITY", "85"))   # JPEG压缩质量
MAX_SCREENSHOTS = int(_env("MAX_SCREENSHOTS", "200"))        # 最大保留截图数

# ============================================================
# 直播间配置
# ============================================================
DOUYIN_LIVE_URL = "https://live.douyin.com"
POPUP_CHECK_INTERVAL = int(_env("POPUP_CHECK_INTERVAL", "10"))
AUTO_ANALYSIS_INTERVAL = int(_env("AUTO_ANALYSIS_INTERVAL", "30"))
