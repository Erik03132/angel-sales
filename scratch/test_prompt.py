import re
history = [
    {"role": "user", "parts": ["Ключевое, 120 штук, Кобб"]},
    {"role": "model", "parts": ["Кобб-500 будет по 85₽ за штуку (от 100 до 499 штук). Итого 10 200₽ за 120 цыплят. Как я могу к Вам обращаться?"]}
]

last_bot_msg = ""
for m in reversed(history or []):
    if m.get("role") == "model":
        last_bot_msg = " ".join(m.get("parts", [])).lower()
        break

dynamic_step = ""
if "номер телефона" in last_bot_msg or "оставьте ваш номер" in last_bot_msg:
    dynamic_step = "ШАГ 4..."
elif ("как я могу" in last_bot_msg and "обращаться" in last_bot_msg) or "как вас зовут" in last_bot_msg or "ваше имя" in last_bot_msg:
    dynamic_step = "ШАГ 3: Ты только что спросила ИМЯ. Твоя задача сейчас — дословно сказать: «Оставьте Ваш номер телефона, я забронирую партию.» 🚫 ЗАПРЕТ спрашивать имя или город."
elif "город" in last_bot_msg or "количество" in last_bot_msg:
    dynamic_step = "ШАГ 2..."
else:
    dynamic_step = "ШАГ 1..."

print(f"last_bot_msg: {last_bot_msg}")
print(f"dynamic_step: {dynamic_step}")
