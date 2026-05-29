// PM2 Ecosystem Configuration — AI-EGGS
// Деплоится на VPS через deploy_to_vps.sh
// Управление: pm2 start ecosystem.config.cjs
//
// АРХИТЕКТУРА (обновлено 02.05.2026):
// Только angela-bot — AI-продавец 24/7 на сайте + TG
// scheduler, autopilot, server — ОСТАНОВЛЕНЫ навсегда.
module.exports = {
  apps: [
    {
      name: "angela-bot",
      script: "tg_bot.py",
      interpreter: "/root/antigravity/ai-eggs/venv/bin/python3",
      cwd: "/root/antigravity/ai-eggs/agent",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,        // ← автоподъём при крэше
      watch: false,
      max_memory_restart: "300M",
      restart_delay: 5000,      // ← 5 сек пауза между рестартами
      max_restarts: 50,         // ← 50 попыток (бот критичен)
      env: {
        PYTHONUNBUFFERED: "1",
        TZ: "Europe/Moscow"
      },
      error_file: "/root/antigravity/ai-eggs/agent/logs/bot_pm2_error.log",
      out_file: "/root/antigravity/ai-eggs/agent/logs/bot_pm2_out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      max_size: "10M",
      retain: 5
    }
  ]
};
