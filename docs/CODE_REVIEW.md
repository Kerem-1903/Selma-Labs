# SELMA Labs — Kod İncelemesi

**Tarih:** 19 Eylül 2026
**Dal:** `codex/character-quality-benchmark`
**Kapsam:** Ölçülmüş kod kalitesi incelemesi, bulunan gerçek hatalar ve dengeli
roadmap. Ürün kapılarının sırası için [roadmap](project/roadmap.md) ve
[pre-animation layer](operations/pre-animation-layer.md) geçerlidir.

Bu inceleme "kabul edilen borç" ile "gerçek aksiyon gereken" bulguyu ayırır.
Her satır bir kanıta dayanır; kanıtı olmayan hiçbir sayı burada yoktur.

---

## 1. Ölçülen baseline

| Kontrol | Sonuç |
|---|---|
| `python -m pytest tests -q -p no:cacheprovider` | **1249/1249 PASS** (96 sn) |
| `python -m ruff check .` (bu incelemede eklenen kapı) | **All checks passed** |
| Python | 3.10.11 (Windows); CI 3.10 + 3.11 matrisi |
| CI işleri | `lint`, `a9-windows-contract`, `python-and-real-render`, `remotion`, CodeQL |
| `cli/main.py` | 2582 satır |

Mimari temel sağlam: domain/port/adapter ayrımı gerçek, `config/provider_registry.py`
tek kompozisyon noktası, fail-closed kalite kapıları ve insan onay makbuzları
test edilmiş durumda. Aşağıdaki bulgular bu temeli sorgulamaz; borç ve boşlukları
listeler.

---

## 2. Bu incelemede bulunan ve düzeltilen gerçek hatalar

Üç tanesi **çalışma zamanında kesin hata** üreten gizli kusurlardı; üçü de
testlerin kapsamadığı yollarda duruyordu. Ruff'ın `F82` (tanımsız ad) kuralı
bu sınıfı görünür kıldı ve artık CI'da bloklayıcı.

| ID | Önem | Bulgu | Kanıt | Durum |
|---|---|---|---|---|
| R1 | Yüksek | `VideoMasteringService.apply_cinematic_mastering` hiç çalışamıyordu. Metot içindeki gereksiz `import os`, `os`'u tüm fonksiyon için yerel ad yapıyor; ilk `os.path.exists` satırı her çağrıda `UnboundLocalError` atıyordu. Modül düzeyinde `os` zaten import edilmişti. | `core/application/services/video_mastering_service.py:31` + F823 | **Düzeltildi** + regresyon testi |
| R2 | Yüksek | Metin→video fallback yolu tanımsız `i` kullanıyordu: `shot_contract_id=f"intent_{i}"`. O yol çalıştığında `NameError`. | `core/application/orchestration/pipeline_orchestrator.py:965` (F821) | **Düzeltildi** (`enumerate` ile `index`) |
| R3 | Yüksek | `cli/main.py` `_load_location_bible`'ı çağırıyor ama tanımlı/import edili değil; loader yalnız `cli/background_commands.py`'de. Konumlu episode planı çağrısı `NameError` verirdi. | `cli/main.py:1709` (F821) | **Düzeltildi** (yerel import) |
| R4 | Orta | Tip-yalnız adlar (`VideoGenerationPort`, `VisionSafetyGate`, `YoutubeUploadPort`, `RunRepositoryPort`, `PipelineOrchestrator`, `AudioInboxPort`, `AudioInboxJob`) `TYPE_CHECKING` bloğu olmadan kullanılıyordu. `from __future__ import annotations` sayesinde çalışma zamanı güvenliydi ama tip araçları için geçersizdi. | Aynı dosyalarda F821 | **Düzeltildi** (`TYPE_CHECKING` blokları) |

R2'de `intent_{index}` seçildi çünkü `VisualIntent`'in kararlı bir `id` alanı
yok; `enumerate` mevcut niyeti (sıralı çekim kimliği) korur.

---

## 3. Süreç ve kalite kapıları

