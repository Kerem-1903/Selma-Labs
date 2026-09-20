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
| `python -m pytest tests -q -p no:cacheprovider` | **1246/1246 PASS** (72–84 sn) |
| `python -m ruff check .` (bu incelemede eklenen kapı) | **All checks passed** (kademe 2 seçimi) |
| Python | 3.10.11 (Windows); CI 3.10 + 3.11 matrisi |
| CI işleri | `lint`, `a9-windows-contract`, `python-and-real-render`, `remotion`, CodeQL |
| `cli/main.py` | 1580 satır (parser çıkarılmadan önce 2585) |
| `cli/parsers/` | 1100 satır: `series`, `character`, `episode`, `production` aile kurucuları |

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

### Kademe 2 geçişinde bulunan gerçek hatalar

mypy kapısı açıldığında, `config/provider_registry.py`'nin seçtiği iki adaptörün
**hiç örneklenemediği** ortaya çıktı: port sözleşmesindeki abstract üyeler eksik
di, dolayısıyla o dallar `TypeError` ile ölüyordu.

| ID | Önem | Bulgu | Kanıt | Durum |
|---|---|---|---|---|
| R16 | Yüksek | `SelmaGPTScenePlanningProvider` `provider_identity`'yi tanımlamıyordu; `ScenePlanningPort` bunu abstract ister. `scene_planning_provider = "selmagpt"` seçilirse sınıf örneklenemez, `TypeError: Can't instantiate abstract class`. | `infrastructure/providers/scene_planning/selmagpt_scene_planning_provider.py` | **Düzeltildi** (`provider_identity` eklendi) |
| R17 | Yüksek | `SelmaGPTTranslationProvider` hem `provider_identity` hem de portun asıl metodu olan `translate_texts`'i eksikti; yalnız tekil `translate_text` vardı. `translation_provider = "selmagpt"` dalı örnekleme anında ölüyordu. | `infrastructure/providers/translation/selmagpt_translation_provider.py` | **Düzeltildi** (ikisi de eklendi; sıra ve uzunluk korunuyor) |

Aynı geçişte iki kablolama kusuru da görünür oldu: `ResilientSearchProviderDecorator`
bir `VideoSearchProvider` protokolü bekliyor ama registry ona `VideoSourcePort`
veriyordu (iki protokolün `search` imzaları farklı), ve `SearchCacheService`
sarmalayıcısı protokolün istediği `name` özelliğini hiç sunmuyordu. Sarmalayıcıya
`name` eklendi; dekoratör çağrısı gerekçesiyle `cast` edildi, çünkü protokolün
istediği `name`/`**kwargs` çağrıları somut sağlayıcılarda karşılanıyor ama port
daha dar bir imza ilan ediyor.

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
| R11 | Orta | **CI bağımlılık kilidi üretildi.** `requirements-ci.lock.txt` (96 pin) `pip-compile` ile derlendi ve 3.10 işi artık onu kuruyor; `requirements-ci.txt` insan tarafından düzenlenen girdi olarak kaldı ve kilidin nasıl yenileneceğini başlığında yazıyor. 3.11 işi bilinçli olarak gevşek dosyayı kurar (uyumluluk sinyali). GPU çalışma zamanı seti (`requirements.txt`: whisperx, insightface, ultralytics, gradio) hâlâ kilitsiz — o setin derlenmesi bir Linux/GPU makinesi istiyor. | `requirements-ci.lock.txt` |
| R12 | Orta | **Lint ratchet'i kademe 2'de ve bloklayıcı.** Kademe 1 yalnız correctness kurallarıydı; kademe 2 `F`, `I`, `UP`, `B`, `E4`, `S110`/`S112` ile ağacı temiz tutuyor. Kapalı kalanlar gerekçesiyle `ignore` listesinde: `B008`, `B904`, `B905`. | `pyproject.toml`, §5 |
| R13 | Yüksek (ürün) | **Fonksiyonel boşluklar** (dokümanların kendi kaydettiği, kod gereci): çok-karakterli sahnede kimlik seçimi yok (`ep01`'de 25 çekimin 6'sı yanlış karakterle etiketli); profilde üç-çeyrek ayrımı ölçülemiyor; palette drift advisory; LivePortrait mock; ADR-009 Wan gerçek provider bloklu; pose-pack (5) ve keyframe (5) için **10 insan imzası bekliyor**. | `docs/project/status.md`, phase-1 roadmap |
| R14 | Düşük | **God dosya — yarısı çözüldü.** `build_parser()`'ın 1016 satırı `cli/parsers/` ailelerine taşındı; `cli/main.py` 2585 → 1580 satır ve artık yalnız dispatcher + handler gövdesi. Kalan iş: handler'ları `cli/*_commands.py`'ye indirmek. Taşımanın davranış-nötr olduğu kanıtlandı: `build_parser()`'ın `format_help()` çıktısı ve her argümanın `dest`/`option_strings`/`default`/`nargs`/`choices` kümesi taşımadan önce ve sonra **aynı** (251 KB JSON karşılaştırması). | `wc -l`, `cli/parsers/` |
| R15 | Düşük | **mypy tüm üretim Python'unda bloklayıcı.** Baseline 200 hataydı; `core`, `infrastructure`, `config` ve `cli` sıfırlandı ve tek bloklayıcı kapıya alındı. Geçiş, tip düzeltmelerinin yanında üç gerçek sözleşme kusuru buldu: olmayan tek-varlık vision skoru çağrısı, yanlış ComfyUI çağrı imzası ve gölgelenen çift `_save_locked_asset` tanımı. | `pyproject.toml`, CI `lint` işi |

---

## 5. Lint ratchet sırası

**Kademe 1 (tarihsel):** yalnız correctness — `E9`, `F63`, `F7`, `F82`, `F811`,
`F823`, `E722`. Bu set R1–R4 hatalarını bulduğu için değerini kanıtladı.

**Kademe 2 (bugünkü kapı, bloklayıcı):**

```toml
select = ["B", "E4", "E9", "E722", "F", "I", "S110", "S112", "UP"]
ignore = ["B008", "B904", "B905"]
[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]   # re-export bir kullanımdır, ölü import değil
"scripts/*" = ["E402"]    # betikler sys.path'i import'tan önce kurar
```

Ölçülmüş geçiş:

| Adım | Sayı | Yöntem |
|---|---|---|
| `F`, `I`, `UP` (import sırası, annotation modernizasyonu, ölü import) | 600 bulgu | `ruff check --fix`, 273 dosya |
| Otomatik düzeltilemeyen kalıntı | 11 bulgu | elle: `UP031`, `UP035`, `I001`, `F841` (8) |
| `B` (bugbear) | 9 bulgu | `B007` yeniden adlandırma, `B009` otomatik, `B023` closure düzeltmesi |
| `E4` | 86 bulgu | `scripts/*` gerekçeli ignore, `app.py` yerel `noqa`, e2e import'u başa alındı |
| `S110`/`S112` | 3 bulgu | iki sessiz yutma log'a bağlandı, test `pytest.raises`'a çevrildi |

Kademe 2'nin bulduğu gerçek kusur: `scripts/run_pose_identity_isolation.py`
`with_identity` closure'ı döngü değişkeni `base`'i bağlamıyordu (`B023`) — her
varyant son iterasyonun isteğini üretebilirdi. Şablon artık varsayılan argümanla
bağlanıyor.

**Kademe 2b (mypy):** aynı geçişte tip kapısı açıldı.

```toml
[tool.mypy]
files = ["core", "infrastructure", "config", "cli"]
follow_imports = "silent"  # üçüncü taraf paket içlerini raporlama
```

| Ölçüm | Önce | Sonra |
|---|---|---|
| Üretim Python'u hatası | 200 / 63 dosya | **0** |
| Kapı kapsamı | 228 dosya, dar katmanlar | **`core` + `infrastructure` + `config` + `cli`** |
| Kapı | Kısmen `continue-on-error` | **tamamı bloklayıcı** |

Son genişletme `core/application` ve `infrastructure` borcunu sıfırladı. Özellikle
`VisionSafetyGate`'in somut serviste bulunmayan `score_asset` metodunu çağırdığı
ve `HybridBRollProvider`'ın ComfyUI portuna `VideoGenerationRequest` yerine
`prompt=` gönderdiği görüldü; her ikisi de seçildiklerinde çalışma zamanı hatasıydı.

**Sonraki kademeler:**

1. **`SIM`** (38 bulgu) ve **`S` bandit setinin geri kalanı** — sırayla.
2. **`B904`** — 16 `raise` site, her biri elle `raise ... from` kararı; otomatik
   düzeltme hata zincisini gizlediği için bilinçli olarak kapalı.
3. **`B905`** — 38 `zip`; her çağrının uzunluk sözleşmesi ayrı ayrı kararlaştırılıp
   `strict=` ile yazılmalı, toplu değiştirme değil.
4. **`RUF100`** bilinçli olarak kapalı: `# noqa: BLE001 - CLI boundary` gibi
   kayıtlar niyet belgeler; `RUF100` bunları "kullanılmayan" sayıp siler.
5. **mypy için sıradaki sınır** — üretim ağacı tamamlandı; yalnız bağımsız
   teşhis/operasyon betikleri tip kapısının dışında. Bunlar davranış sözleşmeleri
   netleştikçe ayrı bir `scripts` kapısına alınabilir.

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

### Aşama H2 — Borç azaltma (devam ediyor)
- [x] R10: yığın tek commit olarak indi (§6); bundan sonrası PR başına.
- [x] R12: lint ratchet kademe 2 — ağaç temiz ve kapı bloklayıcı (§5).
- [x] R11: `requirements-ci.lock.txt` üretildi ve 3.10 CI işi onu kuruyor;
      GPU çalışma zamanı kilidi ayrı bir makine istiyor (açık madde).
- [x] R15: mypy kapısı `core`, `infrastructure`, `config` ve `cli` genelinde
      bloklayıcı; üretim Python'u borcu sıfır.
- [~] R14: `build_parser()` `cli/parsers/`'e taşındı, `main.py` 2585 → 1580;
      kalan iş handler'ları `cli/*_commands.py`'ye indirmek.

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

- `python -m pytest tests -q` → **1249/1249 PASS** (3 yeni CLI yüzeyi testi).
- `python -m ruff check .` → temiz (kademe 2 seçimi, `pyproject.toml`).
- `python -m mypy` → **Success: no issues found** (`core`, `infrastructure`,
  `config`, `cli`; tamamı bloklayıcı).
- `requirements-ci.lock.txt` çözülebilirliği `pip install --dry-run` ile
doğrulandı (96 pin).
- CLI taşıması davranış-nötr kanıtlandı: `build_parser()` `format_help()` çıktısı
  ve argüman şeması önce/sonra birebir aynı (251 KB şema dökümü karşılaştırması).
- CI `lint` işi ruff'ı ve üretim ağacının tamamındaki mypy'yi bloklayıcı çalıştırır.
