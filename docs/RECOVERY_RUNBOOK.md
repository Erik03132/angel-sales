# 🛠️ RUNBOOK: Восстановление сервера 72.56.38.19 (Timeweb, аккаунт wy07319)

**Контекст (2026-07-18):** сервер был отключён за неуплату, IP мог уйти
другому клиенту. Поддержка Timeweb (ticket открыт) должна восстановить
сервер. После восстановления пройти чек-лист ниже.

**Аккаунт панели:** `wy07319` / `Incubator2026` (Timeweb Cloud).
**Старый root-пароль** `zE4qDJb-+Y+rv+` и старый SSH-ключ `antigravity_agent`
скорее всего НЕ подойдут на восстановленном сервере — их нужно переустановить.

---

## 🔑 ШАГ 0 — Получить доступ (через панель Timeweb, НЕ через SSH)

1. Зайти в https://timeweb.cloud → аккаунт `wy07319`.
2. Найти сервер → статус должен стать «Запущен» (после ответа поддержки).
3. **Сбросить пароль root** через кнопку в панели (запомнить новый).
   ИЛИ
4. **Добавить SSH-ключ** в раздел «SSH-ключи» сервера, вставить:
   ```
   ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFnviTWgJhEPSPsTWyH4qHFs8ixkO/5KDmY7jZMxtDwe antigravity_agent
   ```
5. Проверить доступ:
   ```bash
   ssh -o StrictHostKeyChecking=accept-new root@72.56.38.19 'echo OK; uptime'
   ```
   Если пароль — `sshpass -p '<NEWPASS>' ssh ...`.

⚠️ **ВАЖНО:** при первом подключении host key изменится. Скопировать
новый отпечаток и ОБНОВИТЬ known_hosts локально:
   ```bash
   ssh-keygen -R 72.56.38.19
   ```

---

## 🌐 ШАГ 1 — Проверить сайт vezemcip.ru (Laravel, nginx)

Сайт — ОТДЕЛЬНЫЙ сервис (Laravel «sk_sokol»), не PM2-агенты.

1. HTTP отвечает?
   ```bash
   curl -s -o /dev/null -w "HTTP %{http_code}\n" http://vezemcip.ru/
   ```
2. nginx + PHP-FPM живы?
   ```bash
   ssh root@72.56.38.19 'systemctl status nginx --no-pager; systemctl status php*-fpm --no-pager'
   ```
3. Если упали — поднять:
   ```bash
   ssh root@72.56.38.19 'systemctl start nginx; systemctl start php8.*-fpm'
   ```
4. Проверить права на storage (Laravel-специфика):
   ```bash
   ssh root@72.56.38.19 'chown -R www-data:www-data /var/www/*/storage; chmod -R 775 /var/www/*/storage'
   ```
5. Если сайт НЕ поднялся после восстановления (диск сброшен) —
   восстановить из бэкапа панели Timeweb («Снапшоты» / «Бэкапы»).

---

## 🤖 ШАГ 2 — Поднять ботов (PM2)

Код лежит в `/root/antigravity/ai-eggs/agent/`.

1. Синхронизировать свежий код + .env (если сервер «чистый» после восстановления):
   ```bash
   bash projects/ai-eggs/agent/deploy_to_vps.sh
   ```
2. Запустить всё через универсальный воскрешатель:
   ```bash
   ssh root@72.56.38.19 'bash /root/antigravity/ai-eggs/resurrect.sh'
   ```
   Он проверит PM2, создаст `.cjs`, запустит ecosystem, сделает `pm2 save`.
3. Проверить статус:
   ```bash
   ssh root@72.56.38.19 'pm2 list'
   ```
   Ожидаемые процессы: `angela-bot`, `angela-vk-bot`, `a2a-dispatcher`,
   `a2a-autopilot`, `mango-webhook` (id 8), `voice-angela` (id 21).

---

## 🔌 ШАГ 3 — Боты на портах 8085 / 8086 (Mango DTMF)

Эти порты были закрыты — значит mango-webhook и dtmf-handler не запущены.

1. mango-webhook (регистрация звонков):
   ```bash
   ssh root@72.56.38.19 'pm2 restart mango-webhook || pm2 start /opt/mango_webhook.py --name mango-webhook --interpreter /root/antigravity/ai-eggs/venv/bin/python3'
   ```
2. dtmf handler (порт 8086):
   ```bash
   ssh root@72.56.38.19 'bash /root/antigravity/ai-eggs/tools/setup_dtmf_vps.sh'
   ```
3. Проверить порты:
   ```bash
   for p in 8085 8086 80 443; do nc -z -w 3 72.56.38.19 $p && echo "port $p OPEN" || echo "port $p closed"; done
   ```

---

## ✅ ШАГ 4 — Финальная проверка

- [ ] `curl http://vezemcip.ru/` → HTTP 200
- [ ] `pm2 list` → все процессы `online`
- [ ] Порты 8085, 8086 открыты
- [ ] Angela отвечает в Telegram (@Angella26bot)
- [ ] Mango входящие звонки регистрируются
- [ ] `pm2 save` выполнен (автозапуск после reboot)

---

## 🧯 Если сервер НЕ удалось восстановить (удалён)

1. Создать НОВЫЙ сервер в `wy07319`.
2. Перенести код: `bash agent/deploy_to_vps.sh` (обновить IP в скрипте).
3. Восстановить сайт из снапшота/бэкапа панели.
4. Обновить DNS `vezemcip.ru` (NS `ns17/ns18.hostia.name` → REGTIME) на НОВЫЙ IP.
5. Добавить SSH-ключ `antigravity_agent`, прописать новый IP в `.env`.

---

## 📌 Доступы (сохранены в projects/ai-eggs/.env)

| Что | Значение |
|-----|----------|
| Timeweb Cloud аккаунт | `wy07319` / `Incubator2026` |
| VPS IP | `72.56.38.19` |
| VPS user | `root` |
| Старый пароль root | `zE4qDJb-+Y+rv+` (может не подойти) |
| SSH-ключ (local) | `.ssh_agent_key` → `antigravity_agent` |
| Домен | `vezemcip.ru` (NS hostia.name, REGTIME, оплачен до 2026-10-07) |
| Сайт | Laravel «sk_sokol» на nginx (порт 80) |
