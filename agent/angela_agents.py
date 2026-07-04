"""
Angela Agent System - 3 Specialized Agents
Based on: https://habr.com/ru/companies/alpinadigital/articles/1054436/

Architecture:
- Agent 1: Router (Workflow - 70%) -Deterministic role/topic classification
- Agent 2: KnowledgeBase (Workflow - 70%) - FAQ, products, context loading
- Agent 3: Generator (Autonomous - 30%) - LLM response generation

Principle: 70% workflow, 30% autonomous agents
"""

import json
import os
import re
import time
import traceback

import requests
from feed_calculator import process_feed_query
from hybrid_search import bm25_search
from memory_graph import MemoryGraph
from sales_logic import apply_sales_layer, resolve_breed_synonyms
from tool_digest import digest_product_context, digest_vector_context
from vector_memory import VectorMemory

# RAG Lite
try:
    from rag_lite import format_context_for_llm, search_knowledge
except ImportError:
    search_knowledge = None
    format_context_for_llm = None

# === ROLES ===
ROLE_CREATOR = "creator"
ROLE_BOSS = "boss"
ROLE_EMPLOYEE = "employee"
ROLE_CUSTOMER = "customer"

_CREATOR_TG_ID = str(os.getenv("ADMIN_TELEGRAM_ID", "176203333")).strip()

# === PHONE PATTERN ===
_PHONE_PATTERN = re.compile(
    r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
)

# === LOAD ENV ===
from dotenv import load_dotenv
load_dotenv(override=True)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

if not os.getenv("OPENROUTER_API_KEY"):
    load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

OPENROUTER_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip() or None
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")


# ═══════════════════════════════════════════════════════════════
# AGENT 1: ROUTER (Workflow - 70%)
# Deterministic role/topic classification
# ═══════════════════════════════════════════════════════════════

