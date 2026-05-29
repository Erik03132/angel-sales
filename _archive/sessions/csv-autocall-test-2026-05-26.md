# CSV → Autocall → STT → TG Report: Test Session

**Date:** 2026-05-26  
**Status:** 🟡 In Progress — STT detects, DTMF doesn't, report misses results

---

## What Works

### STT Classifier (dtmf_monitor.py on VPS)
- Priority-based classifier: explicit yes/no → negated confirmations → positive → other
- "Нет, нет, нет, нет, нет" → ✅ `cancelled`
- "Не подтверждаем" → ✅ `cancelled` (with `ж?` in regex)
- "Не подтвердал" (without ж) → ✅ `cancelled`

### VPS Services
| Service | Status | File |
|---------|--------|------|
| dtmf-monitor | ✅ online (52 restarts) | `/opt/dtmf_monitor.py` |
| dtmf-handler | ✅ online (12 restarts) | `/opt/dtmf_handler.py` |
| mango-webhook | ✅ online | `/opt/mango_webhook.py` |
| baresip (screen sip_bot) | ✅ | screen session |
| baresip-watchdog | ✅ | `/opt/baresip_watchdog.sh` |

### Bug Fixes Applied
1. **STT classifier** — `dtmf_monitor.py:83`: `не\s+(подтвержд?|...)` (ж optional)
2. **BrokenPipeError** — `dtmf_handler.py:397`: wrapped in try/except
3. **CSV path** — `dtmf_handler.py:94`: writes to `/opt/data/mango/call_results.csv`
4. **SSH cat** — `tg_bot.py:434`: reads both `/opt/data/mango/` and `/data/mango/`
5. **Wait → Poll** — `tg_bot.py:424`: polls CSV every 20s, max 3 min (was fixed 45s)

---

## What's Broken

### DTMF Not Detected by baresip
- User confirmed: call arrived, person spoke confirmation (said yes)
- dtmf-monitor detected NO DTMF → STT ran instead → unclear result
- baresip screen shows no `received event` line
- **Root cause unknown** — might be codec/DTMF transport issue

### Report Misses Results
- Even when STT works ("Нет, нет, нет"), report shows "STT не сработал"
- **Fixed but untested:** polling every 20s for 3 min (replaces 45s fixed wait)
- The polling fix should resolve this, but not verified yet

### angela-autopilot Conflicts
- **Fixed:** removed `angela-bot` from `bot_healthcheck.sh` loop → no more spamming
- `bot_healthcheck.sh` at `/root/antigravity/tools/bot_healthcheck.sh`

---

## Key Files

### Local (Mac)
| File | Purpose |
|------|---------|
| `tg_bot.py` | Telegram bot with CSV handler + autocall pipeline |
| `mango_autocall.py` | `make_call()` function |
| `.env` | Bot token: `ANGELOCHKA_BOT_TOKEN` |
| `/tmp/tg_bot_test.log` | Local bot startup log |

### VPS (72.56.38.19)
| File | Purpose |
|------|---------|
| `/opt/dtmf_monitor.py` | DTMF + STT monitor (screen parser) |
| `/opt/dtmf_handler.py` | HTTP handler, writes CSV |
| `/opt/data/mango/call_results.csv` | Call results (current) |
| `/data/mango/call_results.csv` | Call results (old path) |
| `/opt/mango_webhook.py` | Mango event webhook |
| `/root/antigravity/tools/bot_healthcheck.sh` | Every 15 min healthcheck |

---

## How to Resume

```bash
# 1. Clean old bot lock
rm -f /Users/igorvasin/freelance-2026/ai-eggs/logs/bot.lock

# 2. Start local bot
cd /Users/igorvasin/freelance-2026/ai-eggs/agent
source ../venv/bin/activate
nohup python3 -u tg_bot.py > /tmp/tg_bot_test.log 2>&1 &

# 3. Send CSV to @Angella26bot in Telegram
# 4. Check /opt/data/mango/call_results.csv on VPS for results
# 5. If DTMF still not detected → debug baresip codec/DTMF config
```

## Debug Commands

```bash
# Check VPS services
ssh root@72.56.38.19 'pm2 status'
# Check dtmf-monitor logs
ssh root@72.56.38.19 'pm2 logs dtmf-monitor --lines 20 --nostream'
# Check call results
ssh root@72.56.38.19 'cat /opt/data/mango/call_results.csv | tail -5'
# Check baresip screen
ssh root@72.56.38.19 'screen -S sip_bot -X hardcopy /tmp/baresip_screen.txt && cat /tmp/baresip_screen.txt'
# Check local bot log
cat /tmp/tg_bot_test.log | tail -20
```
