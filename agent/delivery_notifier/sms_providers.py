"""
SMS-провайдеры для системы уведомлений Азовского инкубатора.
Поддержка: SMS.ru, SMSC.ru, SMSAero (легко добавить новый).

Использование:
    provider = get_provider("smsru", api_key="YOUR_KEY")
    result = provider.send("79991234567", "Текст сообщения")
"""
import requests
import time
from abc import ABC, abstractmethod


class SMSProvider(ABC):
    """Абстрактный SMS-провайдер."""
    
    @abstractmethod
    def send(self, phone: str, text: str) -> dict:
        """Отправить SMS. Возвращает {'success': bool, 'message_id': str, 'error': str}"""
        pass
    
    @abstractmethod
    def check_balance(self) -> float:
        """Проверить баланс. Возвращает сумму в рублях."""
        pass
    
    @abstractmethod
    def get_status(self, message_id: str) -> str:
        """Статус доставки: 'delivered', 'sent', 'failed', 'unknown'."""
        pass


class SMSRuProvider(SMSProvider):
    """SMS.ru — простой и дешёвый.
    Регистрация: https://sms.ru
    Цена: ~2-3₽ за SMS (зависит от оператора).
    """
    
    BASE_URL = "https://sms.ru"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def send(self, phone: str, text: str) -> dict:
        try:
            resp = requests.get(f"{self.BASE_URL}/sms/send", params={
                "api_id": self.api_key,
                "to": phone,
                "msg": text,
                "json": 1
            }, timeout=15)
            data = resp.json()
            
            if data.get("status") == "OK":
                sms_data = data.get("sms", {}).get(phone, {})
                return {
                    "success": True,
                    "message_id": sms_data.get("sms_id", ""),
                    "error": ""
                }
            else:
                return {
                    "success": False,
                    "message_id": "",
                    "error": data.get("status_text", "Unknown error")
                }
        except Exception as e:
            return {"success": False, "message_id": "", "error": str(e)}
    
    def check_balance(self) -> float:
        try:
            resp = requests.get(f"{self.BASE_URL}/my/balance", params={
                "api_id": self.api_key,
                "json": 1
            }, timeout=10)
            data = resp.json()
            return float(data.get("balance", 0))
        except Exception:
            return -1
    
    def get_status(self, message_id: str) -> str:
        try:
            resp = requests.get(f"{self.BASE_URL}/sms/status", params={
                "api_id": self.api_key,
                "sms_id": message_id,
                "json": 1
            }, timeout=10)
            data = resp.json()
            status_code = data.get("sms", {}).get(message_id, {}).get("status_code", -1)
            status_map = {-1: "unknown", 100: "sent", 101: "sent", 102: "delivered", 103: "failed"}
            return status_map.get(status_code, "unknown")
        except Exception:
            return "unknown"


class SMSCProvider(SMSProvider):
    """SMSC.ru — быстрый, надёжный, до 1000 SMS/сек.
    Регистрация: https://smsc.ru
    """
    
    BASE_URL = "https://smsc.ru/sys"
    
    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
    
    def send(self, phone: str, text: str) -> dict:
        try:
            resp = requests.get(f"{self.BASE_URL}/send.php", params={
                "login": self.login,
                "psw": self.password,
                "phones": phone,
                "mes": text,
                "fmt": 3  # JSON
            }, timeout=15)
            data = resp.json()
            
            if "error" not in data:
                return {
                    "success": True,
                    "message_id": str(data.get("id", "")),
                    "error": ""
                }
            else:
                return {
                    "success": False,
                    "message_id": "",
                    "error": data.get("error", "Unknown error")
                }
        except Exception as e:
            return {"success": False, "message_id": "", "error": str(e)}
    
    def check_balance(self) -> float:
        try:
            resp = requests.get(f"{self.BASE_URL}/balance.php", params={
                "login": self.login,
                "psw": self.password,
                "fmt": 3
            }, timeout=10)
            data = resp.json()
            return float(data.get("balance", 0))
        except Exception:
            return -1
    
    def get_status(self, message_id: str) -> str:
        return "unknown"  # SMSC uses different status check


class DryRunProvider(SMSProvider):
    """Тестовый провайдер — НЕ отправляет SMS, только логирует.
    Используется для проверки перед боевой рассылкой.
    """
    
    def __init__(self):
        self.sent = []
    
    def send(self, phone: str, text: str) -> dict:
        msg_id = f"dry_{int(time.time())}_{len(self.sent)}"
        self.sent.append({"phone": phone, "text": text, "id": msg_id})
        print(f"  📱 [DRY RUN] → {phone}: {text[:60]}...")
        return {"success": True, "message_id": msg_id, "error": ""}
    
    def check_balance(self) -> float:
        return 999999.0
    
    def get_status(self, message_id: str) -> str:
        return "delivered"


def get_provider(name: str, **kwargs) -> SMSProvider:
    """Фабрика провайдеров.
    
    Примеры:
        get_provider("smsru", api_key="xxx")
        get_provider("smsc", login="xxx", password="xxx")
        get_provider("dryrun")  # тест без отправки
    """
    providers = {
        "smsru": lambda: SMSRuProvider(kwargs["api_key"]),
        "smsc": lambda: SMSCProvider(kwargs["login"], kwargs["password"]),
        "dryrun": lambda: DryRunProvider(),
    }
    
    if name not in providers:
        raise ValueError(f"Неизвестный провайдер: {name}. Доступные: {list(providers.keys())}")
    
    return providers[name]()
