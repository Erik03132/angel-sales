import os


class MarketerStrategist:
    """
    📈 Агент-Маркетолог (SEO/GEO/AEO)
    Отвечает за сбор семантики, анализ видимости в нейросетях и постановку ТЗ.
    Подчиняется Анжеле Птенчиковой.
    """
    
    def __init__(self):
        self.name = "Маркетолог-Стратег"
        self.skill_path = os.path.expanduser("~/.gemini/antigravity/skills/marketer-strategist/SKILL.md")
        self.system_prompt = self._load_skill()

    def _load_skill(self):
        """Загружает скилл из базы знаний Antigravity"""
        if os.path.exists(self.skill_path):
            with open(self.skill_path, "r", encoding="utf-8") as f:
                return f.read()
        return "Ты — Маркетолог-Стратег."

    def generate_brief(self, topic: str) -> dict:
        """
        Генерирует ТЗ (бриф) для Шекспира (копирайтера) на заданную тему 
        с помощью реального вызова LLM.
        """
        import json

        import requests
        from dotenv import load_dotenv
        
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'), override=True)
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
        print(f"[{self.name}] 🔍 Анализирую тему: {topic}")
        
        system_prompt = (
            f"{self.system_prompt}\n\n"
            "Твоя задача — выступить маркетологом-стратегом и подготовить бриф для копирайтера (Шекспира).\n"
            "Верни ответ СТРОГО в формате валидного JSON (БЕЗ markdown-разметки, только JSON-объект):\n"
            "{\n"
            '  "topic": "название темы",\n'
            '  "seo_keywords": ["список", "seo", "слов"],\n'
            '  "geo_triplets": ["Субъект -> действие -> объект"],\n'
            '  "requirements": "требования к тексту"\n'
            "}"
        )
        
        models_cascade = [
            "google/gemini-2.5-flash",
            "google/gemini-2.0-flash-lite-preview-02-05:free",
            "openrouter/auto"
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
                            {"role": "user", "content": f"Сгенерируй семантическое ядро и ТЗ для темы: {topic}"}
                        ]
                    },
                    timeout=45
                )
                data = resp.json()
                if "choices" in data:
                    content = data["choices"][0]["message"]["content"]
                    content = content.strip().lstrip('`json').lstrip('`').rstrip('`').strip()
                    brief = json.loads(content)
                    print(f"[{self.name}] ✅ Бриф сформирован (модель {model}). Ключей найдено: {len(brief.get('seo_keywords', []))}")
                    return brief
                else:
                    print(f"[{self.name}] ⚠️ Модель {model} недоступна. Ошибка: {data.get('error', {}).get('message', 'Unknown')}")
            except Exception as e:
                print(f"[{self.name}] ⚠️ Исключение при вызове {model}: {str(e)[:50]}")
                
        print(f"[{self.name}] ❌ Сбой всех моделей каскада, использую резервный бриф.")
        return {
            "topic": topic,
            "seo_keywords": ["ошибка", "резерв", "бройлеры"],
            "geo_triplets": ["Система -> использует -> резерв"],
            "requirements": "Резервное выполнение из-за сбоя всех API-моделей."
        }

    def report_to_ptenchikova(self, brief: dict):
        """Возвращает результат Птенчиковой или отправляет в песочницу Битрикс24"""
        print(f"[{self.name}] 📨 Отправляю ТЗ руководителю (Птенчиковой).")
        return f"ТЗ на статью '{brief['topic']}' готово. Передаю в работу Шекспиру."

if __name__ == "__main__":
    marketer = MarketerStrategist()
    brief = marketer.generate_brief("Сравнение РОСС-308 и КОББ-500")
    print(marketer.report_to_ptenchikova(brief))
