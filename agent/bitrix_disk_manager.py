import os

import requests
from dotenv import load_dotenv


class BitrixDiskManager:
    def __init__(self, user_id=15):
        # Ищем .env в папке выше (ai-eggs)
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        load_dotenv(env_path)
        
        url = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL") or os.getenv("BITRIX_WEBHOOK_URL")
        if not url:
            # Фолбек на известный URL из логов, если .env не загрузился
            url = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL") or os.getenv("BITRIX_WEBHOOK_URL")
            
        self.webhook_url = url.rstrip('/')
        self.user_id = user_id
        # ТЕПЕРЬ ПРИОРИТЕТ НА ОБЩИЙ ДИСК (для видимости всеми)
        self.storage_id = self._find_best_storage()
        self.root_folder_name = "00_CONTENT_MACHINE_EGGS"

    def _find_best_storage(self):
        """Находит Общий диск (common) или Личный диск пользователя."""
        try:
            res = requests.get(f"{self.webhook_url}/disk.storage.getlist.json")
            storages = res.json().get('result', [])
            
            # 1. Сначала ищем Общий диск (виден всем)
            for s in storages:
                if s.get('ENTITY_TYPE') == 'common':
                    print(f"📂 Выбран Общий диск (ID {s['ID']})")
                    return s['ID']
            
            # 2. Фолбек: Личный диск Игоря (15)
            for s in storages:
                if s.get('ENTITY_TYPE') == 'user' and str(s.get('ENTITY_ID')) == str(self.user_id):
                    print(f"📂 Выбран Личный диск ID {s['ID']}")
                    return s['ID']
                    
        except Exception as e:
            print(f"⚠️ Ошибка поиска диска: {e}")
        
        return 3 # Жесткий фолбек на ID Общего диска в песочнице

    def get_or_create_root_folder(self):
        res = requests.get(f"{self.webhook_url}/disk.storage.getchildren.json", params={"id": self.storage_id})
        items = res.json().get('result', [])
        for item in items:
            if item['NAME'] == self.root_folder_name and item['TYPE'] == 'folder':
                return item['ID']
        
        res = requests.post(f"{self.webhook_url}/disk.storage.addfolder.json", json={
            "id": self.storage_id,
            "data": {"NAME": self.root_folder_name}
        })
        return res.json().get('result', {}).get('ID')

    def create_subfolder(self, parent_id, name):
        res = requests.get(f"{self.webhook_url}/disk.folder.getchildren.json", params={"id": parent_id})
        items = res.json().get('result', [])
        for item in items:
            if item['NAME'] == name:
                return item['ID']
        
        res = requests.post(f"{self.webhook_url}/disk.folder.addsubfolder.json", json={
            "id": parent_id,
            "data": {"NAME": name}
        })
        return res.json().get('result', {}).get('ID')

    def upload_file(self, folder_id, filename, content):
        import base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        res = requests.post(f"{self.webhook_url}/disk.folder.uploadfile.json", json={
            "id": folder_id,
            "data": {"NAME": filename},
            "fileContent": encoded_content
        })
        return res.json().get('result', {}).get('ID')
