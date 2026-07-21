#!/usr/bin/env python3
"""sync_autodial_to_bitrix.py — записывает результаты автодозвона в Битрикс (комментарий + поле)."""
import os, requests, json, time
from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=True)
for v in ("HTTPS_PROXY","HTTP_PROXY","ALL_PROXY","https_proxy","http_proxy","all_proxy"):
    os.environ.pop(v, None)

BX = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL","").rstrip("/")

# Enum IDs для UF_CRM_AUTODIAL_RESULT
ENUM = {
    "confirmed": 1146,
    "cancelled": 1148,
    "no_answer": 1150,
    "unclear": 1152,
    "unavailable": 1154,
}

STATUS_LABELS = {
    "confirmed": "✅ Подтвердил",
    "cancelled": "❌ Отказал",
    "no_answer": "📵 Не ответил",
    "unclear": "❓ Неразборчиво",
    "unavailable": "🚫 Недоступен",
}

# === Результаты обзвона 12.06.2026 ===
RESULTS = {
    # Пакет #01 - Подтвердили
    "79780472328": {"status": "confirmed", "stt": "Да, девочки. Алло."},
    "79900285370": {"status": "confirmed", "stt": "Да."},
    # Пакет #01 - Отказали
    "79900253251": {"status": "cancelled", "stt": "Нет. Нет. Нет. Нет."},
    "79782135785": {"status": "cancelled", "stt": "Нет."},
    # Пакет #01 - Неразборчиво (сняли трубку)
    "79882450770": {"status": "unclear", "stt": "на линии."},
    "79518442665": {"status": "unclear", "stt": "автоответчик"},
    "79887655787": {"status": "unclear", "stt": "Алло!"},
    "79787919899": {"status": "unclear", "stt": ""},
    "79780402144": {"status": "unclear", "stt": "Алло! Алло!"},
    "79809077038": {"status": "unclear", "stt": "голосовой ассистент"},
    "79787895963": {"status": "unclear", "stt": "музыка ожидания"},
    "79788129014": {"status": "unclear", "stt": ""},
    "79054710100": {"status": "unclear", "stt": "Не ещё что-нибудь передать."},
    "79780659583": {"status": "unclear", "stt": "Алло!"},
    # Пакет #01 - Не ответили
    "79289883569": {"status": "no_answer"}, "79892841625": {"status": "no_answer"},
    "79787756299": {"status": "no_answer"}, "79281692391": {"status": "no_answer"},
    "79788603825": {"status": "no_answer"}, "79787728865": {"status": "no_answer"},
    "79189409596": {"status": "no_answer"}, "79054040717": {"status": "no_answer"},
    "79788727422": {"status": "no_answer"}, "79787801072": {"status": "no_answer"},
    "79782705854": {"status": "no_answer"}, "79787743464": {"status": "no_answer"},
    "79785925921": {"status": "no_answer"}, "79788142616": {"status": "no_answer"},
    "79787274973": {"status": "no_answer"}, "79780501475": {"status": "no_answer"},
    "79787910059": {"status": "no_answer"}, "79189812004": {"status": "no_answer"},
    "79788624613": {"status": "no_answer"}, "79185249699": {"status": "no_answer"},
    "79782934053": {"status": "no_answer"}, "79787020843": {"status": "no_answer"},
    "79781420393": {"status": "no_answer"}, "79900451752": {"status": "no_answer"},
    "79182488378": {"status": "no_answer"}, "79010148309": {"status": "no_answer"},
    "79515596860": {"status": "no_answer"}, "79787710706": {"status": "no_answer"},
    "79996976619": {"status": "no_answer"}, "79508588089": {"status": "no_answer"},
    "79284052889": {"status": "no_answer"},
    # Пакет #01 - Недоступен
    "79783176393": {"status": "unavailable"}, "79781918120": {"status": "unavailable"},
    "79782847410": {"status": "unavailable"},
    # Пакет #02 - Подтвердили
    "79494210798": {"status": "confirmed", "stt": "Да, я заказывал инди-коп."},
    "79780521470": {"status": "confirmed", "stt": "DTMF 1"},
    "79298424537": {"status": "confirmed", "stt": "DTMF 1"},
    "79781486828": {"status": "confirmed", "stt": "DTMF 1"},
    "79507699810": {"status": "confirmed", "stt": "DTMF 1"},
    # Пакет #02 - Отказали
    "79788204669": {"status": "cancelled", "stt": "Нет. Нет."},
    "79782181334": {"status": "cancelled", "stt": "Нет"},
    "79785622457": {"status": "cancelled", "stt": "Нет."},
    "79780662548": {"status": "cancelled", "stt": "Нет. Нет."},
    "79883455246": {"status": "cancelled", "stt": "Нет."},
    # Пакет #02 - Неразборчиво
    "79189214384": {"status": "unclear", "stt": ""},
    "79788343810": {"status": "unclear", "stt": ""},
    "79788768816": {"status": "unclear", "stt": ""},
    "79785945384": {"status": "unclear", "stt": "Взрак!"},
    "79788134978": {"status": "unclear", "stt": "Алло!"},
    "79184635506": {"status": "unclear", "stt": "музыка ожидания"},
    "79064265862": {"status": "unclear", "stt": ""},
    # Пакет #02 - Не ответили
    "79785167402": {"status": "no_answer"}, "79788736872": {"status": "no_answer"},
    "79787269365": {"status": "no_answer"}, "79788988215": {"status": "no_answer"},
    "79786439390": {"status": "no_answer"}, "79900008254": {"status": "no_answer"},
    "79202188309": {"status": "no_answer"}, "79515643661": {"status": "no_answer"},
    "79785065082": {"status": "no_answer"}, "79782915237": {"status": "no_answer"},
    "79613292483": {"status": "no_answer"}, "79782802474": {"status": "no_answer"},
    "79787173559": {"status": "no_answer"}, "79786184312": {"status": "no_answer"},
    "79780320199": {"status": "no_answer"}, "79787873276": {"status": "no_answer"},
    "79490661468": {"status": "no_answer"}, "79787158218": {"status": "no_answer"},
    "79788485412": {"status": "no_answer"}, "79788669501": {"status": "no_answer"},
    "79085050438": {"status": "no_answer"}, "79591042163": {"status": "no_answer"},
    "79900007895": {"status": "no_answer"}, "79781064333": {"status": "no_answer"},
    "79787139226": {"status": "no_answer"},
    # Пакет #02 - Недоступен
    "79789252827": {"status": "unavailable"}, "79900258013": {"status": "unavailable"},
    "79781271569": {"status": "unavailable"}, "79788414674": {"status": "unavailable"},
    "79785031877": {"status": "unavailable"}, "79786567881": {"status": "unavailable"},
    "79900311084": {"status": "unavailable"},
}

