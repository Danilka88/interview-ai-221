import numpy as np
import noisereduce as nr
import logging

# Параметры для шумоподавления (можно будет вынести в конфиг)
# Эти значения могут быть настроены в зависимости от типа шума и желаемого результата
DEFAULT_NOISE_REDUCE_RATE = 0.8 # Степень подавления шума (0.0 - 1.0)
DEFAULT_CHUNK_SIZE = 4096 # Размер обрабатываемого аудио-чанка

async def process_audio_for_noise_reduction(audio_chunk: bytes, sample_rate: int, noise_reduce_rate: float = DEFAULT_NOISE_REDUCE_RATE) -> bytes:
    """
    Применяет алгоритм шумоподавления к аудио-чанку.
    Принимает аудио в формате bytes (PCM 16-bit, mono).
    Возвращает обработанный аудио-чанк в том же формате.
    """
    if not audio_chunk:
        return b''

    try:
        # Преобразование байтов в массив numpy (PCM 16-bit, mono)
        # Предполагаем, что аудио приходит в формате int16
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)

        # Нормализация аудио для noisereduce (требует float)
        audio_data_float = audio_data.astype(np.float32) / 32768.0

        # Применение шумоподавления
        # Здесь можно использовать более сложные методы определения шума,
        # но для начала подойдет простой подход
        reduced_noise_audio = nr.reduce_noise(
            y=audio_data_float,
            sr=sample_rate,
            # Параметры для определения шума можно настроить
            # Например, noise_clip=0.1, prop_decrease=noise_reduce_rate
            prop_decrease=noise_reduce_rate
        )

        # Обратное преобразование в int16
        reduced_noise_audio_int16 = (reduced_noise_audio * 32767).astype(np.int16)

        return reduced_noise_audio_int16.tobytes()
    except Exception as e:
        logging.error(f"Ошибка при обработке аудио для шумоподавления: {e}", exc_info=True)
        # В случае ошибки возвращаем исходный чанк, чтобы не прерывать поток
        return audio_chunk