class RouterAgent:
    """Deterministic router: role + topic classification"""
    
    def __init__(self):
        self._roles_config = None
        self._load_roles_config()
    
    def _load_roles_config(self):
        """Load roles_config.json"""
        try:
            _roles_path = os.path.join(AGENT_DIR, "roles_config.json")
            _roles_real = os.path.realpath(_roles_path)
            if not _roles_real.startswith(os.path.realpath(AGENT_DIR) + os.sep):
                print(f"⚠️ Router: path traversal blocked: {_roles_real}")
                return
            if os.path.exists(_roles_real):
                with open(_roles_real, "r", encoding="utf-8") as f:
                    self._roles_config = json.load(f)
        except Exception as e:
            print(f"⚠️ Router: roles_config load error: {e}")
    
    def classify_role(self, sender_id: str = None, sender_name: str = None) -> str:
        """Classify user role (deterministic)"""
        sid = str(sender_id) if sender_id else ""
        
        # 1. Creator
        if sid == _CREATOR_TG_ID:
            return ROLE_CREATOR
        
        # 2. Boss/Employee from config
        if self._roles_config:
            user_entry = self._roles_config.get("users", {}).get(sid, {})
            user_role = user_entry.get("role", self._roles_config.get("default_role", "manager"))
            if user_role == "owner":
                return ROLE_BOSS
            elif user_role in ("manager", "employee"):
                return ROLE_EMPLOYEE
        
        # 3. Default: customer
        return ROLE_CUSTOMER
    
    def classify_complexity(self, prompt: str, history=None) -> str:
        """Classify query complexity: 'lite' | 'std' | 'pro'"""
        text = prompt.lower().strip()
        
        if len(text) < 15:
            return "lite"
        
        _PRO_KEYWORDS = {
            "жалоба", "претензия", "плохо", "дохнут", "падёж", "мор",
            "обман", "кинули", "некачественный", "больные", "заболели",
            "возврат", "вернуть деньги", "компенсация",
            "скидка", "торг", "дорого", "дешевле", "снизить цену",
            "оптом", "крупная партия", "тысяча", "10000", "5000",
            "конкурент", "другой поставщик", "у других дешевле",
            "юрлицо", "договор", "счёт-фактура", "накладная", "НДС",
        }
        
        _LITE_KEYWORDS = {
            "привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
            "цена", "стоимость", "сколько стоит", "прайс", "цены",
            "доставка", "когда доставка", "сроки", "когда привезут",
            "есть в наличии", "наличие", "остаток", "сколько есть",
            "контакты", "телефон", "адрес", "где находитесь",
            "график", "режим работы", "когда работаете",
            "спасибо", "благодарю", "ок", "хорошо", "понял", "ясно",
            "да", "нет", "ладно", "договорились",
        }
        
        for kw in _PRO_KEYWORDS:
            if kw in text:
                return "pro"
        
        for kw in _LITE_KEYWORDS:
            if kw in text:
                return "lite"
        
        if history and len(history) > 8:
            return "pro"
        
        return "std"
    
    def detect_topic(self, query: str) -> str:
        """Detect topic category (deterministic)"""
        q = query.lower()
        
        if any(kw in q for kw in ["цена", "стоимость", "сколько стоит", "прайс"]):
            return "pricing"
        elif any(kw in q for kw in ["доставка", "когда доставка", "сроки", "привезут"]):
            return "delivery"
        elif any(kw in q for kw in ["корм", "кормление", "комбикорм", "ПК-"]):
            return "feeding"
        elif any(kw in q for kw in ["порода", "цыплята", "бройлер", "несушк"]):
            return "breeds"
        elif any(kw in q for kw in ["наличие", "остаток", "есть в наличии"]):
            return "availability"
        elif any(kw in q for kw in ["инкубац", "вылуп", "яйц"]):
            return "incubation"
        elif any(kw in q for kw in ["crm", "сделк", "менеджер", "продаж"]):
            return "crm"
        elif any(kw in q for kw in ["задач", "проект", "разработк", "код"]):
            return "dev"
        else:
            return "general"
    
    def route(self, query: str, sender_id: str = None, sender_name: str = None, 
              history=None, channel: str = "website") -> dict:
        """Main routing function - deterministic workflow"""
        role = self.classify_role(sender_id, sender_name)
        complexity = self.classify_complexity(query, history)
        topic = self.detect_topic(query)
        
        return {
            "role": role,
            "complexity": complexity,
            "topic": topic,
            "channel": channel,
            "is_internal": role in (ROLE_CREATOR, ROLE_BOSS, ROLE_EMPLOYEE),
            "is_customer": role == ROLE_CUSTOMER,
        }


# ═══════════════════════════════════════════════════════════════
# AGENT 2: KNOWLEDGE BASE (Workflow - 70%)
# FAQ, products, context loading
# ═══════════════════════════════════════════════════════════════

