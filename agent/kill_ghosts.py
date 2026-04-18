import psutil
import os

print("PID: name (cmdline)")
killed = 0
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if p.info['cmdline'] and 'tg_bot.py' in ' '.join(p.info['cmdline']):
            print(f"Killing {p.info['pid']}: {p.info['cmdline']}")
            p.kill()
            killed += 1
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

print(f"Killed {killed} ghost processes.")
