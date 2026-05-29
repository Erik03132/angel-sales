"""Тест: транскрипция одного самого длинного звонка за 3 дня."""
import json, requests, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env', override=True)
BITRIX_URL = (os.getenv('PRODUCTION_BITRIX_WEBHOOK_URL') or os.getenv('BITRIX_WEBHOOK_URL', '')).rstrip('/')
GEMINI_KEY = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY', '')
MSK = timezone(timedelta(hours=3))

print(f"Bitrix: {BITRIX_URL[:50]}...")
print(f"Gemini key: {'OK' if GEMINI_KEY else '❌ НЕТ'}\n")

# 1. Берём звонки за 3 дня
since = (datetime.now(MSK) - timedelta(days=3)).strftime('%Y-%m-%dT00:00:00')
resp = requests.get(f'{BITRIX_URL}/voximplant.statistic.get',
    params={'FILTER[>=CALL_START_DATE]': since}, timeout=60)
calls = resp.json().get('result', [])

with_rec = [c for c in calls if c.get('RECORD_FILE_ID') and int(c.get('CALL_DURATION', 0)) > 30]
best = sorted(with_rec, key=lambda x: int(x['CALL_DURATION']), reverse=True)[0]

dur = int(best['CALL_DURATION'])
print(f"Выбран звонок:")
print(f"  ID: {best['ID']}")
print(f"  Дата: {best['CALL_START_DATE']}")
print(f"  Телефон: {best['PHONE_NUMBER']}")
print(f"  Длительность: {dur//60}:{dur%60:02d}")
print(f"  RECORD_FILE_ID: {best['RECORD_FILE_ID']}\n")

# 2. Получаем download URL
r = requests.get(f'{BITRIX_URL}/disk.file.get.json',
    params={'id': best['RECORD_FILE_ID']}, timeout=30)
url = r.json().get('result', {}).get('DOWNLOAD_URL', '')
print(f"Download URL: ...{url[-40:]}\n")

# 3. Скачиваем MP3
print("Скачиваю MP3...")
resp2 = requests.get(url, timeout=60, stream=True)
tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
for chunk in resp2.iter_content(8192):
    tmp.write(chunk)
tmp.close()
size_kb = os.path.getsize(tmp.name) / 1024
print(f"Скачано: {size_kb:.0f} KB\n")

# 4. Gemini Flash (новый SDK google-genai)
print("Отправляю в Gemini Flash...")
from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_KEY)

SYSTEM = """Ты — аналитик звонков птицеводческого хозяйства «ВезёмЦыплят» (Крым).
Обработай запись звонка и верни ТОЛЬКО JSON без markdown-обёрток:
{
  "transcript": "МЕНЕДЖЕР: ...\nКЛИЕНТ: ...",
  "summary": "2-3 предложения о чём звонок",
  "client_questions": ["вопрос 1", "вопрос 2"],
  "agreements": ["договорённость 1"],
  "manager_score": {
    "total": 3,
    "named_self": true,
    "asked_city": false,
    "gave_price_scale": true,
    "offered_upsell": false,
    "set_next_step": false
  }
}
Язык: только русский."""

direction = 'входящий' if str(best.get('CALL_TYPE')) == '2' else 'исходящий'
user_msg = f"Тип: {direction}, тел: {best['PHONE_NUMBER']}, длит: {dur//60}:{dur%60:02d}"

with open(tmp.name, 'rb') as f:
    audio_bytes = f.read()

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[
        types.Content(parts=[
            types.Part(text=SYSTEM + "\n\n" + user_msg),
            types.Part(inline_data=types.Blob(mime_type='audio/mp3', data=audio_bytes)),
        ])
    ],
)
os.unlink(tmp.name)

raw = response.text.strip()

# Чистим от markdown если есть
if '```json' in raw:
    raw = raw.split('```json')[1].split('```')[0].strip()
elif '```' in raw:
    raw = raw.split('```')[1].split('```')[0].strip()

print(f"Ответ Gemini ({len(raw)} символов):\n{raw[:300]}...\n")

# 5. Парсим и сохраняем
result = json.loads(raw)

out_dir = Path(__file__).parent.parent / 'data' / 'transcripts' / best['CALL_START_DATE'][:10]
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / f"call_{best['ID']}.json"

record = {**best, **result, 'processed_at': datetime.now(MSK).isoformat()}
with open(out_file, 'w', encoding='utf-8') as f:
    json.dump(record, f, ensure_ascii=False, indent=2)

# 6. Выводим результат
print('=' * 55)
print(f"✅ СОХРАНЕНО: {out_file}")
print()
print(f"📝 САММАРИ:")
print(f"   {result.get('summary', '')}")
print()
print(f"❓ ВОПРОСЫ КЛИЕНТА:")
for q in result.get('client_questions', []):
    print(f"   - {q}")
print()
print(f"🤝 ДОГОВОРЁННОСТИ:")
for a in result.get('agreements', []):
    print(f"   - {a}")
print()
score = result.get('manager_score', {})
print(f"⭐ ОЦЕНКА МЕНЕДЖЕРА: {score.get('total', '?')}/5")
print(f"   Назвал себя:     {'✅' if score.get('named_self') else '❌'}")
print(f"   Спросил город:   {'✅' if score.get('asked_city') else '❌'}")
print(f"   Цена со шкалой:  {'✅' if score.get('gave_price_scale') else '❌'}")
print(f"   Предложил доп.:  {'✅' if score.get('offered_upsell') else '❌'}")
print(f"   Следующий шаг:   {'✅' if score.get('set_next_step') else '❌'}")
print()
print(f"📄 ТРАНСКРИПТ:")
print(result.get('transcript', '')[:800])
