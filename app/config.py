"""專案路徑與環境設定；不輸出金鑰。"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{ROOT / "storage/readings.sqlite"}')
CORS_ORIGINS = [item.strip() for item in os.getenv('CORS_ORIGINS', '').split(',') if item.strip()]
