from marketer import MarketerStrategist
from rembrandt import RembrandtDesigner
from shakespeare import ShakespeareEditor


def run_campaign(topic="Сравнение РОСС-308 и КОББ-500: Что выбрать фермеру на юге России?"):
    print("="*60)
    print("👑 АНЖЕЛА ПТЕНЧИКОВА: Даю старт маркетинговой кампании!")
    print(f"Тема: {topic}")
    print("="*60)
    
    # 1. Задачу берет Маркетолог
    print("\n--- Шаг 1: Работает МАРКЕТОЛОГ ---")
    marketer = MarketerStrategist()
    brief = marketer.generate_brief(topic)
    
    # 2. Параллельно задачу берет Дизайнер
    print("\n--- Шаг 2: Работает РЕМБРАНДТ ---")
    rembrandt = RembrandtDesigner()
    img_url = rembrandt.generate_cover(topic, context="Деревенский стиль, теплый желтый свет инкубатора")
    
    # 3. По готовности брифа задачу берет Шекспир
    print("\n--- Шаг 3: Работает ШЕКСПИР ---")
    shakespeare = ShakespeareEditor()
    article_text = shakespeare.write_article(brief)
    
    print("\n" + "="*60)
    print("📢 ИТОГОВЫЙ МАТЕРИАЛ ДЛЯ УТВЕРЖДЕНИЯ (Генерирует Птенчикова):")
    print("="*60)
    print(f"Обложка статьи: {img_url}\n")
    print("--- Текст ---")
    print(article_text)
    print("==========================================================")
    print("Птенчикова: Сборка завершена. Ожидаю апрува для отправки в Битрикс Sandbox.")

if __name__ == "__main__":
    run_campaign()
