import logging
import os
import io
import base64
import soundfile as sf
import torch
from vosk import Model
from typing import Dict, Optional

from core.config import settings

# --- Кэш для загруженных моделей Vosk ---
LOADED_VOSK_MODELS: Dict[str, Model] = {}

# --- Динамическая загрузка и кэширование моделей Vosk ---

def get_vosk_model(language_code: str = "ru") -> Optional[Model]:
    """
    Загружает или получает из кэша модель Vosk для указанного языка.

    Args:
        language_code: Код языка (например, 'ru', 'en-us').

    Returns:
        Загруженная модель Vosk или None, если модель не найдена.
    """
    if language_code in LOADED_VOSK_MODELS:
        logging.info(f"Возвращаю модель Vosk для языка '{language_code}' из кэша.")
        return LOADED_VOSK_MODELS[language_code]

    # Соглашение по именованию: модели лежат в 'vosk-models/vosk-model-{code}'
    # Старая модель 'vosk-model-ru' переименовывается в 'vosk-models/vosk-model-ru'
    model_path = os.path.join("vosk-models", f"vosk-model-{language_code}")

    # Обратная совместимость для старого пути русской модели
    if language_code == 'ru' and not os.path.exists(model_path) and os.path.exists("vosk-model-ru"):
        logging.warning("Обнаружена старая структура папок. Перемещаю 'vosk-model-ru' в 'vosk-models/vosk-model-ru'")
        os.makedirs("vosk-models", exist_ok=True)
        try:
            os.rename("vosk-model-ru", model_path)
        except OSError as e:
            logging.error(f"Не удалось переместить папку с моделью: {e}")
            return None

    if not os.path.exists(model_path):
        logging.error(f"Директория модели Vosk для языка '{language_code}' не найдена по пути: '{model_path}'")
        return None

    try:
        logging.info(f"Загружаю модель Vosk для языка '{language_code}' из '{model_path}'...")
        model = Model(model_path)
        LOADED_VOSK_MODELS[language_code] = model
        logging.info(f"Модель Vosk для языка '{language_code}' успешно загружена и кэширована.")
        return model
    except Exception as e:
        logging.error(f"Не удалось загрузить модель Vosk из '{model_path}': {e}")
        return None

# --- Логика синтеза речи (TTS) ---

class SileroTTS:
    def __init__(self, model_path: str):
        self.device = torch.device('cpu')
        torch.set_num_threads(4)
        if not os.path.isfile(model_path):
            logging.info(f"Файл модели Silero не найден по пути {model_path}. Скачиваю...")
            torch.hub.download_url_to_file(f'https://models.silero.ai/models/tts/ru/v3_1_ru.pt', model_path)
        try:
            self.model = torch.package.PackageImporter(model_path).load_pickle("tts_models", "model")
            self.model.to(self.device)
        except Exception as e:
            raise RuntimeError(f"Не удалось загрузить модель из файла '{model_path}': {e}")
        self.speakers = ['aidar', 'baya', 'kseniya', 'xenia', 'eugene', 'random']
        self.sample_rate = 48000

    def synthesize(self, text: str, speaker: str = 'baya') -> bytes:
        if speaker not in self.speakers: raise ValueError(f"Неверный голос. Доступные голоса: {self.speakers}")
        if not text: raise ValueError("Текст для синтеза не может быть пустым.")
        audio_tensor = self.model.apply_tts(text=text, speaker=speaker, sample_rate=self.sample_rate)
        buffer = io.BytesIO()
        sf.write(buffer, audio_tensor.numpy(), self.sample_rate, format='WAV')
        buffer.seek(0)
        return buffer.read()

async def text_to_speech(text: str, silero_tts_instance: "SileroTTS") -> str:
    if not silero_tts_instance: return ""
    try:
        audio_bytes = silero_tts_instance.synthesize(text=text, speaker='baya')
        return base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        logging.error(f"Ошибка синтеза речи: {e}")
        return ""

SAMPLE_RATE = 16000

# --- Инициализация моделей при старте приложения ---

silero_tts_instance: Optional[SileroTTS] = None

# Предзагружаем русскую модель при старте, чтобы обеспечить обратную совместимость и быстрый первый запуск
get_vosk_model("ru")

try:
    silero_tts_instance = SileroTTS(model_path=settings.SILERO_MODEL_PATH)
    logging.info("Модель SileroTTS успешно загружена.")
except Exception as e:
    logging.error(f"Не удалось загрузить модель SileroTTS: {e}")