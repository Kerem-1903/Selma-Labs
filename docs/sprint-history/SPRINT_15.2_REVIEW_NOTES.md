# Sprint 15.2 – AssetSelectionService Hardening & Optimization

## Değişiklikler

1. `top_k <= 0` durumu artık constructor'da `ValueError` ile engelleniyor (fail-fast).
2. `penalties` sözlüğü artık lazy allocation ile oluşturuluyor (`None` başlatılıp
   sadece bir ceza uygulandığında `dict()` yaratılıyor). Bu, ceza almayan adaylar
   için gereksiz dictionary allocation'ını ortadan kaldırıyor.

## Değiştirilen Dosyalar

- `core/application/services/asset_selection_service.py`
- `tests/unit/test_asset_selection_service.py`

## Git Diff

```diff
--- core/application/services/asset_selection_service.py
+++ core/application/services/asset_selection_service.py
@@ -14,6 +14,8 @@
     def __init__(self, rules: Sequence[SelectionRule], provider_window: int = 3, keyword_window: int = 15, top_k: int = 5):
         if any(not isinstance(r, SelectionRule) for r in rules):
             raise TypeError("All rules must be instances of SelectionRule")
+        if top_k <= 0:
+            raise ValueError("top_k must be greater than zero")
         self._rules = tuple(rules)
         self._provider_window = provider_window
         self._keyword_window = keyword_window
@@ -30,8 +32,8 @@
             adjusted_candidates = []
             for candidate in candidates:
                 total_penalty = 0.0
-                penalties = {}
+                penalties = None  # LAZY ALLOCATION: Sadece ceza varsa sözlük yaratılır
 
                 for rule in self._rules:
                     try:
@@ -43,6 +45,8 @@
 
                     p = max(0.0, min(1.0, p if math.isfinite(p) else 0.0))
                     if p > 0.0:
+                        if penalties is None:
+                            penalties = {}
                         penalties[rule.__class__.__name__] = p
                         total_penalty += p
```

```diff
--- tests/unit/test_asset_selection_service.py
+++ tests/unit/test_asset_selection_service.py
@@ -30,6 +30,12 @@
     with pytest.raises(ValueError):
         ProviderFatigueRule(float("nan"))
 
+def test_asset_selection_service_invalid_top_k():
+    with pytest.raises(ValueError, match="top_k must be greater than zero"):
+        AssetSelectionService([], top_k=0)
+    with pytest.raises(ValueError, match="top_k must be greater than zero"):
+        AssetSelectionService([], top_k=-5)
+
 def test_asset_reuse_rule():
     rule = AssetReuseRule(0.8)
```

## Değerlendirme

- `top_k <= 0` durumu engellendi; potansiyel out-of-bounds hataları önlendi.
- Lazy dictionary initialization ile ceza almayan adaylar için gereksiz
  dictionary allocation'ı ortadan kaldırıldı.
- Mimari, SOLID ve immutability kuralları korundu; public sözleşmeler değişmedi.
