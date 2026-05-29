#!/usr/bin/env python3
"""
🎙️ TTS Engine — Supertonic 3 (on-device, русский язык)
Генерирует WAV-файлы для автодозвона Mango Office.

Использование:
    from tts_engine import TTSEngine
    engine = TTSEngine()
    wav_path = engine.synthesize("Здравствуйте, ваш заказ подтверждён!")
"""

import os
import time

# Кэш модели — загружаем один раз
_tts_instance = None


def _get_tts():
    """Lazy-load TTS модели (300MB, грузим один раз)."""
    global _tts_instance
    if _tts_instance is None:
        try:
            from supertonic import TTS
            print("📥 TTS: загружаю Supertonic 3...")
            t0 = time.time()
            _tts_instance = TTS(
                model_dir=os.path.expanduser("~/.cache/huggingface/hub/supertonic-3"),
                auto_download=False,
            )
            print(f"✅ TTS: модель готова за {time.time()-t0:.1f}с")
        except ImportError:
            print("❌ TTS: supertonic не установлен. pip install supertonic")
            return None
        except Exception as e:
            print(f"❌ TTS: ошибка загрузки модели: {e}")
            return None
    return _tts_instance


# Голоса: F1–F5 — женские, M1–M5 — мужские
# F5 — выбранный голос (живой, чёткий, хорошо читает русский)
VOICE_FEMALE = "F5"
VOICE_MALE = "M1"

# ===========================================================
# ФИКСИРОВАННЫЙ ТЕКСТ АВТОДОЗВОНА
# Меняется ТОЛЬКО номер телефона клиента
# ===========================================================
CONFIRM_CALL_TEXT = (
    "Здравствуйте, это Азовский инкубатор, <breath> "
    "ваш заказ доставим завтра. <breath> "
    "Для подтверждения заказа скажите ДА <breath> "
    "или нажмите цифру один на телефоне, <breath> "
    "или скажите НЕТ <breath> "
    "и нажмите цифру ноль. <breath> "
    "Всего вам доброго!"
)

# Путь к кэшированному WAV (генерируется один раз, пересоздаётся только при изменении текста)
_CONFIRM_WAV_CACHE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tts_cache", "confirm_call_v1.wav"
)

# Шаблоны фраз для автодозвона
# <breath> — естественная пауза-вдох между блоками
TEMPLATES = {
    "confirm_order": (
        "Здравствуйте! <breath> "
        "Это компания Азовский инкубатор. "
        "Звоним подтвердить ваш заказ — {product}. <breath> "
        "Доставка {day}. <breath> "
        "Чтобы подтвердить заказ — нажмите один. "
        "Для отмены — нажмите ноль."
    ),
    "delivery_reminder": (
        "Здравствуйте! <breath> "
        "Напоминаем — завтра доставка вашего заказа. "
        "Будьте готовы принять {product}. <breath> "
        "По любым вопросам звоните нам. До свидания!"
    ),
    "missed_call": (
        "Здравствуйте! <breath> "
        "Вы звонили в Азовский инкубатор. "
        "Перезвоните нам — три шесть пять два, семь семь семь, шесть пять четыре. <breath> "
        "Мы поможем с выбором птицы. До свидания!"
    ),
    "payment_reminder": (
        "Здравствуйте! <breath> "
        "Напоминаем об ожидающей оплате вашего заказа. "
        "Пожалуйста, внесите предоплату для подтверждения брони. <breath> "
        "По вопросам — звоните нам. Спасибо!"
    ),
    "no_answer_sms": (
        "Здравствуйте! <breath> "
        "Мы звонили вам из Азовского инкубатора по поводу вашего заказа. "
        "Пожалуйста, перезвоните нам. Будем рады помочь!"
    ),
}


