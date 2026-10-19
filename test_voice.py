import base64,io,wave,unittest
from unittest.mock import patch
import voice

def wav(frames=16000,rate=16000,channels=1):
    out=io.BytesIO()
    with wave.open(out,'wb') as f:
        f.setnchannels(channels);f.setsampwidth(2);f.setframerate(rate);f.writeframes(b'\0'*frames*channels*2)
    return {'audio':base64.b64encode(out.getvalue()).decode()}

class VoiceTest(unittest.TestCase):
    def test_rejects_invalid_audio_and_unsupported_format(self):
        for payload in ({},{'audio':'%'},{'audio':123},wav(rate=8000),wav(channels=2),wav(frames=0),wav(frames=16000*61)):
            with self.subTest(payload_type=type(payload)):
                with self.assertRaises(ValueError):voice.transcribe(payload)
    def test_requires_installed_model(self):
        with patch('voice.status',return_value={'available':False}):
            with self.assertRaisesRegex(ValueError,'instalado'):voice.transcribe(wav())
    def test_rejects_overlapping_transcription(self):
        voice._lock.acquire()
        try:
            with patch('voice.status',return_value={'available':True}):
                with self.assertRaisesRegex(ValueError,'andamento'):voice.transcribe(wav())
        finally:voice._lock.release()
    def test_truncated_wav_rejected(self):
        payload=wav();payload['audio']=base64.b64encode(base64.b64decode(payload['audio'])[:-30]).decode()
        with self.assertRaisesRegex(ValueError,'incompleto'):voice.transcribe(payload)
if __name__=='__main__':unittest.main()
