import os
import json
import spacy
from typing import List

# Загружаем русскую модель spaCy для умной нарезки текста
try:
    nlp = spacy.load("ru_core_news_sm")
except:
    print("⏳ Загрузка языковой модели spaCy (ru)...")
    os.system("python -m spacy download ru_core_news_sm")
    nlp = spacy.load("ru_core_news_sm")

class AngelochkaBrain:
    def __init__(self):
        self.unified_knowledge = []
        self.base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        self.data_dir = os.path.join(self.base_dir, 'data')
        os.makedirs(self.data_dir, exist_ok=True)

    def _process_text(self, text: str) -> List[str]:
        """Разбивает длинный текст на смысловые предложения (semantic chunks)"""
        if not text: return []
        doc = nlp(text)
        return [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 10]

    def load_bitrix(self):
        path = os.path.join(self.data_dir, "raw_bitrix_products.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                products = json.load(f)
                for p in products:
                    content = f"Товар: {p['NAME']}. Цена: {p['PRICE']} {p['CURRENCY_ID']}. {p.get('DESCRIPTION', '')}"
                    self.unified_knowledge.append({
                        "id": f"bitrix_{p['ID']}",
                        "source": "bitrix_crm",
                        "content": content,
                        "metadata": {"type": "product", "price": p['PRICE']}
                    })
            print(f"✔️ Загружено {len(products)} товаров из Bitrix")

    def load_avito(self):
        path = os.path.join(self.data_dir, "raw_avito_data.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
                for i in items:
                    content = f"Объявление Авито: {i['title']}. Цена: {i['price']}. Описание: {i['description']}"
                    self.unified_knowledge.append({
                        "id": f"avito_{hash(i['title'])}",
                        "source": "avito",
                        "content": content,
                        "metadata": {"type": "ad"}
                    })
            print(f"✔️ Загружено {len(items)} объявлений из Avito")

    def load_vk(self):
        path = os.path.join(self.data_dir, "raw_vk_data.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                blocks = json.load(f)
                for b in blocks:
                    if b["source"] == "vk_discussion":
                        # Группируем обсуждение в один контекст или режем по комментам
                        full_thread = f"Обсуждение ВК '{b['title']}': " + " | ".join(b["comments"])
                        self.unified_knowledge.append({
                            "id": f"vk_disc_{hash(b['title'])}",
                            "source": "vk",
                            "content": full_thread,
                            "metadata": {"type": "faq"}
                        })
            print(f"✔️ Загружено обсуждений из VK")

    def build(self):
        print("🧠 [Unify Brain]: Собираю единую базу знаний Анжелочки...")
        self.load_bitrix()
        self.load_avito()
        self.load_vk()
        
        # Сохраняем финальный файл для векторизации
        output_path = os.path.join(self.data_dir, "angelochka_unified_brain.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.unified_knowledge, f, ensure_ascii=False, indent=2)
            
        print(f"🚀 Единая база знаний готова: {output_path}")
        print(f"📊 Итого элементов знаний: {len(self.unified_knowledge)}")

if __name__ == "__main__":
    brain = AngelochkaBrain()
    brain.build()
