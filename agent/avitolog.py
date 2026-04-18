#!/usr/bin/env python3
"""
🎯 АВИТОЛОГ — AI-агент управления рекламными кампаниями на Avito.

Фазы работы:
1. РАЗВЕДКА: Получение всех объявлений через Avito API
2. АНАЛИТИКА: Статистика по каждому объявлению (просмотры, звонки, избранное)
3. АУДИТ: Классификация объявлений (🟢 работает / 🟡 оптимизировать / 🔴 закрыть)
4. РЕКОМЕНДАЦИИ: Конкретные действия по каждому объявлению
5. АВТОПИЛОТ: Автоматическая оптимизация заголовков, описаний, цен

Запуск: python3 avitolog.py
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

AVITO_CLIENT_ID = os.getenv("AVITO_CLIENT_ID", "")
AVITO_CLIENT_SECRET = os.getenv("AVITO_CLIENT_SECRET", "")
AVITO_USER_ID = os.getenv("AVITO_USER_ID", "71718357")  # ID профиля IncuBird

DATA_DIR = os.path.join(BASE_DIR, "data", "avito")
os.makedirs(DATA_DIR, exist_ok=True)

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


class AvitoAPI:
    """Клиент Avito REST API v2."""
    
    BASE_URL = "https://api.avito.ru"
    
    def __init__(self, client_id, client_secret, user_id):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self.token = None
        self.token_expires = 0
    
    def authenticate(self):
        """Получаем OAuth2 токен."""
        try:
            resp = requests.post(f"{self.BASE_URL}/token/", data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials"
            }, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                if "access_token" in data:
                    self.token = data["access_token"]
                    self.token_expires = time.time() + data.get("expires_in", 3600)
                    log(f"✅ Авторизация Avito OK (токен на {data.get('expires_in', 3600)} сек)")
                    return True
                else:
                    log(f"❌ Ошибка авторизации: {data}")
                    return False
            else:
                log(f"❌ HTTP {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            log(f"❌ Ошибка подключения: {e}")
            return False
    
    def _headers(self):
        if time.time() > self.token_expires - 60:
            self.authenticate()
        return {"Authorization": f"Bearer {self.token}"}
    
    def get_items(self, per_page=25, page=1, status="active"):
        """Получаем список объявлений.
        
        API: GET /core/v1/items
        Params: per_page, page, status (active/removed/old/blocked)
        """
        resp = requests.get(f"{self.BASE_URL}/core/v1/items", 
            headers=self._headers(),
            params={"per_page": per_page, "page": page, "status": status},
            timeout=15)
        if resp.status_code == 200:
            return resp.json().get("resources", [])
        log(f"  Items error: {resp.status_code} - {resp.text[:200]}")
        return []
    
    def get_all_items(self, status="active"):
        """Получаем ВСЕ объявления с пагинацией."""
        all_items = []
        page = 1
        while True:
            items = self.get_items(per_page=50, page=page, status=status)
            if not items:
                break
            all_items.extend(items)
            page += 1
            time.sleep(0.5)  # Не перегружаем API
        log(f"📦 Всего объявлений (status={status}): {len(all_items)}")
        return all_items
    
    def get_item_stats(self, item_ids, date_from=None, date_to=None):
        """Статистика по объявлениям.
        
        API: POST /core/v1/items/stats
        Возвращает: просмотры, звонки, избранное, сообщения.
        """
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        
        resp = requests.post(f"{self.BASE_URL}/core/v1/items/stats", 
            headers=self._headers(),
            json={
                "itemIds": item_ids[:200],  # Максимум 200 за раз
                "dateFrom": date_from,
                "dateTo": date_to,
                "fields": ["uniqViews", "uniqContacts", "uniqFavorites"]
            },
            timeout=30)
        
        if resp.status_code == 200:
            return resp.json().get("result", {}).get("items", [])
        log(f"  Stats error: {resp.status_code} - {resp.text[:200]}")
        return []
    
    def get_item_info(self, item_id):
        """Детальная информация по объявлению.
        
        API: GET /core/v1/accounts/{user_id}/items/{item_id}/
        """
        resp = requests.get(
            f"{self.BASE_URL}/core/v1/accounts/{self.user_id}/items/{item_id}/",
            headers=self._headers(),
            timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return {}
    
    def get_vas_costs(self, item_ids):
        """Стоимость продвижения для объявлений.
        
        API: POST /core/v1/accounts/{user_id}/price/vas
        """
        resp = requests.post(
            f"{self.BASE_URL}/core/v1/accounts/{self.user_id}/price/vas",
            headers=self._headers(),
            json={"itemIds": item_ids},
            timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return {}


class Avitolog:
    """Главный агент-аудитор Авито."""
    
    def __init__(self):
        self.api = AvitoAPI(AVITO_CLIENT_ID, AVITO_CLIENT_SECRET, AVITO_USER_ID)
        self.items = []
        self.stats = {}
        self.audit_results = []
    
    def phase1_collect(self):
        """Фаза 1: Сбор всех объявлений."""
        log("=" * 60)
        log("🔍 ФАЗА 1: СБОР ДАННЫХ")
        log("=" * 60)
        
        if not self.api.authenticate():
            log("❌ Не удалось авторизоваться. Нужны свежие API-ключи!")
            return False
        
        self.items = self.api.get_all_items("active")
        
        # Сохраняем сырые данные
        with open(os.path.join(DATA_DIR, "raw_items.json"), "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=2)
        
        log(f"💾 Сохранено в data/avito/raw_items.json")
        return True
    
    def phase2_analyze(self):
        """Фаза 2: Получаем статистику по каждому объявлению."""
        log("=" * 60)
        log("📊 ФАЗА 2: АНАЛИТИКА")
        log("=" * 60)
        
        item_ids = [item["id"] for item in self.items]
        
        # Получаем статистику за 30 дней
        stats_30d = self.api.get_item_stats(item_ids)
        # Получаем статистику за 7 дней (для тренда)
        stats_7d = self.api.get_item_stats(
            item_ids,
            date_from=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        )
        
        # Объединяем
        for item in self.items:
            item_id = item["id"]
            s30 = next((s for s in stats_30d if s.get("itemId") == item_id), {})
            s7 = next((s for s in stats_7d if s.get("itemId") == item_id), {})
            
            self.stats[item_id] = {
                "views_30d": sum(d.get("uniqViews", 0) for d in s30.get("stats", [])),
                "contacts_30d": sum(d.get("uniqContacts", 0) for d in s30.get("stats", [])),
                "favorites_30d": sum(d.get("uniqFavorites", 0) for d in s30.get("stats", [])),
                "views_7d": sum(d.get("uniqViews", 0) for d in s7.get("stats", [])),
                "contacts_7d": sum(d.get("uniqContacts", 0) for d in s7.get("stats", [])),
            }
        
        # Сохраняем
        with open(os.path.join(DATA_DIR, "items_stats.json"), "w", encoding="utf-8") as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
        
        log(f"📊 Статистика по {len(self.stats)} объявлениям сохранена")
        return True
    
    def phase3_audit(self):
        """Фаза 3: Классификация каждого объявления."""
        log("=" * 60)
        log("🎯 ФАЗА 3: АУДИТ")
        log("=" * 60)
        
        for item in self.items:
            item_id = item["id"]
            stats = self.stats.get(item_id, {})
            
            views = stats.get("views_30d", 0)
            contacts = stats.get("contacts_30d", 0)
            favorites = stats.get("favorites_30d", 0)
            views_7d = stats.get("views_7d", 0)
            
            # Конверсия «просмотр → контакт»
            cvr = (contacts / views * 100) if views > 0 else 0
            
            # Тренд (последняя неделя vs средняя за месяц)
            avg_weekly_views = views / 4.3 if views > 0 else 0
            trend = ((views_7d / avg_weekly_views) - 1) * 100 if avg_weekly_views > 0 else 0
            
            # Классификация
            if views == 0 and contacts == 0:
                grade = "🔴 МЁРТВОЕ"
                action = "Закрыть или полностью переделать"
            elif cvr < 0.5:
                grade = "🔴 НЕЭФФЕКТИВНОЕ"
                action = "Переделать заголовок и описание, проверить цену"
            elif cvr < 2.0:
                grade = "🟡 СРЕДНЕ"
                action = "Оптимизировать заголовок, добавить фото"
            elif cvr >= 2.0 and views >= 50:
                grade = "🟢 РАБОТАЕТ"
                action = "Оставить, масштабировать"
            else:
                grade = "🟡 МАЛО ТРАФИКА"
                action = "Поднять в поиске, добавить ключевые слова"
            
            result = {
                "id": item_id,
                "title": item.get("title", ""),
                "price": item.get("price", 0),
                "url": item.get("url", f"https://www.avito.ru/{item_id}"),
                "views_30d": views,
                "contacts_30d": contacts,
                "favorites_30d": favorites,
                "cvr": round(cvr, 2),
                "trend": round(trend, 1),
                "grade": grade,
                "action": action
            }
            self.audit_results.append(result)
        
        # Сортируем: сначала мёртвые, потом по конверсии
        self.audit_results.sort(key=lambda x: x["cvr"])
        
        # Сохраняем
        with open(os.path.join(DATA_DIR, "audit_results.json"), "w", encoding="utf-8") as f:
            json.dump(self.audit_results, f, ensure_ascii=False, indent=2)
        
        # Считаем статистику
        dead = sum(1 for r in self.audit_results if "МЁРТВОЕ" in r["grade"])
        bad = sum(1 for r in self.audit_results if "НЕЭФФЕКТИВНОЕ" in r["grade"])
        mid = sum(1 for r in self.audit_results if "СРЕДНЕ" in r["grade"] or "МАЛО" in r["grade"])
        good = sum(1 for r in self.audit_results if "РАБОТАЕТ" in r["grade"])
        
        log(f"")
        log(f"🎯 РЕЗУЛЬТАТ АУДИТА:")
        log(f"  🟢 Работает: {good}")
        log(f"  🟡 Нужна оптимизация: {mid}")
        log(f"  🔴 Неэффективные: {bad}")
        log(f"  🔴 Мёртвые (0 просмотров): {dead}")
        log(f"")
        
        return True
    
    def phase4_report(self):
        """Фаза 4: Генерация отчёта."""
        log("=" * 60)
        log("📝 ФАЗА 4: ОТЧЁТ")
        log("=" * 60)
        
        report_lines = []
        report_lines.append("# 🎯 АУДИТ AVITO — IncuBird\n")
        report_lines.append(f"**Дата:** {datetime.now().strftime('%d.%m.%Y')}")
        report_lines.append(f"**Всего объявлений:** {len(self.audit_results)}\n")
        
        # Сводка
        dead = [r for r in self.audit_results if "МЁРТВОЕ" in r["grade"]]
        bad = [r for r in self.audit_results if "НЕЭФФЕКТИВНОЕ" in r["grade"]]
        mid = [r for r in self.audit_results if "СРЕДНЕ" in r["grade"] or "МАЛО" in r["grade"]]
        good = [r for r in self.audit_results if "РАБОТАЕТ" in r["grade"]]
        
        report_lines.append("## 📊 Сводка\n")
        report_lines.append(f"| Категория | Кол-во | % |")
        report_lines.append(f"|---|---|---|")
        total = len(self.audit_results) or 1
        report_lines.append(f"| 🟢 Работает | {len(good)} | {len(good)/total*100:.0f}% |")
        report_lines.append(f"| 🟡 Нужна оптимизация | {len(mid)} | {len(mid)/total*100:.0f}% |")
        report_lines.append(f"| 🔴 Неэффективные | {len(bad)} | {len(bad)/total*100:.0f}% |")
        report_lines.append(f"| 🔴 Мёртвые | {len(dead)} | {len(dead)/total*100:.0f}% |")
        report_lines.append("")
        
        # Детали по каждой категории
        for category_name, items in [("🔴 ЗАКРЫТЬ (мёртвые)", dead), 
                                       ("🔴 ПЕРЕДЕЛАТЬ (неэффективные)", bad),
                                       ("🟡 ОПТИМИЗИРОВАТЬ", mid),
                                       ("🟢 МАСШТАБИРОВАТЬ", good)]:
            if items:
                report_lines.append(f"\n## {category_name}\n")
                report_lines.append(f"| # | Объявление | Цена | Просм./мес | Контакты | CVR% | Действие |")
                report_lines.append(f"|---|---|---|---|---|---|---|")
                for i, r in enumerate(items, 1):
                    title = r['title'][:40] + ('...' if len(r['title']) > 40 else '')
                    report_lines.append(
                        f"| {i} | [{title}]({r['url']}) | {r['price']}₽ | "
                        f"{r['views_30d']} | {r['contacts_30d']} | {r['cvr']}% | {r['action']} |"
                    )
        
        report = "\n".join(report_lines)
        
        report_path = os.path.join(DATA_DIR, "AVITO_AUDIT_REPORT.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        log(f"📝 Отчёт сохранён: {report_path}")
        return report
    
    def run_full_audit(self):
        """Полный аудит: все 4 фазы."""
        log("🎯 АВИТОЛОГ v1.0 — Полный аудит Avito")
        log(f"   User ID: {AVITO_USER_ID}")
        log("")
        
        if not self.phase1_collect():
            return None
        self.phase2_analyze()
        self.phase3_audit()
        return self.phase4_report()


if __name__ == "__main__":
    agent = Avitolog()
    report = agent.run_full_audit()
    if report:
        print("\n" + "=" * 60)
        print(report)
