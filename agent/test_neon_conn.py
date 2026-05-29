
import os

import psycopg2
from dotenv import load_dotenv

# Загружаем .env
load_dotenv('/Users/igorvasin/freelance-2026/ai-eggs/.env')

NEON_URL = os.getenv("NEON_DATABASE_URL")

def test_neon():
    print("Connecting to Neon...")
    try:
        conn = psycopg2.connect(NEON_URL)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        print("✅ Connection successful!")
        print(f"DB Version: {version[0]}")
        
        # Check if table exists
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chat_history');")
        exists = cur.fetchone()[0]
        print(f"Table 'chat_history' exists: {exists}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    test_neon()