class TTSEngine:
    """
    TTS движок для генерации голосовых сообщений.
    Использует Supertonic 3 (on-device, без GPU, без torch).
    """

    def __init__(self, voice: str = VOICE_FEMALE, speed: float = 1.2, quality: int = 10):
        """
        voice:   F1/F2 (женский) или M1/M2 (мужской)
        speed:   0.7 (медленно) ... 2.0 (быстро), 1.0 = норма
        quality: 5 (быстро) ... 12 (высокое), 8 = баланс
        """
        self.voice = voice
        self.speed = speed
        self.quality = quality
        self._output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "tts_cache"
        )
        os.makedirs(self._output_dir, exist_ok=True)

    def synthesize(self, text: str, filename: str = None) -> str | None:
        """
        Генерирует WAV из текста.
        Возвращает путь к WAV файлу или None при ошибке.

        text:     текст для синтеза (русский)
        filename: имя файла (без пути), None = временный файл
        """
        tts = _get_tts()
        if tts is None:
            return None

        try:
            style = tts.get_voice_style(voice_name=self.voice)

            t0 = time.time()
            wav, duration = tts.synthesize(
                text=text,
                lang="ru",
                voice_style=style,
                total_steps=self.quality,
                speed=self.speed,
            )
            elapsed = time.time() - t0
            print(f"🎙️ TTS: '{text[:50]}...' → {duration[0]:.1f}с аудио за {elapsed:.1f}с")

            # Путь к файлу
            if filename:
                out_path = os.path.join(self._output_dir, filename)
            else:
                out_path = os.path.join(self._output_dir, f"tts_{int(time.time())}.wav")

            tts.save_audio(wav, out_path)
            print(f"✅ TTS: сохранён {out_path} ({os.path.getsize(out_path) // 1024} KB)")
            return out_path

        except Exception as e:
            print(f"❌ TTS synthesize error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def render_template(self, template_name: str, **kwargs) -> str | None:
        """
        Рендерит шаблон и синтезирует голос.

        Пример:
            engine.render_template("confirm_order",
                product="100 гусят",
                day="в понедельник")
        """
        if template_name not in TEMPLATES:
            print(f"❌ TTS: шаблон '{template_name}' не найден")
            return None

        text = TEMPLATES[template_name].format(**kwargs)
        filename = f"{template_name}_{int(time.time())}.wav"
        return self.synthesize(text, filename=filename)

    def synthesize_confirm(self, product: str, day: str = "в понедельник") -> str | None:
        """Фраза подтверждения заказа с DTMF-подсказкой."""
        return self.render_template("confirm_order", product=product, day=day)

    def synthesize_reminder(self, product: str) -> str | None:
        """Напоминание о доставке завтра."""
        return self.render_template("delivery_reminder", product=product)

    def get_confirm_wav(self, force_regen: bool = False) -> str | None:
        """
        Возвращает путь к WAV с фиксированным текстом автодозвона.
        Генерирует ОДИН РАЗ, потом отдаёт кэш.

        force_regen=True — перегенерировать даже если кэш есть.
        """
        if os.path.exists(_CONFIRM_WAV_CACHE) and not force_regen:
            print(f"📁 TTS: используем кэш → {_CONFIRM_WAV_CACHE}")
            return _CONFIRM_WAV_CACHE

        print("🎙️ TTS: генерируем confirm_call WAV...")
        result = self.synthesize(CONFIRM_CALL_TEXT, filename="confirm_call_v1.wav")
        return result


# === CLI ===
if __name__ == "__main__":
    import subprocess

    print("=== TTS Engine — тест финального скрипта ===\n")
    engine = TTSEngine()  # F5, speed=1.2, quality=10

    print("📞 Текст автодозвона:")
    print(f"   {CONFIRM_CALL_TEXT}\n")

    path = engine.get_confirm_wav(force_regen=True)
    if path:
        print(f"\n✅ WAV готов: {path}")
        print("🔊 Воспроизвожу...")
        subprocess.run(["afplay", path])
    else:
        print("❌ Синтез не удался")

