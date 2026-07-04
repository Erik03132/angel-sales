# CLAUDE.md — ai-eggs (Angela)

> Автогенерируемые правила на основе https://code.claude.com/docs/en/prompt-library

## Паттерны

### Plan before code
Всегда планируй перед редактированием кода.
Если задача > 5 файлов — сначала опиши план.

### Follow existing patterns
Копируй паттерны из angelochka_core.py:
- Tier routing (LITE/STD/PRO)
- FAQ caching (SmartFAQ)
- Prompt caching (cache_control: ephemeral)

### Turn corrections into rules
Если я纠错 — добавь правило сюда.

## Роли

- **CREATOR** — Игорь, создатель. Бро-режим, на "ты".
- **BOSS** — Андрей, руководитель. Уважительный тон, на "вы".
- **EMPLOYEE** — Коллега-менеджер. Равный тон.
- **CUSTOMER** — Клиент. Продажный пайплайн (5 шагов).

## Запреты

- НЕ выдумывай данные (цены, имена, статистику)
- НЕ автоматизируй написание кода (только советы)
- НЕ удаляй FAQ-эталоны без согласования
- НЕ изменяй tier routing без A/B теста

## Метрики

- Стоимость API: <$60/мес (цель)
- Качество ответов: >90% (цель)
- Предсказуемость: 70% workflow, 30% autonomous

## Источники

- Статья 1054436: https://habr.com/ru/companies/alpinadigital/articles/1054436/
- Prompt Library: https://code.claude.com/docs/en/prompt-library
- Building Effective Agents: https://www.anthropic.com/engineering/building-effective-agents
