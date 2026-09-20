import logging
import os
import uuid

from core.domain.entities.media_asset import MediaAsset
from core.domain.ports.video_source_port import VideoSourcePort

logger = logging.getLogger(__name__)

class UserUploadedAssetProvider(VideoSourcePort):
    """
    Kullanıcının Gradio UI üzerinden Medya Havuzuna (Asset Pool) yüklediği
    videoları 'Pexels' veya stok siteler yerine lokal klasörden bulup sisteme veren adaptör.
    """
    def __init__(self, upload_directory: str = "output/user_uploads/videos"):
        self.upload_directory = upload_directory
        if not os.path.exists(self.upload_directory):
            os.makedirs(self.upload_directory)

    @property
    def name(self) -> str:
        return "UserUploads"

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        """
        Klasördeki yüklenmiş videoları tarar ve arama terimine en yakın olanları getirir.
        Şu anlık basit dosya adı eşleşmesi yapar.
        """
        logger.info(f"UserUploads provider searching for: '{query}' in {self.upload_directory}")
        count = 0
        results: list[MediaAsset] = []
        query_words = [word for word in query.lower().split() if word]

        # Kullanıcı dosyalarını oku
        files = []
        if os.path.exists(self.upload_directory):
            files = [f for f in os.listdir(self.upload_directory) if f.lower().endswith(('.mp4', '.mov'))]

        # Basitçe dosya adında arama kelimesi geçiyorsa döndür.
        # Eğer hiç geçmiyorsa (ya da isimler alakasızsa) boş dönme diye rastgele de verebiliriz,
        # fakat şimdilik eşleşenleri veya sıradakileri veriyoruz.
        matched = [f for f in files if any(word in f.lower() for word in query_words)]
        ordered_files = matched + [f for f in files if f not in matched]
        for f in ordered_files:
            if count >= max_results:
                break

            file_path = os.path.join(self.upload_directory, f)
            # Yapay Zeka video seçicisine MediaAsset formatında ver.
            results.append(MediaAsset(
                id=str(uuid.uuid4()),
                provider="user_uploads",
                provider_asset_id=f,
                media_type="video",
                original_url=file_path,  # Local path
                duration_seconds=10.0, # Approximate, could use ffprobe here
                width=1080,
                height=1920,
                fps=30,
                local_path=file_path,
                metadata={"description": f"User uploaded asset: {f}"},
            ))
            count += 1

        if count == 0:
            logger.warning("Kullanıcı klasöründe uygun video bulunamadı. Lütfen Medya Havuzuna dosya yükleyin.")
        return results

    async def download(self, asset: MediaAsset) -> bytes:
        """Dosya zaten lokalde olduğu için doğrudan okuyup bytes olarak dön."""
        if not os.path.exists(asset.original_url):
            raise FileNotFoundError(f"Asset file missing: {asset.original_url}")

        with open(asset.original_url, "rb") as f:
            return f.read()
