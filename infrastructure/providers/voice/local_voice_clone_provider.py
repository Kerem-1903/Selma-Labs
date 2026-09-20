import asyncio
import io
import logging
import os
import wave

from core.domain.exceptions import ProviderError
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.voice_direction import VoiceDirection

logger = logging.getLogger(__name__)

class LocalVoiceCloneProvider(VoiceGeneratorPort):
    """
    Kullanıcının yüklediği 10-30 saniyelik referans sesi kullanarak
    metni (senaryoyu) o sesle klonlayarak okuyan Coqui XTTSv2 altyapısı.
    """

    def __init__(self, reference_audio_path: str = "output/user_uploads/voice_reference.wav", model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"):
        self.reference_audio_path = reference_audio_path
        self.model_name = model_name
        self.tts = None # Lazy loading (sadece kullanılacağı zaman belleğe alınır)

    @property
    def name(self) -> str:
        return "local_xtts"

    def _load_model(self):
        if self.tts is None:
            logger.info("Yükleniyor: Local XTTS Voice Cloning Modeli (Bu işlem ilk seferde vakit alabilir)...")
            try:
                import torch
                from TTS.api import TTS
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self.tts = TTS(self.model_name).to(device)
                logger.info(f"Model {device} üzerinde başarıyla yüklendi.")
            except ImportError:
                raise ProviderError("TTS modülü bulunamadı. Lütfen 'pip install TTS' komutuyla yükleyin.")

    async def generate_voice(
        self,
        text: str,
        voice_name: str,
        *,
        direction: VoiceDirection | None = None,
    ) -> GeneratedAudio:
        del direction
        if not text.strip():
            raise ValueError("Klonlanacak metin boş olamaz.")

        if not os.path.exists(self.reference_audio_path):
            raise ProviderError(f"Referans ses bulunamadı: {self.reference_audio_path}. Lütfen UI üzerinden bir ses yükleyin.")

        logger.info(f"Ses klonlanıyor... Voice: {voice_name}")

        # CPU/GPU blocking process olduğu için bunu bir thread'de çalıştırmak en güvenlisidir.
        loop = asyncio.get_event_loop()

        output_dir = "output/voice_cache"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{voice_name}.wav")

        def _synthesize():
            self._load_model()
            self.tts.tts_to_file(
                text=text,
                speaker_wav=self.reference_audio_path,
                language="tr",
                file_path=output_path
            )

        try:
            await loop.run_in_executor(None, _synthesize)
        except Exception as e:
            logger.error(f"Ses klonlama sırasında hata oluştu: {e}")
            raise ProviderError(f"Local TTS Hatası: {e}")

        # VoiceService'in beklediği formatta (GeneratedAudio) dönüyoruz.
        with open(output_path, "rb") as f:
            audio_bytes = f.read()

        with wave.open(io.BytesIO(audio_bytes), "rb") as audio_file:
            sample_rate = audio_file.getframerate()
            duration_seconds = audio_file.getnframes() / sample_rate

        return GeneratedAudio(
            audio_bytes=audio_bytes,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
            provider="local_xtts",
            voice_name=voice_name,
        )
