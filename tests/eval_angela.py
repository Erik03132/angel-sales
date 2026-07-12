"""
Angela Eval Suite — evaluates system, not just model.
Based on: https://habr.com/ru/articles/1050736/

Usage:
  python3 tests/eval_angela.py              # full suite
  python3 tests/eval_angela.py --router     # router only
  python3 tests/eval_angela.py --faq        # faq only
"""

import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
AGENT_DIR = os.path.join(BASE_DIR, 'agent')
sys.path.insert(0, AGENT_DIR)

from angela_agents import RouterAgent, KnowledgeBaseAgent


class EvalSuite:
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0

    def add(self, name: str, category: str, cap: bool, fn):
        """Register a test. cap=True=capability, False=regression"""
        self.tests.append((name, category, cap, fn))

    def run(self, filter_cat: str = None):
        for name, cat, cap, fn in self.tests:
            if filter_cat and cat != filter_cat:
                continue
            try:
                fn()
                tag = "✅" if cap else "🟢"
                print(f"  {tag} [{cat}] {name}")
                self.passed += 1
            except AssertionError as e:
                print(f"  ❌ [{cat}] {name}: {e}")
                self.failed += 1
            except Exception as e:
                print(f"  💥 [{cat}] {name}: {type(e).__name__}: {e}")
                self.failed += 1

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'─'*60}")
        print(f"  Результаты: {self.passed}/{total} passed")
        if total:
            print(f"  Score: {self.passed/total*100:.0f}%")
        return self.failed == 0


def build_suite() -> EvalSuite:
    suite = EvalSuite()
    router = RouterAgent()
    kb = KnowledgeBaseAgent()

    # ═══════════════════════════════════════
    # ROUTER
    # ═══════════════════════════════════════

    # classsify_complexity - regression (должно быть стабильно)
    for q, exp in [
        ("привет", "lite"),
        ("здравствуйте", "lite"),
        ("цена", "lite"),
        ("сколько стоит", "lite"),
        ("спасибо", "lite"),
        ("жалоба на качество", "pro"),
        ("хочу вернуть деньги", "pro"),
        ("нужен договор для юрлица", "pro"),
        ("опрос", "pro"),
    ]:
        suite.add(f"classify_complexity(\"{q}\") → {exp}", "router", False,
                  lambda q=q, exp=exp: assert_eq(router.classify_complexity(q), exp))

    # classify_complexity - capability (новые запросы)
    for q, exp in [
        ("какие породы бройлеров самые выгодные для разведения", "std"),
        ("расскажите подробнее про содержание индюков в домашних условиях", "std"),
        ("нужна консультация по кормлению цыплят в первую неделю жизни", "std"),
    ]:
        suite.add(f"classify_complexity(\"{q[:30]}...\") → {exp}", "router", True,
                  lambda q=q, exp=exp: assert_eq(router.classify_complexity(q), exp))

    # detect_topic - capability
    for q, exp in [
        ("сколько стоят бройлеры", "pricing"),
        ("есть ли доставка в крым", "delivery"),
        ("какой корм лучше для бройлеров", "feeding"),
        ("какие породы уток есть", "breeds"),
        ("есть ли в наличии муларды", "availability"),
        ("инкубационное яйцо когда вывод", "incubation"),
        ("как создать сделку в битрикс", "crm"),
        ("когда будет новый функционал", "dev"),
        ("как дела", "general"),
    ]:
        suite.add(f"detect_topic(\"{q[:30]}...\") → {exp}", "router", True,
                  lambda q=q, exp=exp: assert_eq(router.detect_topic(q), exp))

    # ═══════════════════════════════════════
    # KB - FAQ
    # ═══════════════════════════════════════

    # Regression: точное совпадение
    for q, key in [
        ("где вы находитесь", "где вы находитесь"),
        ("есть ли бройлеры", "есть ли бройлеры"),
        ("индюки", "индюки"),
        ("привет", "привет"),
        ("доставка", "доставка"),
        ("гарантия", "гарантия"),
        ("оплата", "оплата"),
    ]:
        suite.add(f"FAQ exact: \"{q}\" → \"{key}\"", "faq", False,
                  lambda q=q, key=key: assert_faq_hit(kb, q, key))

    # Capability: alias/fingerprint
    # "в москву привезёте" matches either of the two Moscow entries — both correct
    suite.add("FAQ alias: \"в москву привезёте...\" → Москва (любой)", "faq", True,
              lambda: assert_faq_hit_moscow(kb, "в москву привезёте"))

    for q, key in [
        ("расскажи про уток", "утки"),
        ("сколько стоят утки", "утки"),
        ("аптечка для цыплят", "аптечка"),
        ("привезите в москву", "в москву доставляете"),
        ("яйцо на инкубацию", "инкубационное яйцо"),
        ("а сколько стоят бройлера", "цена бройлера"),
        ("хочу заказать", "как заказать"),
        ("чем кормить цыплят бройлеров", "чем кормить цыплят"),
        ("посчитайте заказ", "посчитайте заказ"),
        ("ветеринарные справки", "вет справка"),
        ("к дому привезут", "к дому привезете"),
    ]:
        suite.add(f"FAQ alias: \"{q[:30]}...\" → \"{key}\"", "faq", True,
                  lambda q=q, key=key: assert_faq_hit(kb, q, key))

    # Regression: не должно находить
    for q in ["свинина", "кролики", "баранина", "как переустановить windows"]:
        suite.add(f"FAQ nomatch: \"{q}\" → None", "faq", False,
                  lambda q=q: assert_faq_miss(kb, q))

    # Capability: negative synonyms защита
    suite.add("FAQ neg-syn: \"бройлеры\" не находит \"утки\"", "faq", True,
              lambda: assert_faq_not_match(kb, "бройлеры", "утки"))
    suite.add("FAQ neg-syn: \"утки\" не находит \"индюки\"", "faq", True,
              lambda: assert_faq_not_match(kb, "утки", "индюки"))
    suite.add("FAQ neg-syn: \"индюки\" не находит \"бройлеры\"", "faq", True,
              lambda: assert_faq_not_match(kb, "индюки", "бройлеры"))

    return suite


