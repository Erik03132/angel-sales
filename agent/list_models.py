import google.generativeai as genai
import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

for m in genai.list_models():
    if 'embedContent' in m.supported_generation_methods:
        print(m.name)
