import asyncio
from aiogram import Bot
from aiogram.types import FSInputFile
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")

async def test_send():
    bot = Bot(token=TOKEN)
    file_path = "/Users/igorvasin/freelance-2026/ai-eggs/voice_test_user.ogg"
    chat_id = 176203333 # User's ADMIN_ID
    print("Sending...")
    try:
        await bot.send_voice(chat_id=chat_id, voice=FSInputFile(file_path))
        print("Success!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Error:", repr(e))
    finally:
        await bot.session.close()

asyncio.run(test_send())
