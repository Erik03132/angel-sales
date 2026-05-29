// PM2 Ecosystem Configuration — Antigravity AI-EGGS
// Файл деплоится на VPS через deploy_to_vps.sh
// Управление: pm2 start ecosystem.config.js
//
// ОТКЛЮЧЕНО 2026-05-05: angela-scheduler и angela-autopilot УДАЛЕНЫ.
// Отчёты (daily_report, call_quality, project_report) отправляются
// ТОЛЬКО по запросу пользователя через ТГ-бота Анжелы.
module.exports = {
  apps: [
    {
      name: "angela-vk-bot",
      script: "vk_bot.py",
      interpreter: "/root/antigravity/ai-eggs/venv/bin/python3",
      cwd: "/root/antigravity/ai-eggs/agent",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "200M",
      // Restart policy: при краше ждём 5 секунд
      restart_delay: 5000,
      // Максимум 15 рестартов, потом стоп
      max_restarts: 15,
      // Переменные окружения
      env: {
        PYTHONUNBUFFERED: "1",
        TZ: "Europe/Moscow"
      },
      // Лог-файлы
      error_file: "/root/antigravity/ai-eggs/agent/logs/vk_bot_pm2_error.log",
      out_file: "/root/antigravity/ai-eggs/agent/logs/vk_bot_pm2_out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      // Ротация логов (макс 10MB)
      max_size: "10M",
      retain: 5
    }
  ]
};