def assert_eq(a, b):
    assert a == b, f"got \"{a}\" expected \"{b}\""

def assert_faq_hit(kb, query, expected_key):
    result = kb.lookup_faq(query)
    assert result, f"\"{query}\" should match FAQ \"{expected_key}\" but got None"
    expected = kb._faq_cache.get(expected_key, "")
    assert result == expected, (
        f"\"{query}\" matched wrong FAQ.\n"
        f"  Expected (\"{expected_key}\"): \"{expected[:50]}...\"\n"
        f"  Got: \"{result[:50]}...\""
    )

def assert_faq_miss(kb, query):
    result = kb.lookup_faq(query)
    assert not result, f"\"{query}\" should NOT match FAQ but got: \"{result[:50]}...\""

def assert_faq_not_match(kb, query, avoid_key):
    result = kb.lookup_faq(query)
    assert result, f"\"{query}\" should match something"
    avoided = kb._faq_cache.get(avoid_key, "")
    assert result != avoided, f"\"{query}\" matched \"{avoid_key}\" but should NOT"

def assert_faq_hit_moscow(kb, query):
    """Check that query matches any Moscow-related FAQ entry"""
    result = kb.lookup_faq(query)
    assert result, f"\"{query}\" should match a Moscow FAQ entry"
    assert "москв" in result.lower(), f"\"{query}\" matched but result doesn't mention Moscow: \"{result[:60]}...\""


if __name__ == "__main__":
    filter_cat = None
    if len(sys.argv) > 1:
        arg = sys.argv[1].lstrip("--")
        if arg in ("router", "faq"):
            filter_cat = arg

    print(f"\n{'='*60}")
    print(f"  Angela Eval Suite")
    print(f"  Based on: Evals: что должен знать каждый AI-инженер в 2026")
    if filter_cat:
        print(f"  Filter: {filter_cat}")
    print(f"{'='*60}")

    suite = build_suite()
    suite.run(filter_cat)
    ok = suite.summary()

    sys.exit(0 if ok else 1)