class KnowledgeBaseAgent:
    """Deterministic knowledge loading: FAQ, products, context"""
    
    def __init__(self):
        self._prices_cache = {"data": None, "mtime": 0}
        self._prices_json_path = os.path.join(BASE_DIR, 'config', 'prices.json')
        self._faq_cache = {}
        self._wisdom = ""
        self._product_items = []
        self._product_bm25 = None
        self._smart_faq = None
        self._vdb = None
        self._memory_graph = None
        self._vector_mem = None
        
        self._load_all()
    
    def _load_all(self):
        """Load all knowledge sources"""
        # Prices
        self._load_prices()
        
        # FAQ cache
        _faq_path = os.path.join(DATA_DIR, 'faq_cache.json')
        if os.path.exists(_faq_path):
            with open(_faq_path, 'r', encoding='utf-8') as f:
                self._faq_cache = json.load(f)
            print(f"✅ KB: FAQ cache loaded: {len(self._faq_cache)} entries")
        
        # Expert knowledge
        _wisdom_path = os.path.join(DATA_DIR, 'expert_knowledge.md')
        if os.path.exists(_wisdom_path):
            with open(_wisdom_path, 'r', encoding='utf-8') as f:
                self._wisdom = f.read()
            print(f"✅ KB: Expert knowledge loaded: {len(self._wisdom)} chars")
        
        # Product catalog (Unified Brain)
        self._load_product_catalog()
        
        # SmartFAQ
        from angelochka_core import SmartFAQ
        self._smart_faq = SmartFAQ(DATA_DIR)
        
        # Vector DB
        try:
            from vector_db import AngelochkaVectorDB
            self._vdb = AngelochkaVectorDB()
            if not self._vdb.enabled:
                self._vdb = None
        except Exception:
            self._vdb = None
        
        # Memory Graph
        try:
            self._memory_graph = MemoryGraph()
            stats = self._memory_graph.stats()
            print(f"✅ KB: Memory graph: {stats['active_nodes']} nodes")
        except Exception:
            self._memory_graph = None
        
        # Vector Memory
        try:
            self._vector_mem = VectorMemory()
            stats = self._vector_mem.stats()
            if stats['total_vectors'] > 0:
                print(f"✅ KB: Vector memory: {stats['total_vectors']} embeddings")
        except Exception:
            self._vector_mem = None
    
    def _load_prices(self):
        """Load prices from config/prices.json"""
        try:
            mtime = os.path.getmtime(self._prices_json_path)
            if self._prices_cache["data"] is None or mtime != self._prices_cache["mtime"]:
                with open(self._prices_json_path, 'r', encoding='utf-8') as f:
                    self._prices_cache["data"] = json.load(f)
                self._prices_cache["mtime"] = mtime
                print(f"✅ KB: Prices loaded")
        except Exception as e:
            print(f"⚠️ KB: Prices load error: {e}")
    
    def _load_product_catalog(self):
        """Load product catalog from Unified Brain"""
        _brain_path = os.path.join(DATA_DIR, 'angelochka_unified_brain.json')
        if os.path.exists(_brain_path):
            with open(_brain_path, 'r', encoding='utf-8') as f:
                brain_data = json.load(f)
                products = []
                for item in brain_data:
                    if item.get("metadata", {}).get("type") == "product":
                        products.append(item["content"])
                self._product_items = products
            print(f"✅ KB: Product catalog: {len(self._product_items)} items")
            
            # BM25 index
            if self._product_items:
                try:
                    from rank_bm25 import BM25Okapi
                    import re as _re_prod
                    _prod_tokenized = [_re_prod.findall(r'\w+', item.lower()) for item in self._product_items]
                    self._product_bm25 = BM25Okapi(_prod_tokenized)
                    print(f"✅ KB: BM25 index: {len(self._product_items)} items")
                except Exception as e:
                    print(f"⚠️ KB: BM25 index error: {e}")
    
    def load_price_list(self) -> str:
        """Format price list for prompt"""
        data = self._prices_cache.get("data")
        if not data:
            return ""
        
        lines = []
        for cat_key, cat in data.get("categories", {}).items():
            label = cat.get("label", cat_key.upper())
            min_ord = cat.get("min_order", 1)
            lines.append(f"{label} (мин. {min_ord} гол.):")
            for name, item in cat.get("items", {}).items():
                if "prices" in item:
                    tiers = ", ".join(f"от {p['from']}шт={p['price']}₽" for p in item["prices"])
                    lines.append(f"  {name}: {tiers}")
                elif "price" in item:
                    lines.append(f"  {name}={item['price']}₽")
            lines.append("")
        
        delivery = data.get("delivery", {})
        if delivery:
            lines.append(f"Доставка: {delivery.get('days', '')} по {delivery.get('geography', '')}. {delivery.get('transport', '')}.")
            lines.append(f"Самовывоз: {delivery.get('pickup_address', '')}")
        
        return "\n".join(lines)
    
    def load_schedule_context(self, query: str = "", month: int = None) -> str:
        """Load schedule context"""
        # ... (existing implementation)
        return ""  # Placeholder - use original implementation
    
    def get_products_context(self, query: str) -> str:
        """Search products by query"""
        if not self._product_items:
            return ""
        
        import re as _re_q
        
        _SYNONYMS = {
            "гусята": "гусь гусенок гуси",
            "утята": "утка утки мускусная индоутка муллард",
            "цыплята": "кобб росс бройлер доминант",
            "бройлеры": "кобб росс бройлер",
            "индюки": "биг индюк индюшата",
            "несушки": "доминант ломан браун несушка",
        }
        
        tokens = _re_q.findall(r'\w+', query.lower())
        if not tokens:
            return ""
        
        expanded = list(tokens)
        for t in tokens:
            if t in _SYNONYMS:
                expanded.extend(_SYNONYMS[t].split())
        
        results = []
        
        if self._product_bm25:
            scores = self._product_bm25.get_scores(expanded)
            indexed = [(i, s) for i, s in enumerate(scores) if s > 0.5]
            indexed.sort(key=lambda x: -x[1])
            results = indexed[:7]
        
        if not results:
            for i, item in enumerate(self._product_items):
                item_lower = item.lower()
                for t in expanded:
                    if len(t) >= 3 and t in item_lower:
                        results.append((i, 1.0))
                        break
            results = results[:7]
        
        _EXCLUDE_PATTERNS = [
            "purina", "agravis", "аптечка", "доставка клиенту", "коробка",
            "тест", "предоплата", "позиция удалена", "заморозка"
        ]
        
        filtered = []
        for idx, score in results:
            item_lower = self._product_items[idx].lower()
            if not any(excl in item_lower for excl in _EXCLUDE_PATTERNS):
                filtered.append((idx, score))
        
        if not filtered:
            return ""
        
        lines = ["📦 КАТАЛОГ ТОВАРОВ (актуальные данные):"]
        for i, (idx, _score) in enumerate(filtered, 1):
            lines.append(f"  {i}. {self._product_items[idx]}")
        
        return "\n".join(lines)
    
    def get_vector_context(self, query: str) -> str:
        """Get vector context from BM25 + RAG + Vector"""
        context = ""
        
        # BM25
        try:
            bm25_results = bm25_search(query, limit=5)
            if bm25_results:
                bm25_context = "\n".join([f"BM25: {r['content']}" for r in bm25_results[:3]])
                context += bm25_context
        except Exception as e:
            print(f"⚠️ KB: BM25 error: {e}")
        
        # RAG Lite
        if search_knowledge:
            try:
                rag_results = search_knowledge(query, top_k=3)
                if rag_results and rag_results[0].get('score', 0) > 5:
                    rag_context = format_context_for_llm(rag_results, max_chars=1500)
                    context += "\n" + rag_context if context else rag_context
            except Exception as e:
                print(f"⚠️ KB: RAG Lite error: {e}")
        
        # Vector Memory
        if self._vector_mem and self._vector_mem.index.ntotal > 0:
            try:
                vector_results = self._vector_mem.search(query, top_k=3)
                if vector_results:
                    vector_context = "\n".join([f"Vector: {r['content']}" for r in vector_results])
                    context += "\n" + vector_context if context else vector_context
            except Exception as e:
                print(f"⚠️ KB: Vector error: {e}")
        
        return context
    
    def get_client_memory(self, sender_id: str) -> str:
        """Get client memory from graph"""
        if not self._memory_graph or not sender_id:
            return ""
        
        try:
            memory_map = self._memory_graph.get_memory_map(str(sender_id))
            if memory_map.get("hubs"):
                for hub in memory_map["hubs"]:
                    self._memory_graph.warm_up(hub["node_id"], 0.3)
                mem_lines = ["\n🧠 ПАМЯТЬ О КЛИЕНТЕ (из графа):"]
                for hub in memory_map["hubs"]:
                    mem_lines.append(f"  • {hub['name']} (важность: {hub['val']})")
                    for detail in hub.get("details", []):
                        scar = " ⚡ШРАМ" if detail.get("is_scar") else ""
                        mem_lines.append(f"    - {detail['name']}{scar}")
                return "\n".join(mem_lines)
        except Exception as e:
            print(f"⚠️ KB: Memory graph error: {e}")
        
        return ""
    
    def lookup_faq(self, query: str) -> str:
        """Look up FAQ cache"""
        # SmartFAQ
        if self._smart_faq:
            cached = self._smart_faq.lookup(query)
            if cached:
                return cached
        
        # Static FAQ
        for q, a in self._faq_cache.items():
            q_lower = q.lower().strip()
            query_lower = query.lower().strip()
            if len(query_lower) < 30 and q_lower == query_lower:
                return a
        
        return ""
    
    def track_faq(self, query: str, answer: str):
        """Track FAQ for auto-caching"""
        if self._smart_faq and len(answer) > 50:
            self._smart_faq.track(query, answer)


