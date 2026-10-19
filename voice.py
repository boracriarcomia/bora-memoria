"""On-demand, local Portuguese dictation. Audio is never persisted or sent to Google."""
import base64
import binascii
import io
import json
import os
from pathlib import Path
import threading
import wave

_lock = threading.Lock()
MAX_SECONDS = 60


def model_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'BoraMemoria/models/vosk-model-small-pt-0.3'


def status():
    return {'available': (model_path() / 'final.mdl').is_file(), 'engine': 'Vosk local · português', 'max_seconds': MAX_SECONDS}


def transcribe(payload):
    encoded = payload.get('audio') if isinstance(payload, dict) else None
    if not isinstance(encoded, str) or len(encoded) > 2_600_000:
        raise ValueError('Áudio inválido ou acima de 60 segundos.')
    try:
        raw = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(raw), 'rb') as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getframerate() != 16000 or audio.getcomptype() != 'NONE':
                raise ValueError('Use áudio mono PCM de 16 kHz.')
            if not 0 < audio.getnframes() <= 16000 * MAX_SECONDS:
                raise ValueError('Grave entre 1 e 60 segundos.')
            pcm = audio.readframes(audio.getnframes())
            if len(pcm) != audio.getnframes() * 2:
                raise ValueError('Áudio incompleto.')
    except (wave.Error, EOFError, binascii.Error) as error:
        raise ValueError('Não foi possível ler o áudio.') from error
    if not status()['available']:
        raise ValueError('O modelo de voz em português ainda não está instalado neste computador.')
    if not _lock.acquire(blocking=False):
        raise ValueError('Já existe uma transcrição em andamento.')
    try:
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        # No resident recognizer: release its model after each request.
        model = Model(str(model_path()))
        recognizer = KaldiRecognizer(model, 16000)
        words = []
        for offset in range(0, len(pcm), 8000):
            if recognizer.AcceptWaveform(pcm[offset:offset+8000]):
                words.append(json.loads(recognizer.Result()).get('text', ''))
        words.append(json.loads(recognizer.FinalResult()).get('text', ''))
        text = ' '.join(part for part in words if part).strip()
        if not text:
            raise ValueError('Não identifiquei fala. Tente novamente, mais perto do microfone.')
        return {'text': text[:8000], 'engine': 'vosk-local', 'review_required': True}
    except (ImportError, OSError) as error:
        raise ValueError('Não foi possível iniciar a transcrição local.') from error
    finally:
        _lock.release()
