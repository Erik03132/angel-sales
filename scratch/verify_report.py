import os
import sys
from datetime import datetime

# Настройка путей
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "agent"))

from angelochka_core import get_dynamic_crm_report

print(f"--- TESTING DYNAMIC REPORT AT {datetime.now()} ---")
report = get_dynamic_crm_report()
print(report)
print("--- END OF REPORT ---")
