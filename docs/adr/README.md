# Architecture Decision Records

Bu dizin, provider ve GPU entegrasyonundan önce bağlayıcı mimari kararları
saklar. ADR'ler mevcut kodun tüm ayrıntılarının uygulandığını değil, yeni
uygulamanın uyması gereken sözleşmeyi belirtir.

## Kararlar

- [ADR-009 — Wan Job Execution Contract ve Pre-GPU Koordinatör Mimarisi](ADR-009-wan-job-execution-contract.md)
  - Tek coordinator + birden fazla GPU slotu
  - `WAN_RENDER → OUTPUT_VERIFY → INTERPOLATE → INTERPOLATION_VERIFY → FINALIZE` job graph'ı
  - Lease, heartbeat, fencing token ve optimistic concurrency
  - Attempt-specific artifact, checksum ve idempotent final commit
  - Ayrı `WanCheckpointStorePort` / `WanArtifactStorePort` authority sınırı
  - JSON checkpoint/index recovery, prefix listing ve schema migration
  - Profil sürümleme, retry/fallback matrisi ve atomic budget admission
  - Provider bağımsız execution, lifecycle ve dar storage port'ları

## Durum notu

ADR-009 kabul edilmiş bir hedef sözleşmedir. Mevcut Wan pre-GPU prototipi bu
sözleşmenin bir kısmını uygular; ADR'nin §13 bölümündeki farklar gerçek
provider adapter'ına geçmeden önce kapatılmalıdır.
