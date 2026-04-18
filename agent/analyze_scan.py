#!/usr/bin/env python3
"""Анализ самого богатого скана Bitrix24 — для итогового отчёта."""
import json, os, glob
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIR = os.path.join(BASE_DIR, "data", "bitrix_scans")

def find_richest_scan():
    """Находит скан с наибольшим объёмом данных."""
    all_files = sorted(glob.glob(os.path.join(SCAN_DIR, "scan_*.json")))
    best, best_size = None, 0
    for f in all_files:
        size = os.path.getsize(f)
        if size > best_size:
            best_size = size
            best = f
    return best

def analyze():
    path = find_richest_scan()
    if not path:
        print("No scans found")
        return
    
    with open(path, 'r', encoding='utf-8') as f:
        scan = json.load(f)
    
    print(f"=== BITRIX24 CRM ANALYSIS ===")
    print(f"Scan file: {os.path.basename(path)}")
    print(f"Scan time: {scan.get('scan_time', '?')}")
    print(f"Data since: {scan.get('since', '?')}")
    print()
    
    # DEALS
    deals = scan.get("deals", {})
    items = deals.get("items", [])
    print(f"DEALS: {deals.get('count', len(items))} total, {deals.get('total_amount', 0)} RUB")
    
    # Group by stage
    stages = defaultdict(list)
    for d in items:
        stages[d.get('STAGE_ID', 'UNKNOWN')].append(d)
    
    print("  By stage:")
    for stage, dlist in sorted(stages.items()):
        total = sum(float(d.get('OPPORTUNITY', 0)) for d in dlist)
        print(f"    {stage}: {len(dlist)} deals ({total:,.0f} RUB)")
    print()
    
    # ACTIVITIES
    acts = scan.get("activities", {})
    print(f"ACTIVITIES:")
    print(f"  Calls: {acts.get('calls_count', 0)}")
    print(f"  Chats (OL): {acts.get('chats_ol_count', 0)}")
    print(f"  SMS: {acts.get('sms_count', 0)}")
    print(f"  Webforms: {acts.get('webforms_count', 0)}")
    print(f"  Email: {acts.get('emails_count', 0)}")
    print(f"  Other: {acts.get('other_count', 0)}")
    print()
    
    # CALLS detail
    calls = acts.get("calls", [])
    print(f"CALL DETAILS ({len(calls)} calls):")
    
    in_calls = [c for c in calls if str(c.get('DIRECTION', '')) == '1']
    out_calls = [c for c in calls if str(c.get('DIRECTION', '')) == '2']
    print(f"  Incoming: {len(in_calls)}, Outgoing: {len(out_calls)}")
    
    # Duration analysis
    durations = []
    for c in calls:
        settings = c.get('SETTINGS', {})
        if isinstance(settings, dict):
            dur = settings.get('DURATION', 0)
        elif isinstance(settings, str):
            try:
                dur = json.loads(settings).get('DURATION', 0)
            except:
                dur = 0
        else:
            dur = 0
        durations.append(int(dur))
    
    if durations:
        avg_dur = sum(durations) / len(durations)
        max_dur = max(durations)
        total_dur = sum(durations)
        short = len([d for d in durations if d < 30])
        medium = len([d for d in durations if 30 <= d < 120])
        long_ = len([d for d in durations if d >= 120])
        print(f"  Duration: avg={avg_dur:.0f}s, max={max_dur}s, total={total_dur//60}min")
        print(f"  Short (<30s): {short}, Medium (30-120s): {medium}, Long (>2min): {long_}")
    
    # Print each call
    for i, c in enumerate(calls[:20], 1):
        subj = c.get('SUBJECT', 'No subject')
        direction = 'IN' if str(c.get('DIRECTION', '')) == '1' else 'OUT'
        settings = c.get('SETTINGS', {})
        if isinstance(settings, dict):
            dur = settings.get('DURATION', 0)
        elif isinstance(settings, str):
            try:
                dur = json.loads(settings).get('DURATION', 0)
            except:
                dur = 0
        else:
            dur = 0
        resp_id = c.get('RESPONSIBLE_ID', '?')
        created = c.get('CREATED', '?')[:16] if c.get('CREATED') else '?'
        desc = c.get('DESCRIPTION', '')[:100] if c.get('DESCRIPTION') else ''
        print(f"  {i}. [{direction}] {subj} | {dur}s | ResponsibleID={resp_id} | {created}")
        if desc:
            print(f"     Description: {desc}")
    print()
    
    # MANAGERS
    mgrs = scan.get("manager_stats", {})
    print(f"MANAGERS ({len(mgrs)}):")
    for name, stats in sorted(mgrs.items(), key=lambda x: x[1].get("deals", 0), reverse=True):
        if name in ("CRM B24", "Sluzhebnyj", "Admin"):
            continue
        print(f"  {name}: deals={stats.get('deals', 0)}, calls={stats.get('calls', 0)}, amount={stats.get('amount', 0):,.0f} RUB")
    print()
    
    # FORGOTTEN DEALS
    forgot = scan.get("forgotten_deals", {})
    print(f"FORGOTTEN DEALS: {forgot.get('count', 0)} ({forgot.get('total_amount', 0):,.0f} RUB)")
    for d in forgot.get("deals", [])[:5]:
        print(f"  ! {d.get('TITLE', '?')} - {float(d.get('OPPORTUNITY', 0)):,.0f} RUB | Modified: {d.get('DATE_MODIFY', '?')[:10]}")
    print()
    
    # TASKS
    tasks = scan.get("tasks", {})
    print(f"TASKS: {tasks.get('open', 0)} open, {tasks.get('closed', 0)} closed")
    
    # PRODUCTS
    prods = scan.get("products", {})
    print(f"PRODUCTS: {prods.get('count', 0)} in catalog")

if __name__ == "__main__":
    analyze()