# ═══════════════════════════════════════════════════════════════
# AGENT 3: GENERATOR (Autonomous - 30%)
# LLM response generation
# ═══════════════════════════════════════════════════════════════

class GeneratorAgent:
    """Autonomous LLM generator with tier routing"""
    
    _TIER_MODELS = {
        "lite": [
            "deepseek/deepseek-v4-flash",
            "deepseek/deepseek-v4-flash:free",
            "qwen/qwen3.6-flash",
        ],
        "std": [
            "deepseek/deepseek-v4-pro",
            "deepseek/deepseek-v4-flash",
            "moonshotai/kimi-k2.6",
        ],
        "pro": [
            "deepseek/deepseek-v4-pro",
            "moonshotai/kimi-k2.6",
            "anthropic/claude-sonnet-4.6",
        ],
    }
    
    def __init__(self):
        pass
    
    def call_llm(self, prompt: str, history=None, system_prompt: str = None, 
                 tier: str = None) -> str:
        """Call LLM with tier routing"""
        if tier is None:
            tier = "std"
        
        # OpenRouter
        result = self._call_openrouter(prompt, history, system_prompt, tier)
        if result:
            return result
        
        # Ollama fallback
        result = self._call_ollama(prompt, history)
        if result:
            return result
        
        return "Прости, у меня сейчас технические неполадки... Напиши мне через пару минут! 🐣"
    
    def _call_openrouter(self, prompt, history=None, system_prompt=None, tier="std"):
        """Call OpenRouter with tier routing"""
        if not OPENROUTER_KEY:
            return None
        
        saved_proxies = {}
        for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
            if key in os.environ:
                saved_proxies[key] = os.environ.pop(key)
        
        messages = []
        if system_prompt:
            messages.append({
                "role": "system",
                "content": [{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }]
            })
        
        if history:
            for msg in history:
                role = "assistant" if msg.get("role") == "model" else msg.get("role", "user")
                content = msg.get("parts", [msg.get("content", "")])[0] if isinstance(msg.get("parts"), list) else msg.get("content", "")
                messages.append({"role": role, "content": content})
        
        messages.append({"role": "user", "content": prompt})
        
        or_models = self._TIER_MODELS.get(tier, self._TIER_MODELS["std"])
        print(f"🎯 Generator: tier={tier.upper()}, models={[m.split('/')[-1] for m in or_models]}")
        
        try:
            for model_name in or_models:
                try:
                    resp = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                        json={"model": model_name, "messages": messages, "max_tokens": 4096},
                        timeout=45,
                        proxies={"http": None, "https": None}
                    )
                    try:
                        data = resp.json()
                    except (ValueError, KeyError):
                        continue
                    if data.get("choices") and len(data["choices"]) > 0:
                        print(f"✅ Generator: {model_name} (tier={tier})")
                        return data["choices"][0]["message"]["content"]
                except Exception as e:
                    print(f"⚠️ Generator: {model_name} error: {e}")
            
            return None
        finally:
            for key, val in saved_proxies.items():
                os.environ[key] = val
    
    def _call_ollama(self, prompt, history=None):
        """Ollama fallback"""
        try:
            messages = []
            if history:
                for msg in history:
                    role = "assistant" if msg.get("role") == "model" else msg.get("role", "user")
                    content = msg.get("parts", [msg.get("content", "")])[0] if isinstance(msg.get("parts"), list) else msg.get("content", "")
                    messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": prompt})
            
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
                timeout=120
            )
            data = resp.json()
            if "message" in data and "content" in data["message"]:
                print(f"✅ Generator: Ollama/{OLLAMA_MODEL} (offline)")
                return data["message"]["content"]
            return None
        except Exception as e:
            print(f"⚠️ Generator: Ollama error: {e}")
            return None


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR: Combines 3 agents
# ═══════════════════════════════════════════════════════════════

