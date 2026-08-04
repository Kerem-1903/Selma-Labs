# Sprint 15.1 – AssetSelectionService (Baseline Architecture)

Bu, 15.2 (Performance/GC hardening) ve 15.3 (Encapsulation fix) öncesindeki,
mimarinin ilk defa oturtulduğu saf ve temel versiyondur.

## Kapsam

- `top_k` parametresi yok — tüm adaylar sıralanıp döndürülür.
- `penalties` sözlüğü her zaman eager olarak oluşturulur (lazy allocation yok).
- Sıralama, doğrudan `AdjustedAssetScore` objeleri üzerinden yapılır
  (15.2'deki primitive-tuple optimizasyonu henüz yok).
- `AdjustedAssetScore.penalties`, singleton `_EMPTY_PENALTIES` proxy'si
  olmadan her zaman `MappingProxyType(dict(...))` ile sarılır.

## Dosyalar

- `config/settings.py` — seçim/ceza ayarları
- `core/domain/value_objects/selection_context.py`
- `core/domain/value_objects/adjusted_asset_score.py`
- `core/application/selection/selection_rule.py`
- `core/application/selection/rules/asset_reuse_rule.py`
- `core/application/selection/rules/provider_fatigue_rule.py`
- `core/application/selection/rules/keyword_fatigue_rule.py`
- `core/application/services/asset_selection_service.py`
- `core/application/services/scene_asset_matching_service.py` (entegrasyon snippet'i)
- `tests/unit/test_asset_selection_service.py`

## Sonraki Sprintler

- **15.2**: `top_k` sınırlaması + fail-fast `ValueError`, lazy `penalties`
  allocation (GC/performans optimizasyonu), primitive tuple sıralaması.
- **15.3**: `_EMPTY_PENALTIES` singleton mantığının `AdjustedAssetScore`
  içine taşınması (encapsulation düzeltmesi).

Not: `MediaAsset`, `ScoredAsset`, `AssetScore`, `Scene`, `VideoSearchService`,
`AssetScoringService` gibi bazı destek sınıfları bu sprintte paylaşılmadı;
yukarıdaki dosyalar bunları import ediyor ama tanımları ayrı modüllerde
bulunuyor.
