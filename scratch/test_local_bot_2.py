import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agent'))
from angelochka_core import get_answer

def run_test():
    print("🤖 ЛОКАЛЬНЫЙ ТЕСТ ВОРОНКИ 2: Ветвь с 'Армавир' 🤖")
    print("=" * 50)
    
    history = []
    
    msg1 = "бройлеры цены"
    print(f"👤 Клиент: {msg1}")
    ans1 = get_answer(msg1, history)
    print(f"🐣 Анжелочка: {ans1}\n")
    history.append({"role": "user", "parts": [msg1]})
    history.append({"role": "model", "parts": [ans1]})
    
    msg2 = "Армавир"
    print(f"👤 Клиент: {msg2}")
    ans2 = get_answer(msg2, history)
    print(f"🐣 Анжелочка: {ans2}\n")
    history.append({"role": "user", "parts": [msg2]})
    history.append({"role": "model", "parts": [ans2]})

if __name__ == "__main__":
    run_test()
