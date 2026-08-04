# selma-labs-sprint14

Intelligent Asset Reuse: `TimelineService`, birbirine çok benzeyen sahneler
(aynı arama anahtar kelimeleri, benzer anlatım metni, benzer süre) için aynı
indirilmiş `MediaAsset`'i tekrar kullanır — gereksiz indirme ve API çağrısı önlenir.

Benzerlik tespiti:
- Sahneler önce arama anahtar kelimelerine göre bucket'lara ayrılır (O(N²) karşılaştırmayı önlemek için).
- Aynı bucket içindeki sahneler `difflib.SequenceMatcher` ile anlatım metni benzerliğine göre karşılaştırılır (`scene_reuse_narration_threshold`).
- Süre farkı da bir eşik değeriyle sınırlandırılır (`scene_reuse_duration_threshold`).
- Reuse sadece hedef sahnenin indirilen asset'inin sağlayıcısı (`provider`), yeniden kullanılacak sahnenin aday listesinde varsa gerçekleşir.
- Özellik varsayılan olarak kapalıdır (`scene_reuse_enabled: bool = False`).

## İçerik

Bu değişiklikte **yeni dosya yok**, yalnızca mevcut dosyalarda değişiklik var.
Orijinal (base) dosya içerikleri elimde olmadığından, değişiklikler `patches/`
klasöründe unified diff formatında paketlendi.

Kendi repo kökünüzde şu şekilde uygulayabilirsiniz:

```bash
cd /path/to/your/repo
patch -p0 < patches/config_settings.diff
patch -p0 < patches/core_application_services_timeline_service.diff
patch -p0 < patches/tests_unit_test_timeline_service.diff
patch -p0 < patches/README.diff
patch -p0 < patches/CURRENT_STATUS.diff
patch -p0 < patches/ARCHITECTURE_REVIEW.diff
```

Değiştirilen dosyalar:
- `config/settings.py`
- `core/application/services/timeline_service.py`
- `tests/unit/test_timeline_service.py`
- `README.md`
- `CURRENT_STATUS.md`
- `ARCHITECTURE_REVIEW.md`

## Manuel adımlar
- (Yok)

## Çalıştırılacak testler
```bash
pytest tests/unit/test_timeline_service.py
```