def find_contact(phone):
    """Найти контакт по телефону."""
    r = requests.post(BX + "/crm.duplicate.findbycomm", json={
        "type": "PHONE",
        "values": [phone],
        "entity_type": "CONTACT"
    }, timeout=30)
    data = r.json().get("result", {})
    ids = data.get("CONTACT", [])
    return ids[0] if ids else None

def add_comment(entity_type, entity_id, text):
    """Добавить комментарий в таймлайн."""
    r = requests.post(BX + "/crm.timeline.comment.add", json={
        "fields": {
            "ENTITY_ID": entity_id,
            "ENTITY_TYPE": entity_type,
            "COMMENT": text,
        }
    }, timeout=30)
    return r.json()

def update_field(contact_id, enum_id):
    """Обновить поле UF_CRM_AUTODIAL_RESULT."""
    r = requests.post(BX + "/crm.contact.update", json={
        "id": contact_id,
        "fields": {"UF_CRM_AUTODIAL_RESULT": enum_id}
    }, timeout=30)
    return r.json()

# === MAIN ===
print("=" * 60)
print("Синхронизация автодозвона 12.06.2026 → Битрикс24")
print("=" * 60)

stats = {"found": 0, "not_found": 0, "updated": 0, "errors": 0}

for phone, info in RESULTS.items():
    status = info["status"]
    stt = info.get("stt", "")
    
    # Формат телефона для поиска
    phone_search = phone
    if not phone_search.startswith("+"):
        phone_search = "+" + phone_search
    if phone_search.startswith("+7"):
        pass
    
    # Ищем контакт
    contact_id = find_contact(phone_search)
    if not contact_id:
        # Попробуем без +
        contact_id = find_contact(phone)
    
    if not contact_id:
        stats["not_found"] += 1
        print(f"  ✗ {phone} — контакт не найден")
        continue
    
    stats["found"] += 1
    
    # Формируем комментарий
    label = STATUS_LABELS.get(status, status)
    comment = f"📞 Автодозвон 12.06.2026\nИндюшата Хайбрид конвертер, Канада — доставка 26 июля\n\nРезультат: {label}"
    if stt:
        comment += f"\nОтвет: «{stt}»"
    
    # Добавляем комментарий
    try:
        add_comment("contact", contact_id, comment)
    except Exception as e:
        print(f"  ⚠ {phone} comment error: {e}")
    
    # Обновляем поле
    enum_id = ENUM.get(status)
    if enum_id:
        try:
            update_field(contact_id, enum_id)
            stats["updated"] += 1
        except Exception as e:
            stats["errors"] += 1
            print(f"  ⚠ {phone} field error: {e}")
    
    print(f"  ✓ {phone} → контакт #{contact_id} — {label}")
    time.sleep(0.3)  # rate limit

print(f"\n{'=' * 60}")
print(f"Готово!")
print(f"  Найдено контактов: {stats['found']}")
print(f"  Не найдено: {stats['not_found']}")
print(f"  Обновлено полей: {stats['updated']}")
print(f"  Ошибок: {stats['errors']}")