class AngelaOrchestrator:
    """Orchestrates 3 agents: Router → KnowledgeBase → Generator"""
    
    def __init__(self):
        self.router = RouterAgent()
        self.kb = KnowledgeBaseAgent()
        self.generator = GeneratorAgent()
    
    def get_answer(self, query: str, history=None, sender_id=None, 
                   sender_name=None, channel="website") -> str:
        """Main entry point - orchestrates 3 agents"""
        if history is None:
            history = []
        
        # Step 1: Router (deterministic)
        route = self.router.route(query, sender_id, sender_name, history, channel)
        print(f"🎭 Route: role={route['role']}, complexity={route['complexity']}, topic={route['topic']}")
        
        # Step 2: Knowledge Base (deterministic)
        context = self._load_context(query, route, history)
        
        # Step 3: Generator (autonomous)
        answer = self._generate_answer(query, route, context, history)
        
        return answer
    
    def _load_context(self, query: str, route: dict, history: list) -> dict:
        """Load all context from Knowledge Base"""
        context = {
            "prices": "",
            "schedule": "",
            "products": "",
            "vector": "",
            "client_memory": "",
            "faq": "",
        }
        
        # Prices
        context["prices"] = self.kb.load_price_list()
        
        # Schedule
        context["schedule"] = self.kb.load_schedule_context(query)
        
        # Products (not for seller channels)
        if not (route["is_customer"] and route["channel"] in ("website", "vk")):
            context["products"] = self.kb.get_products_context(query)
        
        # Vector context
        if not (route["is_customer"] and route["channel"] in ("website", "vk")):
            context["vector"] = self.kb.get_vector_context(query)
        
        # Client memory
        # (needs sender_id - will be passed separately)
        
        # FAQ
        context["faq"] = self.kb.lookup_faq(query)
        
        return context
    
    def _generate_answer(self, query: str, route: dict, context: dict, history: list) -> str:
        """Generate answer using Generator"""
        # Build system prompt based on role
        system_prompt = self._build_system_prompt(route, context, history)
        
        # Call LLM
        answer = self.generator.call_llm(
            query, history, system_prompt, tier=route["complexity"]
        )
        
        return answer
    
    def _build_system_prompt(self, route: dict, context: dict, history: list) -> str:
        """Build system prompt based on role"""
        # This will use the existing prompt building logic
        # For now, return a basic prompt
        return f"Role: {route['role']}, Topic: {route['topic']}"


# Legacy interface
def get_answer(query: str, history=None, sender_id=None, sender_name=None, channel="website") -> str:
    """Legacy interface - use AngelaOrchestrator for new code"""
    orchestrator = AngelaOrchestrator()
    return orchestrator.get_answer(query, history, sender_id, sender_name, channel)
