#!/usr/bin/env python3
"""
call_daily_summary.py — Блок сводки по звонкам для /daily в боте.
Читает call_learnings/YYYY-MM-DD.json (вчера) и возвращает
краткую markdown-сводку для Telegram.

Вызывается из tg_bot.py в cmd_daily как дополнительный блок.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR   = SCRIPT_DIR.parent
LEARNING_DIR = BASE_DIR / "data" / "call_learnings"
TRANSCRIPT_DIR = BASE_DIR / "data" / "transcripts"
MSK = timezone(timedelta(hours=3))


def get_call_summary(date_str: str | None = None) -> str:
    """
    Возвращает краткую сводку по звонкам за дату (default: вчера).
    Формат: Telegram markdown (без parse_mode=HTML).
    """
    if date_str is None:
        yesterday = datetime.now(MSK) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    learning_file = LEARNING_DIR / f"{date_str}.json"
    transcript_dir = TRANSCRIPT_DIR / date_str

    # === Подсчёт транскриптов ===
    total_calls = 0
    incoming = 0
    outgoing = 0
    with_agreements = 0
    durations = []

    if transcript_dir.exists():
        for f in transcript_dir.glob("call_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                total_calls += 1
                d = data.get("direction", "")
                if d == "incoming":
                    incoming += 1
                elif d == "outgoing":
                    outgoing += 1
                if data.get("agreements"):
                    with_agreements += 1
                dur = data.get("duration_sec", 0)
                if dur:
                    durations.append(dur)
            except Exception:
                pass

    # === Факты из call_learner ===
    facts = {}
    if learning_file.exists():
        try:
            facts = json.loads(learning_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    prices   = facts.get("prices", [])
    hatch    = facts.get("hatch_dates", [])
    logistics = facts.get("logistics", [])
    popular  = facts.get("popular_breeds", [])
    issues   = facts.get("issues", [])

    # === Формируем текст ===
    if total_calls == 0 and not facts:
        return f"📞 Звонки за {date_str}: нет данных"

    avg_dur = round(sum(durations) / len(durations)) if durations else 0
    pct_agr = round(with_agreements / total_calls * 100) if total_calls else 0

    lines = [f"📞 *Звонки за {date_str}*\n"]

    # Статистика
    lines.append(
        f"Всего: *{total_calls}* (📥{incoming} вх / 📤{outgoing} исх) | "
        f"Договорённостей: *{with_agreements} ({pct_agr}%)* | "
        f"Ср. длит: *{avg_dur//60}:{avg_dur%60:02d}*"
    )

    # Топ пород
    if popular:
        top = popular[:5]
        breeds_str = ", ".join(f"{p['breed']} ({p['mention_count']})" for p in top)
        lines.append(f"\n🐔 *Топ запросов:* {breeds_str}")

    # Ближайшие выводы
    if hatch:
        lines.append("\n📅 *Ближайшие выводы:*")
        seen_dates = {}
        for h in hatch:
            date = h.get("date", "")
            breed = h.get("breed", "")
            if date not in seen_dates:
                seen_dates[date] = []
            seen_dates[date].append(breed)
        for dt, breeds in sorted(seen_dates.items())[:5]:
            lines.append(f"  • {dt}: {', '.join(breeds[:3])}")

    # Цены
    if prices:
        lines.append("\n💰 *Цены из звонков:*")
        for p in prices[:4]:
            lines.append(f"  • {p.get('breed','?')} — {p.get('price','?')}₽ ({p.get('context','')})")

    # Логистика сегодня
    today_str = datetime.now(MSK).strftime("%Y-%m-%d")
    today_logistics = [l for l in logistics if today_str in l.get("schedule", "")]
    if today_logistics:
        lines.append("\n🚚 *Доставки сегодня:*")
        for l in today_logistics[:3]:
            lines.append(f"  • {l.get('location','?')}: {l.get('details','')[:60]}")

    # Проблемы
    if issues:
        lines.append("\n⚠️ *Требует внимания:*")
        for issue in issues[:3]:
            lines.append(f"  • {issue[:80]}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    print(get_call_summary(date))
