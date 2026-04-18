#!/usr/bin/env python3
"""
Стресс-тест Анжелочки: 20 самых частых вопросов клиентов птицефабрики.
Генерирует HTML-отчёт с оценкой качества.
"""

import requests
import json
import time
import html
from datetime import datetime

API_URL = "http://localhost:8001/api/chat"

# 20 самых вероятных вопросов клиентов Азовского Инкубатора
QUESTIONS = [
    # Базовые / приветственные
    ("Приветствие", "Привет, вы работаете?"),
    ("Ассортимент", "Чем вы торгуете? Что у вас есть?"),
    
    # Бройлеры
    ("Бройлеры — цена", "Сколько стоят бройлеры?"),
    ("Кобб-500 vs РОСС", "Какая разница между Кобб-500 и РОСС? Что лучше?"),
    
    # Другая птица
    ("Мулларды", "Есть мулларды? Почём? И чем они отличаются от обычных уток?"),
    ("Индюки", "Какие индюки есть? Сколько стоят? До какого веса дорастают?"),
    ("Несушки", "Мне нужны несушки, которые будут нестись. Что посоветуете?"),
    ("Народный синоним", "Хочу пекинку. Есть?"),
    
    # Цены и заказ
    ("Минимальный заказ", "Какой минимальный заказ? Можно взять 10 штук?"),
    ("Большой заказ", "Мне нужно 500 кобб-500 и 200 мулардов. Посчитайте сколько выйдет?"),
    ("Оплата", "Как можно оплатить?"),
    
    # Доставка и локация
    ("Адрес", "Где вы находитесь? В каком городе?"),
    ("Доставка Краснодар", "Вы доставляете в Краснодар? Сколько стоит доставка?"),
    ("Доставка Москва", "А в Москву привезёте?"),
    
    # Уход и содержание
    ("Температура", "Какая температура нужна цыплятам в первые дни?"),
    ("Кормление", "Чем кормить бройлеров? Какой корм брать? Сколько корма нужно?"),
    ("Вакцинация", "Птица вакцинирована? Какие прививки делаете?"),
    
    # Возражения
    ("Возражение — дорого", "Дорого! У конкурентов дешевле."),
    ("Гарантии", "А если птенцы сдохнут по дороге? Какие гарантии?"),
    
    # Закрытие сделки
    ("Заказ", "Хочу заказать 100 Кобб-500 на следующую неделю. Как забронировать?"),
]

def test_angelochka():
    results = []
    total_time = 0
    
    print(f"\n🧪 Стресс-тест Анжелочки v9.0")
    print(f"   Вопросов: {len(QUESTIONS)}")
    print(f"   API: {API_URL}")
    print(f"   Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    
    for i, (category, question) in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] {category}: {question[:50]}...")
        
        start = time.time()
        try:
            resp = requests.post(API_URL, json={"message": question}, timeout=30)
            elapsed = time.time() - start
            total_time += elapsed
            
            if resp.status_code == 200:
                answer = resp.json().get("response", "ПУСТОЙ ОТВЕТ")
                status = "✅"
            else:
                answer = f"HTTP {resp.status_code}: {resp.text}"
                status = "❌"
        except requests.exceptions.Timeout:
            elapsed = 30
            answer = "ТАЙМАУТ (30 сек)"
            status = "⏱️"
        except Exception as e:
            elapsed = time.time() - start
            answer = f"ОШИБКА: {str(e)}"
            status = "❌"
        
        print(f"   {status} ({elapsed:.1f}s) → {answer[:60]}...\n")
        
        results.append({
            "num": i,
            "category": category,
            "question": question,
            "answer": answer,
            "time": elapsed,
            "status": status
        })
        
        # Пауза между запросами (не перегружаем LLM)
        time.sleep(1)
    
    return results, total_time

