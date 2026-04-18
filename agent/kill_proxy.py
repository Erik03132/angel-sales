import re

with open("tg_bot.py", "r") as f:
    code = f.read()

# Replace session object
code = code.replace("bot = Bot(token=TELEGRAM_TOKEN, session=session)", "bot = Bot(token=TELEGRAM_TOKEN) # session=session")

with open("tg_bot.py", "w") as f:
    f.write(code)
