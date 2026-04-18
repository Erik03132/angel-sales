import os
import vk_api
import json
import time

# Загружаем настройки
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

VK_LOGIN = os.getenv("VK_LOGIN")
VK_PASS = os.getenv("VK_PASS")
# Ссылка на группу (нужен ID)
GROUP_ID = os.getenv("VK_GROUP_ID", "-202157053") # ID группы 'Азовский Инкубатор'

def auth_handler():
    """Обработчик двухфакторки (если понадобится)"""
    key = input("Введите код подтверждения из SMS/App: ")
    remember_device = True
    return key, remember_device

def fetch_vk_knowledge():
    print(f"🚀 Попытка входа в ВК для {VK_LOGIN}...")
    
    try:
        vk_session = vk_api.VkApi(
            VK_LOGIN, 
            VK_PASS,
            auth_handler=auth_handler
        )
        vk_session.auth()
        vk = vk_session.get_api()
        
        print("✅ Авторизация успешна! Начинаю сбор данных...")
        
        # 1. Собираем стену группы (посты и комментарии к ним)
        # Нам нужно название или ID группы. Попробуем найти по короткому имени если надо.
        target_group = "incubird" # Публичный адрес
        
        posts = vk.wall.get(domain=target_group, count=100)
        knowledge_blocks = []
        
        for post in posts['items']:
            text = post['text']
            if len(text) > 50:
                knowledge_blocks.append({
                    "content": text,
                    "metadata": {"source": "VK Post", "date": post['date']}
                })
            
            # Собираем комменты к посту (там часто вопросы-ответы)
            comments = vk.wall.getComments(domain=target_group, post_id=post['id'], count=50)
            for comm in comments['items']:
                if len(comm['text']) > 20:
                    knowledge_blocks.append({
                        "content": comm['text'],
                        "metadata": {"source": "VK Comment", "post_id": post['id']}
                    })
                    
        # Сохраняем для векторизации
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'raw_vk_knowledge.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge_blocks, f, ensure_ascii=False, indent=2)
            
        print(f"✨ Собрано {len(knowledge_blocks)} фрагментов знаний из ВК!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка входа/сбора ВК: {e}")
        return False

if __name__ == "__main__":
    fetch_vk_knowledge()