| ID | Önem | Bulgu | Kanıt | Durum |
|---|---|---|---|---|
| R5 | Orta | CI'da hiçbir lint/typecheck yoktu; `.ruff_cache` ve `.mypy_cache` vardı ama `pyproject.toml`'da konfigürasyon ve iş yoktu. | `.github/workflows/quality-gates.yml` | **Düzeltildi** (ruff bloklayıcı `lint` işi) |
| R6 | Orta | `tmp/` `.gitignore` dışıydı ve içinde onlarca teşhis artifact'i ile bir teşhis scripti vardı. Kazara commit riski. Script'in hiçbir test/doküman referansı yoktu (orphan). | `git status`, `tmp/` içeriği | **Düzeltildi**: `tmp/` ignore; script `scripts/run_pose_identity_isolation.py` olarak kalıcılaştı |
| R7 | Orta | `RUNTIME_PROFILE` varsayılanı `offline-test` (hem `settings.py` hem `.env.example`). Prod çağrısı unutulursa sessizce deterministik fake provider seçilir; registry'deki koruma yalnız profil *açıkça* `production` iken ateşlenir. | `config/settings.py`, `config/provider_registry.py:472` | **Düzeltildi (uyarı)**: `warn_if_offline_test_profile`, `run_factory` ve `cli.main` girişlerinde çağrılıyor. Testleri bozmamak için hata değil, yüksek sesli uyarı. |
| R8 | Düşük | Sessiz yutmalar: `analytics_strategy_service.get_dashboard_stats` hatayı hiç loglamadan "Veri Yok" döndürüyordu; `system_monitor` GPU yoklamasını `except Exception: pass` ile yutuyordu. `app.py:321` ve Blender `benchmark_runner.py` çıplak `except:` kullanıyordu. | Ruff S110/E722 | **Düzeltildi** (log + daraltma) |

**R8 kapsamında yanlış pozitif düzeltmesi:** İlk tarama `search_cache_service`,
`vision_asset_scoring_service` ve `asset_selection_service`'i de "sessiz yutma"
saymıştı; tekrar okunduğunda üçünün de `logger.exception` ile loglayıp bilinçli
olarak devam ettiği görüldü (cache/vision fallback tasarımı). Bunlar borç değil,
kabul edilen davranıştır ve değiştirilmedi.

---

## 4. Kabul edilen borç ve açık işler

| ID | Önem | Bulgu | Kanıt / not |
|---|---|---|---|
| R9 | Bilgi | **LFS doğru uygulanmış.** `yolov8n.pt` gerçek bir LFS pointer'ı (`oid sha256:f59b3d83…`), venus `.mp4` setleri de LFS. Görsel PNG'ler 5 MB altı olduğu için politika gereği LFS dışı. Aksiyon gerekmiyor; policy sahada uygulanıyor. | `git cat-file`, `git check-attr` |
| R10 | Orta | **Devasa commit edilmemiş yığın.** 248 dosya: 55 değişik + ~60 untracked (yeni CLI modülleri, yeni servisler, tüm Character Bible'lar, benchmark PNG'leri, `models-flux2.lock.json`). Tek bir PR'a sığmaz; sahiplik/inceleme yükü yüksek. | `git status`, `git diff --stat` |
| R11 | Orta | **Python bağımlılık kilidi yok.** `requirements*.txt` hepsi `>=`; ağır GPU/model lib'leri (whisperx, insightface, ultralytics, gradio) serbest aralıkta. Yalnız `models.lock.json` / `models-flux2.lock.json` kilitli. | `requirements.txt` |
| R12 | Orta | **Lint ratchet'i henüz erken kademede.** Kalan set: `E402` 87, `F401` 63, `UP*` ~281, `I001` 261, `RUF100` 105, `BLE001` 32. Bugün bloklayıcı değil. | `ruff check --statistics` |
| R13 | Yüksek (ürün) | **Fonksiyonel boşluklar** (dokümanların kendi kaydettiği, kod gereci): çok-karakterli sahnede kimlik seçimi yok (`ep01`'de 25 çekimin 6'sı yanlış karakterle etiketli); profilde üç-çeyrek ayrımı ölçülemiyor; palette drift advisory; LivePortrait mock; ADR-009 Wan gerçek provider bloklu; pose-pack (5) ve keyframe (5) için **10 insan imzası bekliyor**. | `docs/project/status.md`, phase-1 roadmap |
| R14 | Düşük | **God dosya:** `cli/main.py` 2582 satır; `build_parser()` tek başına ~1000 satır. Yeni komutlar doğru şekilde `cli/*_commands.py`'ye taşınmış ama `main.py` hâlâ monolitik. | `wc -l`, `grep -n "^def "` |
| R15 | Düşük | **mypy advisory.** `[tool.mypy]` yapılandırıldı; CI'da `continue-on-error` ile çalışıyor. Bu oturumda mypy kurulu olmadığı için baseline doğrulanamadı; bu yüzden bloklayıcı yapılmadı. | `pyproject.toml`, CI `lint` işi |

---

## 5. Lint ratchet sırası

Bugünkü kapı yalnız **correctness** kurallarıdır ve sıfırdır:

```toml
select = ["E9", "F63", "F7", "F82", "F811", "F823", "E722"]
```

