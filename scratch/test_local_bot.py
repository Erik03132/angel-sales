import sys
import os

# Добавляем путь к основному коду, чтобы импорты работали
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agent'))

from angelochka_core import get_answer

def run_test():
    print("🤖 ЛОКАЛЬНЫЙ ТЕСТ ВОРОНКИ АНЖЕЛОЧКИ 🤖")
    print("=" * 50)
    
    history = []
    
    # Реплика 1
    msg1 = "Какие есть несушки?"
    print(f"👤 Клиент: {msg1}")
    ans1 = get_answer(msg1, history)
    print(f"🐣 Анжелочка: {ans1}\n")
    history.append({"role": "user", "parts": [msg1]})
    history.append({"role": "model", "parts": [ans1]})
    
    # Реплика 2
    msg2 = "Ключевое, 120 штук, Кобб"
    print(f"👤 Клиент: {msg2}")
    ans2 = get_answer(msg2, history)
    print(f"🐣 Анжелочка: {ans2}\n")
    history.append({"role": "user", "parts": [msg2]})
    history.append({"role": "model", "parts": [ans2]})
    
    # Реплика 3
    msg3 = "Эдуард, а что?"
    print(f"👤 Клиент: {msg3}")
    ans3 = get_answer(msg3, history)
    print(f"🐣 Анжелочка: {ans3}\n")
    history.append({"role": "user", "parts": [msg3]})
    history.append({"role": "model", "parts": [ans3]})
    
    # Реплика 4
    msg4 = "89991234567"
    print(f"👤 Клиент: {msg4}")
    ans4 = get_answer(msg4, history)
    print(f"🐣 Анжелочка: {ans4}\n")

if __name__ == "__main__":
    run_test()
