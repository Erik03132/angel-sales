import os


class ShakespeareEditor:
    """
    ✍️ Агент-Копирайтер (Шекспир)
    Отвечает за написание E-E-A-T статей, постов для ВКонтакте и Авито-объявлений по ТЗ.
    Подчиняется Анжеле Птенчиковой.
    """
    
    def __init__(self):
        self.name = "Шекспир-Копирайтер"
        self.skill_path = os.path.expanduser("~/.gemini/antigravity/skills/shakespeare-editor/SKILL.md")
        self.system_prompt = self._load_skill()

    def _load_skill(self):
        """Загружает скилл из базы знаний Antigravity"""
        if os.path.exists(self.skill_path):
            with open(self.skill_path, "r", encoding="utf-8") as f:
                return f.read()
        return "Ты — Копирайтер Шекспир."

    def write_article(self, brief: dict) -> dict:
        """
        Генерирует контент на основе брифа от Маркетолога.
        Адаптирует текст под 5 разных форматов: Дзен, ВКонтакте, Telegram, MAX и Отраслевые площадки.
        """
        print(f"[{self.name}] 🖋️ Получил ТЗ от Маркетолога. Тема: {brief['topic']}")
        print(f"[{self.name}] 🧩 Интегрирую ключи: {', '.join(brief['seo_keywords'])}")
        
        import json

        import requests
        from dotenv import load_dotenv
        
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'), override=True)
        
        system_prompt = (
            f"{self.system_prompt}\n\n"
            "Твоя задача — выступить омниканальным E-E-A-T копирайтером.\n"
            "Верни ответ СТРОГО в формате валидного JSON (БЕЗ markdown-разметки, только JSON-объект):\n"
            "{\n"
            '  "zen": "полная статья с H2 (строка)",\n'
            '  "vk": "короткий пост с эмодзи (строка)",\n'
            '  "ok": "теплый ламповый пост для Одноклассников (строка)",\n'
            '  "telegram": "буллиты для ТГ (строка)",\n'
            '  "max": "формат рассылки MAX (строка)",\n'
            '  "industry": "экспертная аналитика (строка)"\n'
            "}\n"
            "CRITICAL: Each value in the JSON MUST be a single flat string containing the text of the article. DO NOT return nested objects, keys, or JSON structures inside the quotes."
        )
        
        user_prompt = f"Напиши статью на тему: '{brief['topic']}'.\nОбязательные ключи: {', '.join(brief.get('seo_keywords', []))}\nТребования: {brief.get('requirements', '')}"
        
        models_cascade = [
            "google/gemini-2.0-flash-001",
            "openai/gpt-4o-mini",
            "google/gemini-flash-1.5"
        ]
        
        for model in models_cascade:
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}", "Content-Type": "application/json"} if os.getenv('OPENROUTER_API_KEY') else {},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    },
                    timeout=60
                )
                data = resp.json()
                if "choices" in data:
                    content = data["choices"][0]["message"]["content"]
                    content = content.strip().lstrip('`json').lstrip('`').rstrip('`').strip()
                    omnichannel_content = json.loads(content)
                    print(f"[{self.name}] ✅ Омниканальный контент сгенерирован LLM (модель {model}).")
                    return omnichannel_content
                else:
                    print(f"[{self.name}] ⚠️ Модель {model} недоступна. Ошибка: {data.get('error', {}).get('message', 'Unknown')}")
            except Exception as e:
                print(f"[{self.name}] ⚠️ Исключение при вызове {model}: {str(e)[:50]}")
                
        print(f"[{self.name}] ❌ Ошибка LLM, использую текст-заглушку.")
        return {
            "zen": f"# {brief['topic']}\n\n*Ошибка генерации: Сбой всех API-моделей...*",
            "vk": "Ошибка генерации.",
            "telegram": "Ошибка генерации.",
            "max": "Ошибка генерации.",
            "industry": "Ошибка генерации."
        }

if __name__ == "__main__":
    shakespeare = ShakespeareEditor()
    mock_brief = {
        "topic": "5 главных ошибок при покупке бройлеров",
        "seo_keywords": ["КОББ-500", "РОСС-308"],
        "geo_triplets": ["Азовский Инкубатор -> доставляет", "КОББ-500 -> набирает вес"],
        "requirements": "Без воды"
    }
    result = shakespeare.write_article(mock_brief)
    print("\n--- РЕЗУЛЬТАТ ---")
    for platform, text in result.items():
        print(f"\n[{platform.upper()}]:\n{text}")