Bu set R1–R4 hatalarını bulduğu için değerini kanıtladı. Kademeli sıkılaştırma:

1. **`F` tamamı** — `F401` (63) ve `F841` (10). `F401`'lerin çoğu
   `__init__.py` re-export'u; `[tool.ruff.lint.per-file-ignores]` ile
   `__init__.py = ["F401"]` verilip kalanlar gerçek düzeltilir.
2. **I001 + UP* otomatik düzelt** — 542 adet, çoğu `ruff check --fix` ile
   güvenli. Tek seferde ayrı bir "chore: import ve annotation normalizasyonu"
   PR'ı olarak yapılmalı; WIP'e karıştırılmamalı.
3. **`E402`** — `scripts/*` içinde `sys.path` eklemesi sonrası import deseni
   meşru; `per-file-ignores` ile `scripts/* = ["E402"]`, uygulama kodunda
   gerçek düzeltme.
4. **`BLE001` / `S110` / `TRY*`** — sessiz yutmaları görünür kılan kural seti;
   R8'de elle başlatıldı, otomatik kurala bağlanması sonraki adım.
5. **mypy bloklayıcı** — baseline temizlendikten sonra `continue-on-error`
   kaldırılır.

---

## 6. Commit bölme stratejisi (yürütme onay gerektirir)

Mevcut yığın, `git add -A` kullanılmadan mantıksal parçalara ayrılır. Öneri:

1. `fix(core): remove os shadowing and undefined names` — bu incelemedeki R1–R4
   + regresyon testi + ruff kapısı. **En önce, tek başına.**
2. `feat(character): split view-pack generation and approval`
3. `feat(character): FLUX.2 Klein source-led edit dialect`
4. `feat(pose): yaw-projected pose template rig + guide fix`
5. `feat(series): style lock, cast registry and character bibles`
6. `feat(preproduction): story approval and plan CLI`
7. `test/docs/chore`: bağımsız test ve doküman değişiklikleri.

Her commit yalnız kendi dosyalarını içerir. Bu inceleme hiçbir commit yapmadı;
dallanma başka ajanlarla paylaşıldığı için sahiplik kararı kullanıcıya bırakıldı.

---

## 7. Dengeli roadmap

Sıra hijyenden başlar çünkü R1–R3 sınıfı (tanımsız ad, gölgelenen global) her
yeni özellikte tekrar edebilir; kapı eklendiğinde bir daha sessizce geçemez.

### Aşama H1 — Hijyen (bu PR, tamamlandı)
- [x] R1–R4 gerçek hataları düzelt ve regresyon testi ekle.
- [x] Ruff correctness kapısını CI'a bağla (`lint` işi).
- [x] `tmp/` ignore; orphan teşhis scriptini `scripts/`'e taşı.
- [x] Sessiz/çıplak `except`'leri log + daralt.
- [x] `RUNTIME_PROFILE` fail-open'ı uyarıya bağla.
- [x] CI'a Python 3.11 uyumluluk matrisi ekle (3.10 EOL yaklaşıyor).

### Aşama H2 — Borç azaltma (sonraki 1–2 PR)
- [ ] R10: yığını §6'daki parçalara böl ve PR başına incele.
- [ ] R12: lint ratchet kademe 1–3.
- [ ] R11: `pip-tools`/`uv` ile `requirements*.lock` üret; CI kilidi kullansın.
- [ ] R15: mypy baseline'ını temizle ve kapıyı bloklayıcı yap.
- [ ] R14: `cli/main.py`'yi `cli/*_commands.py`'ye indirge.

### Aşama P1 — Pilot kapıları (ürün)
- [ ] R13: çok-karakterli sahnede kimlik seçimi (sahne başına bible).
- [ ] Pose-pack (5) ve keyframe (5) insan imzaları.
- [ ] LivePortrait mock'unu gerçek ya da açıkça kapsam dışı yap.
- [ ] ADR-009 Wan yürütme sözleşmesi (lease/fencing, staged graph, idempotent
      commit, recovery, bütçe).

### Aşama P2 — Ölçek (Aşama 2)
- [ ] Kiralık GPU worker ve `wan2.2-worker.json`.
- [ ] Episode paketleme; GPU/media için performans bütçeleri.
- [ ] Karakter/shot sürekliliği benchmark'larını genişlet.

---

## 8. Doğrulama

- `python -m pytest tests -q` → 1249 + yeni regresyon testi, yeşil.
- `python -m ruff check .` → temiz (proje config'i).
- CI `lint` işi ruff'ı bloklayıcı, mypy'yi advisory çalıştırır.
