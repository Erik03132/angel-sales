## 🏁 2026-07-07 — AI-Eggs (IncuBird)

**Статус:** Voice Angela запущена, VPS `72.56.38.19` жив. Автообзвон через Mango.

**Ключевые компоненты:**
- `agent/voice_bridge.py` (voice-angela, PM2 id 21) — входящие звонки baresip
- `agent/angela_outbound.py` — исходящий обзвон + Битрикс
- Mango webhook `/opt/mango_webhook.py` (PM2 id 8)

**Стек:** OpenRouter DeepSeek → Qwen fallback. Gemini Kore TTS (через SOCKS5). Whisper STT.

**Проблемы:** Whisper hallucinates на тишине/автоответчиках. Авито ждёт OAuth2 токен.

**VPS:** `root@72.56.38.19`, 12 PM2 процессов.

**План на завтра:**
- Продолжить автообзвон
- Настроить Авито OAuth2
- Улучшить STT обработку (batch по raw WAV)