def generate_html_report(results, total_time):
    success = sum(1 for r in results if r["status"] == "✅")
    avg_time = total_time / len(results) if results else 0
    
    rows = ""
    for r in results:
        answer_escaped = html.escape(r["answer"]).replace("\n", "<br>")
        question_escaped = html.escape(r["question"])
        
        status_color = "#22c55e" if r["status"] == "✅" else "#ef4444"
        time_color = "#22c55e" if r["time"] < 5 else ("#f59e0b" if r["time"] < 10 else "#ef4444")
        
        rows += f"""
        <tr>
            <td style="text-align:center; font-weight:600;">{r["num"]}</td>
            <td><span class="badge">{html.escape(r["category"])}</span></td>
            <td class="question">{question_escaped}</td>
            <td class="answer">{answer_escaped}</td>
            <td style="text-align:center; color:{time_color}; font-weight:600;">{r["time"]:.1f}s</td>
            <td style="text-align:center; font-size:1.2em; color:{status_color};">{r["status"]}</td>
        </tr>
        """
    
    report_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчёт: Тестирование Анжелочки v9.0</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0c0f1a;
            --card: #151928;
            --card-light: #1c2237;
            --primary: #f59e0b;
            --accent: #38bdf8;
            --green: #22c55e;
            --red: #ef4444;
            --text: #e2e8f0;
            --text-dim: #94a3b8;
            --border: #2d3655;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 40px 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        
        /* Header */
        header {{
            text-align: center;
            margin-bottom: 50px;
        }}
        header h1 {{
            font-size: 2.2em;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 8px;
        }}
        header p {{
            color: var(--text-dim);
            font-size: 1.1em;
        }}
        
        /* Stats */
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .stat-card {{
            background: var(--card);
            border-radius: 16px;
            padding: 28px;
            text-align: center;
            border: 1px solid var(--border);
            transition: transform 0.2s;
        }}
        .stat-card:hover {{ transform: translateY(-2px); }}
        .stat-card .value {{
            font-size: 2.4em;
            font-weight: 700;
            color: var(--primary);
        }}
        .stat-card .label {{
            color: var(--text-dim);
            font-size: 0.9em;
            margin-top: 4px;
        }}
        .stat-card.green .value {{ color: var(--green); }}
        .stat-card.accent .value {{ color: var(--accent); }}
        
        /* Table */
        .table-container {{
            background: var(--card);
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid var(--border);
            margin-bottom: 40px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        thead th {{
            background: var(--card-light);
            color: var(--primary);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75em;
            letter-spacing: 0.05em;
            padding: 16px 14px;
            text-align: left;
            border-bottom: 2px solid var(--border);
            position: sticky;
            top: 0;
        }}
        tbody td {{
            padding: 16px 14px;
            border-bottom: 1px solid var(--border);
            vertical-align: top;
        }}
        tbody tr:hover {{ background: rgba(245, 158, 11, 0.03); }}
        
        .question {{
            color: var(--accent);
            font-weight: 500;
            min-width: 200px;
        }}
        .answer {{
            color: var(--text);
            font-size: 0.92em;
            line-height: 1.7;
            max-width: 500px;
        }}
        .badge {{
            display: inline-block;
            background: rgba(245, 158, 11, 0.15);
            color: var(--primary);
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 0.8em;
            font-weight: 500;
            white-space: nowrap;
        }}
        
        /* Footer */
        .recommendations {{
            background: var(--card);
            border-radius: 16px;
            padding: 32px;
            border: 1px solid var(--border);
        }}
        .recommendations h2 {{
            color: var(--primary);
            margin-bottom: 20px;
        }}
        .recommendations ul {{
            list-style: none;
        }}
        .recommendations li {{
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
            color: var(--text-dim);
        }}
        .recommendations li:last-child {{ border-bottom: none; }}
        .recommendations li strong {{ color: var(--text); }}
        
        footer {{
            text-align: center;
            padding: 40px;
            color: var(--text-dim);
            font-size: 0.85em;
        }}
        
        @media print {{
            body {{ background: white; color: #1a1a1a; padding: 20px; }}
            .stat-card {{ border: 1px solid #ddd; }}
            .table-container {{ border: 1px solid #ddd; }}
            thead th {{ background: #f5f5f5; color: #333; }}
            tbody td {{ border-bottom: 1px solid #eee; }}
            .question {{ color: #0066cc; }}
            .answer {{ color: #333; }}
            .badge {{ background: #fff3cd; color: #856404; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🐣 Тест-драйв: Анжелочка v9.0</h1>
            <p>Стресс-тест AI-менеджера «Азовского Инкубатора» — {datetime.now().strftime('%d.%m.%Y, %H:%M')}</p>
        </header>
        
        <div class="stats">
            <div class="stat-card">
                <div class="value">{len(results)}</div>
                <div class="label">Вопросов задано</div>
            </div>
            <div class="stat-card green">
                <div class="value">{success}/{len(results)}</div>
                <div class="label">Успешных ответов</div>
            </div>
            <div class="stat-card accent">
                <div class="value">{avg_time:.1f}s</div>
                <div class="label">Среднее время ответа</div>
            </div>
            <div class="stat-card">
                <div class="value">{total_time:.0f}s</div>
                <div class="label">Общее время теста</div>
            </div>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="text-align:center">#</th>
                        <th>Категория</th>
                        <th>Вопрос клиента</th>
                        <th>Ответ Анжелочки</th>
                        <th style="text-align:center">Время</th>
                        <th style="text-align:center">Статус</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        
        <footer>
            <p>Отчёт сгенерирован автоматически · Antigravity AI · {datetime.now().strftime('%d.%m.%Y')}</p>
        </footer>
    </div>
</body>
</html>"""
    return report_html


if __name__ == "__main__":
    results, total_time = test_angelochka()
    
    report = generate_html_report(results, total_time)
    
    output_path = "/Users/igorvasin/freelance-2026/ai-eggs/ANGELOCHKA_TEST_REPORT.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    success = sum(1 for r in results if r["status"] == "✅")
    print(f"\n{'='*50}")
    print(f"📊 ИТОГО: {success}/{len(results)} успешных ответов")
    print(f"⏱️ Среднее время: {total_time/len(results):.1f}s")
    print(f"📄 Отчёт: {output_path}")
    print(f"{'='*50}\n")
