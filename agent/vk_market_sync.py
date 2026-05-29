#!/usr/bin/env python3
"""
VK Market Sync — Синхронизация товаров из unified_brain.json → ВК Магазин.

Использует новый VK API:
  1. market.getProductPhotoUploadServer → upload_url
  2. POST фото → upload response
  3. market.saveProductPhoto → photo_id
  4. market.add → товар в VK Market

Требования:
  - VK_VEZEMCYP_TOKEN (Community Token) в .env
  - Фото пород в vezem/dist/client/*.png
  - vk_api: pip install vk_api

Запуск: python3 vk_market_sync.py [--dry-run] [--limit N]
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# ═══════════════════════════════════════════════
# Настройка
# ═══════════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAIN_PATH = os.path.join(BASE_DIR, 'data', 'angelochka_unified_brain.json')
PHOTOS_DIR = os.path.join(BASE_DIR, 'vezem', 'dist', 'client')
SYNC_LOG_PATH = os.path.join(BASE_DIR, 'data', 'vk_market_sync_log.json')

# Загрузка .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)
except ImportError:
    # Ручная загрузка для VPS без dotenv
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    os.environ[k.strip()] = v.strip()

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [VK-MARKET] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('vk_market_sync')

# VK API
VK_TOKEN = os.getenv('VK_VEZEMCYP_TOKEN', '')  # Community token (для бота)
VK_USER_TOKEN = os.getenv('VK_USER_TOKEN', '')  # User token (для market.add)
VK_GROUP_ID = os.getenv('VK_VEZEMCYP_GROUP_ID', '').lstrip('-')
VK_API_VERSION = '5.199'
VK_API_BASE = 'https://api.vk.com/method'

# market.* методы требуют User Token!
MARKET_TOKEN = VK_USER_TOKEN or VK_TOKEN

# ═══════════════════════════════════════════════
# Маппинг пород → фото файлы
# ═══════════════════════════════════════════════

# Ключ — часть имени из brain (lowercase), значение — имя PNG файла
BREED_PHOTO_MAP = {
    'росс': 'ROSS308.png',
    'росс-308': 'ROSS308.png',
    'кобб': 'Kobb.png',
    'кобб-500': 'Kobb.png',
    'sasso': 'Sasso.png',
    'сассо': 'Sasso.png',
    'мастер грей': 'MasterGray.png',
    'мастер-грей': 'MasterGray.png',
    'ред бро': 'RedBro.png',
    'голошейка': 'Golosheika.png',
    'доминант д-104': 'DominantGold.png',
    'доминант д-107': 'DominantBlue.png',
    'доминант д-109': 'DominantBlack.png',
    'доминант д-102': 'DominantGreen.png',
    'доминант д-149': 'DominantSpeckled.png',
    'доминант': 'DominantGold.png',
    'ломан': 'Loman.png',
    'ломан браун': 'Loman.png',
    'хайсекс': 'Haiseks.png',
    'мулард': 'Mulard.png',
    'муллард': 'Mulard.png',
    'агидель': 'Agidel.png',
    'хайбрид': 'Big6.png',
    'биг-6': 'Big6.png',
    'биг 6': 'Big6.png',
    'губернатор': 'Governor.png',
    'итальянск': 'ItalianGoose.png',
    'холмогор': 'Kholmogory.png',
    'линда': 'Linda.png',
    'легарт': 'Legart.png',
    'леггорн': 'Leghorn.png',
    'адлер': 'Adler.png',
    'кучинская': 'Kuchinskaya.png',
    'бронзовая': 'Bronze.png',
    'бронз': 'Bronze.png',
    'конвертер': 'Konverter.png',
    'стар-53': 'Star53.png',
    'цесарка': 'Cesarka.png',
    'черри велли': 'CherryVelly.png',
    'черри-велли': 'CherryVelly.png',
    'мускусная': 'Myskus.png',
    'индоутка': 'Myskus.png',
    'декалб': 'DekalbWhite.png',
    'виктория': 'Victoria.png',
    'великан': 'Velikan.png',
    'голубой фаворит': 'BlueFavorit.png',
    'грейзбар': 'GREEZBAR.png',
}

# Категории ВК для market.add
VK_CATEGORY_ID = 1  # Общая категория (если не знаем точную)

# Шаблон описания товара
DESCRIPTION_TEMPLATE = """Суточный молодняк — {breed_name}.

