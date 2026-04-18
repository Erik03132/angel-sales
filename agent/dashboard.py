import os
from flask import Flask, render_template_string
import psycopg2
from dotenv import load_dotenv
import markdown2

load_dotenv()

app = Flask(__name__)

# Настройки БД
DATABASE_URL = os.getenv("NEON_DATABASE_URL")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "../logs/history.md")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Angelochka Dashboard | Контроль</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --primary: #f59e0b;
            --text: #f1f5f9;
            --accent: #38bdf8;
        }
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 20px;
            line-height: 1.6;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            border-bottom: 2px solid var(--card);
            padding-bottom: 20px;
        }
        h1 { color: var(--primary); margin: 0; }
        .nav { display: flex; gap: 20px; }
        .nav a { color: var(--text); text-decoration: none; font-weight: 600; padding: 10px 20px; border-radius: 8px; transition: 0.3s; }
        .nav a:hover { background: var(--card); color: var(--primary); }
        .nav a.active { background: var(--primary); color: var(--bg); }

        .card {
            background: var(--card);
            border-radius: 16px;
            padding: 25px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3);
            margin-bottom: 30px;
        }
        
        /* Чат логи */
        .log-content {
            background: #000;
            padding: 20px;
            border-radius: 12px;
            height: 600px;
            overflow-y: auto;
            border-left: 4px solid var(--primary);
        }
        .log-content h2 { color: var(--accent); border-bottom: 1px solid #333; }
        
        /* Таблица склада */
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            text-align: left;
            padding: 15px;
            border-bottom: 1px solid #334155;
        }
        th { color: var(--primary); font-weight: 600; text-transform: uppercase; font-size: 0.8em; }
        tr:hover { background: rgba(245, 158, 11, 0.05); }
        .badge {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8em;
            background: var(--primary);
            color: var(--bg);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🐣 Angelochka <span style="font-weight:300">Zabotkina</span></h1>
            <div class="nav">
                <a href="/" class="{{ 'active' if page == 'history' else '' }}">Последние Диалоги</a>
                <a href="/inventory" class="{{ 'active' if page == 'inventory' else '' }}">Состояние Склада</a>
            </div>
        </header>

        {% if page == 'history' %}
        <div class="card">
            <h3 style="margin-top:0">📡 Прямой эфир диалогов</h3>
            <div class="log-content">
                {{ content | safe }}
            </div>
        </div>
        {% elif page == 'inventory' %}
        <div class="card">
            <h3 style="margin-top:0">📦 Актуальные остатки (Neon DB)</h3>
            <table>
                <thead>
                    <tr>
                        <th>Товар</th>
                        <th>Цена</th>
                        <th>Остаток</th>
                        <th>Статус</th>
                        <th>Доп. Свойства</th>
                    </tr>
                </thead>
                <tbody>
                    {% for p in products %}
                    <tr>
                        <td><strong>{{ p[1] }}</strong></td>
                        <td>{{ p[2] }} ₽</td>
                        <td><span class="badge">{{ p[3] }} шт</span></td>
                        <td>{{ p[4] }}</td>
                        <td style="font-size: 0.8em; color: #94a3b8">{{ p[5] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </div>
    
    <script>
        // Автопрокрутка логов вниз
        const logContent = document.querySelector('.log-content');
        if (logContent) {
            logContent.scrollTop = logContent.scrollHeight;
        }
        // Автоматическое обновление каждые 15 секунд
        setTimeout(() => { location.reload(); }, 15000);
    </script>
</body>
</html>
"""

@app.route("/")
def history():
    content = "Диалогов пока нет..."
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            raw_md = f.read()
            content = markdown2.markdown(raw_md)
    return render_template_string(HTML_TEMPLATE, page="history", content=content)

@app.route("/inventory")
def inventory():
    products = []
    if DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT id, name, price, quantity, stock_status, raw_properties FROM products ORDER BY name ASC")
            products = cur.fetchall()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Error: {e}")
    return render_template_string(HTML_TEMPLATE, page="inventory", products=products)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055)
