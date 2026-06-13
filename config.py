"""集中讀取環境設定（API 金鑰、Sheet ID、模型選擇）。"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- API 金鑰 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")   # 可空，但建議申請（速率 3→10 req/s）
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "")       # E-utilities 禮貌性標示

# --- Google Sheet ---
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
SHEET_ID = os.environ.get("SHEET_ID", "")

# --- 模型 routing（預設全 lite，摘要可升級）---
# 可用 .env 的 LITE_MODEL / SUMMARY_MODEL 覆寫；摘要品質若不夠改成 gemini-3.5-flash。
LITE_MODEL = os.environ.get("LITE_MODEL", "gemini-3.1-flash-lite")
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "gemini-3.1-flash-lite")