🔹 Возраст: суточные (1 день)
🔹 Вакцинация: по возрасту
🔹 Гарантия выживаемости: 95%
🔹 Доставка: ЮФО, СКФО, Крым, Ростовская обл.
🔹 Минимальный заказ: от 50 голов
🔹 Бесплатная доставка от 500 голов

📞 Для уточнения цены и дат — напишите в сообщения сообщества.
🌐 Подробнее: vezemcip.ru"""


# ═══════════════════════════════════════════════
# HTTP helpers (stdlib only — без pip install)
# ═══════════════════════════════════════════════

def _multipart_upload(url, file_path, field_name='file', timeout=30):
    """Загрузка файла через multipart/form-data (только stdlib)."""
    import uuid
    boundary = uuid.uuid4().hex
    
    filename = os.path.basename(file_path)
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    # Формируем multipart body
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f'Content-Type: application/octet-stream\r\n'
        f'\r\n'
    ).encode('utf-8') + file_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
    
    req = urllib.request.Request(url, data=body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))

def vk_api_call(method, params=None, timeout=15, use_user_token=False):
    """Вызов VK API метода. use_user_token=True для market.* методов."""
    url = f"{VK_API_BASE}/{method}"
    token = MARKET_TOKEN if use_user_token else VK_TOKEN
    p = {
        'access_token': token,
        'v': VK_API_VERSION,
    }
    if params:
        p.update(params)
    
    encoded = urllib.parse.urlencode(p).encode('utf-8')
    req = urllib.request.Request(url, data=encoded)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        log.error("VK API %s: HTTP error: %s", method, e)
        return None
    
    if 'error' in data:
        err = data['error']
        log.error("VK API %s: [%s] %s", method, err.get('error_code'), err.get('error_msg'))
        return None
    
    return data.get('response')


def upload_market_photo(photo_path, group_id):
    """
    Загружает фото товара в VK Market.
    Возвращает photo_id или None.
    
    Алгоритм:
    1. market.getProductPhotoUploadServer → upload_url
    2. POST файл → upload_response
    3. market.saveProductPhoto → photo_id
    """
    # Шаг 1: Получить URL для загрузки
    result = vk_api_call('market.getProductPhotoUploadServer', {
        'group_id': group_id,
    }, use_user_token=True)
    if not result or 'upload_url' not in result:
        log.error("Не удалось получить upload_url для фото")
        return None
    
    upload_url = result['upload_url']
    
    # Шаг 2: Загрузить файл (multipart/form-data через urllib)
    try:
        upload_data = _multipart_upload(upload_url, photo_path)
    except Exception as e:
        log.error("Ошибка загрузки файла %s: %s", photo_path, e)
        return None
    
    if not upload_data or 'error' in str(upload_data).lower():
        log.error("Upload failed: %s", upload_data)
        return None
    
    # Шаг 3: Сохранить фото
    save_result = vk_api_call('market.saveProductPhoto', {
        'upload_response': json.dumps(upload_data),
    }, use_user_token=True)
    
    if save_result and 'photo_id' in save_result:
        photo_id = save_result['photo_id']
        log.info("📸 Фото загружено: photo_id=%s (%s)", photo_id, os.path.basename(photo_path))
        return photo_id
    
    log.error("Не удалось сохранить фото: %s", save_result)
    return None


# ═══════════════════════════════════════════════
# Поиск фото для породы
# ═══════════════════════════════════════════════

def find_photo_for_breed(breed_name):
    """Находит файл фото для породы из маппинга."""
    breed_lower = breed_name.lower().strip()
    
    # Точное совпадение
    for key, filename in BREED_PHOTO_MAP.items():
        if key in breed_lower:
            path = os.path.join(PHOTOS_DIR, filename)
            if os.path.exists(path):
                return path
    
    # Fallback — ищем по первому слову
    first_word = breed_lower.split()[0] if breed_lower else ''
    for key, filename in BREED_PHOTO_MAP.items():
        if first_word and first_word in key:
            path = os.path.join(PHOTOS_DIR, filename)
            if os.path.exists(path):
                return path
    
    return None


# ═══════════════════════════════════════════════
# Парсинг brain → список товаров
# ═══════════════════════════════════════════════

def parse_products_from_brain():
    """Парсит unified_brain.json → список товаров для VK Market."""
    if not os.path.exists(BRAIN_PATH):
        log.error("Brain не найден: %s", BRAIN_PATH)
        return []
    
    with open(BRAIN_PATH, 'r', encoding='utf-8') as f:
        brain = json.load(f)
    
    products = []
    seen_names = set()
    
    for item in brain:
        content = item.get('content', '')
        metadata = item.get('metadata', {})
        
        if metadata.get('type') != 'product':
            continue
        
        # Парсим "Название — Цена₽"
        if '—' in content:
            name_part, price_part = content.split('—', 1)
            name = name_part.strip()
            # Извлекаем цену
            price_str = price_part.strip().replace('₽', '').replace(' ', '')
            # Обрабатываем доп. инфо после цены
            if ',' in price_str:
                price_str = price_str.split(',')[0]
            try:
                price = float(price_str)
            except ValueError:
                price = 0
        elif '–' in content:
            name_part, price_part = content.split('–', 1)
            name = name_part.strip()
            try:
                price = float(price_part.strip().replace('₽', '').replace(' ', '').split(',')[0])
            except ValueError:
                price = 0
        else:
            name = content.strip()
            price = 0
        
        # Дедупликация по имени
        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        
        # Формируем VK-совместимое название (макс 100 символов)
        vk_name = f"Цыплята {name} суточные" if len(name) < 80 else name
        if len(vk_name) > 100:
            vk_name = vk_name[:97] + '...'
        
        # Описание
        description = DESCRIPTION_TEMPLATE.format(breed_name=name)
        
        # Поиск фото
        photo_path = find_photo_for_breed(name)
        
        products.append({
            'name': vk_name,
            'original_name': name,
            'description': description,
            'price': price,
            'photo_path': photo_path,
            'brain_id': item.get('id', ''),
        })
    
    return products


# ═══════════════════════════════════════════════
# Получение существующих товаров из VK
# ═══════════════════════════════════════════════

def get_existing_vk_products():
    """Получает список уже существующих товаров в VK Market."""
    all_products = []
    offset = 0
    
    while True:
        result = vk_api_call('market.get', {
            'owner_id': f'-{VK_GROUP_ID}',
            'count': 200,
            'offset': offset,
        }, use_user_token=True)
        
        if not result:
            break
        
        items = result.get('items', [])
        if not items:
            break
        
        all_products.extend(items)
        offset += len(items)
        
        if offset >= result.get('count', 0):
            break
    
    return all_products


# ═══════════════════════════════════════════════
# Создание товара в VK Market
# ═══════════════════════════════════════════════

def create_vk_product(product, dry_run=False):
    """Создаёт один товар в VK Market."""
    name = product['name']
    
    if dry_run:
        photo_info = "📸 " + os.path.basename(product['photo_path']) if product['photo_path'] else "❌ нет фото"
        log.info("[DRY-RUN] %s | %.0f₽ | %s", name, product['price'], photo_info)
        return {'dry_run': True, 'name': name}
    
    # Загружаем фото (VK ТРЕБУЕТ main_photo_id — без фото товар не создать)
    photo_id = None
    if product['photo_path']:
        photo_id = upload_market_photo(product['photo_path'], VK_GROUP_ID)
        if not photo_id:
            log.warning("⚠️ Фото не загружено для %s — ПРОПУСК (VK требует фото)", name)
            return None
        time.sleep(0.5)  # Rate limit
    else:
        log.warning("⚠️ Нет фото для %s — ПРОПУСК (VK требует main_photo_id)", name)
        return None
    
    # Создаём товар
    params = {
        'owner_id': f'-{VK_GROUP_ID}',
        'name': name,
        'description': product['description'],
        'category_id': VK_CATEGORY_ID,
        'price': str(product['price']) if product['price'] > 0 else '0',
        'url': 'https://vezemcip.ru',
    }
    
    if photo_id:
        params['main_photo_id'] = photo_id
    
    result = vk_api_call('market.add', params, use_user_token=True)
    
    if result:
        market_item_id = result.get('market_item_id') or result
        log.info("✅ Создан: %s (market_id=%s)", name, market_item_id)
        return {
            'name': name,
            'market_item_id': market_item_id,
            'photo_id': photo_id,
        }
    
    log.error("❌ Не удалось создать: %s", name)
    return None


# ═══════════════════════════════════════════════
# Основной sync
# ═══════════════════════════════════════════════

def sync_products(dry_run=False, limit=None):
    """Основная функция синхронизации."""
    log.info("=" * 50)
    log.info("🔄 VK Market Sync — Старт")
    log.info("   Group ID: %s", VK_GROUP_ID)
    log.info("   Brain: %s", BRAIN_PATH)
    log.info("   Photos: %s", PHOTOS_DIR)
    log.info("   Dry run: %s", dry_run)
    log.info("=" * 50)
    
    # 1. Парсим brain
    products = parse_products_from_brain()
    log.info("📦 Из brain: %d уникальных товаров", len(products))
    
    with_photo = sum(1 for p in products if p['photo_path'])
    log.info("📸 С фото: %d / %d", with_photo, len(products))
    
    # 2. Проверяем существующие в VK
    if not dry_run:
        existing = get_existing_vk_products()
        existing_names = {p['title'].lower() for p in existing}
        log.info("🛍 В VK Market: %d товаров", len(existing))
    else:
        existing_names = set()
    
    # 3. Фильтруем — только новые
    to_create = []
    for p in products:
        if p['name'].lower() not in existing_names:
            to_create.append(p)
    
    log.info("🆕 Новых для создания: %d", len(to_create))
    
    if limit:
        to_create = to_create[:limit]
        log.info("📏 Лимит: %d", limit)
    
    # 4. Создаём
    results = []
    for i, product in enumerate(to_create, 1):
        log.info("--- [%d/%d] ---", i, len(to_create))
        result = create_vk_product(product, dry_run=dry_run)
        if result:
            results.append(result)
        
        if not dry_run:
            time.sleep(1)  # VK rate limit: 3 req/sec, но лучше не рисковать
    
    # 5. Сохраняем лог
    sync_log = {
        'timestamp': datetime.now().isoformat(),
        'total_in_brain': len(products),
        'with_photo': with_photo,
        'created': len(results),
        'dry_run': dry_run,
        'items': results,
    }
    
    os.makedirs(os.path.dirname(SYNC_LOG_PATH), exist_ok=True)
    with open(SYNC_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(sync_log, f, ensure_ascii=False, indent=2)
    
    log.info("=" * 50)
    log.info("✅ Sync завершён: %d товаров создано", len(results))
    log.info("   Лог: %s", SYNC_LOG_PATH)
    log.info("=" * 50)
    
    return results


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VK Market Sync — загрузка товаров из brain в VK')
    parser.add_argument('--dry-run', action='store_true', help='Показать что будет создано, без реальных вызовов')
    parser.add_argument('--limit', type=int, default=None, help='Максимум товаров для создания')
    args = parser.parse_args()
    
    if not VK_TOKEN:
        log.error("❌ VK_VEZEMCYP_TOKEN не найден в .env!")
        sys.exit(1)
    if not VK_GROUP_ID:
        log.error("❌ VK_VEZEMCYP_GROUP_ID не найден в .env!")
        sys.exit(1)
    
    sync_products(dry_run=args.dry_run, limit=args.limit)
