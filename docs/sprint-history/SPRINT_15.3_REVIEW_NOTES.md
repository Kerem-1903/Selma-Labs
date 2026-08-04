# Sprint 15.3 – AdjustedAssetScore Encapsulation Fix

## Değişiklikler

`_EMPTY_PENALTIES` singleton'ının `AssetSelectionService`'e import edilmesi,
Domain Value Object ile Application Layer arasında istenmeyen bir coupling
yaratıyordu. Bu sprintte:

1. `AdjustedAssetScore.penalties` alanı `Mapping[str, float] | None` olarak
   güncellendi; servis artık `None` veya boş/dolu bir `dict` gönderebilir.
2. Singleton proxy'ye (`_EMPTY_PENALTIES`) çevirme mantığı tamamen
   `AdjustedAssetScore.__post_init__` içine taşındı. Servis bu detaydan
   habersiz.
3. `AssetSelectionService` artık `_EMPTY_PENALTIES`'i import etmiyor;
   sadece `pens` değerini (ki `None` olabilir) doğrudan value object'e
   iletiyor.

## Değiştirilen / Eklenen Dosyalar

- `core/domain/value_objects/adjusted_asset_score.py` (güncellendi)
- `core/application/services/asset_selection_service.py` (güncellendi)

## Git Diff

```diff
--- core/domain/value_objects/adjusted_asset_score.py
+++ core/domain/value_objects/adjusted_asset_score.py
@@ -10,10 +10,10 @@
 @dataclass(frozen=True)
 class AdjustedAssetScore:
     original: ScoredAsset
-    penalties: Mapping[str, float]
+    penalties: Mapping[str, float] | None
     adjusted_score: float
 
     def __post_init__(self):
-        if not self.penalties:
+        if not self.penalties:  # Handles both None and {}
             object.__setattr__(self, "penalties", _EMPTY_PENALTIES)
         else:
```

```diff
--- core/application/services/asset_selection_service.py
+++ core/application/services/asset_selection_service.py
@@ -4,7 +4,7 @@
 from typing import Sequence
 from core.domain.value_objects.scene import Scene
 from core.domain.value_objects.scored_asset import ScoredAsset
-from core.domain.value_objects.adjusted_asset_score import AdjustedAssetScore, _EMPTY_PENALTIES
+from core.domain.value_objects.adjusted_asset_score import AdjustedAssetScore
 from core.domain.value_objects.selection_context import SelectionContext
 from core.application.selection.selection_rule import SelectionRule
 
@@ -58,7 +58,7 @@
             top_candidates = adjusted_candidates[:self._top_k]
             
             final_scene_candidates = [
-                AdjustedAssetScore(original=cand, penalties=_EMPTY_PENALTIES if pens is None else pens, adjusted_score=adj)
+                AdjustedAssetScore(original=cand, penalties=pens, adjusted_score=adj)
                 for adj, cand, pens in top_candidates
             ]
```

## Değerlendirme

- Domain Layer artık kendi optimizasyon detaylarını (singleton proxy) dış
  dünyaya sızdırmıyor.
- Application Layer, private `_EMPTY_PENALTIES` değişkeninden habersiz;
  sadece `None` ya da bir `dict` gönderiyor.
- Encapsulation ve Clean Architecture sınır ihlali giderildi; public
  sözleşmeler ve davranış değişmedi.
