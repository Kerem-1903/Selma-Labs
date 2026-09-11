# ADR-009: Wan Job Execution Contract ve Pre-GPU Koordinatör Mimarisi

- **Durum:** Kabul edildi; gerçek provider/GPU adapter'ı için ön koşul
- **Kapsam:** Wan üretimi, çıktı doğrulama, interpolation ve finalizasyon
- **İlgili kararlar:** ADR-006, ADR-007, ADR-008

## Bağlam

Mevcut Wan yolu, tek bir `WanRenderJob` etrafında render ve doğrulama
çalıştıran bir pre-GPU prototipidir. Gerçek provider ve GPU slotları devreye
girmeden önce job graph'ının semantiği, kalıcı checkpoint, lease, fencing,
çıktı commit'i ve maliyet admission davranışı bağlayıcı bir sözleşme olarak
sabitlenmelidir.

Bu ADR, **en az bir kez execution + idempotent commit** modelini seçer. Gerçek
"exactly once" execution garanti edilmez; eski veya geç kalan worker'ın yeni
sonucu bozması fencing ve conditional commit ile engellenir.

## 1. Çalışma modeli: tek coordinator

Dağıtım modeli **tek coordinator process + birden fazla GPU slotu** olarak
kilitlenmiştir. Coordinator, dinamik kuyruğu paylaşan slot worker'larını
çalıştırır; bir slot uzun süren job ile meşgulken diğer slotlar başka job'ları
claim edebilir.

- JSON checkpoint repository, tek coordinator'ın sahip olduğu kuyruk için
  yeterlidir.
- Process içi lock yalnızca aynı coordinator'ın eşzamanlılığını korur;
  cross-process atomic claim garantisi değildir.
- Aynı queue kökünü kullanan ikinci coordinator, coordinator ownership lock
  nedeniyle **fail closed** başlatılır.
- Birden fazla coordinator/process ihtiyacı doğarsa JSON ve process içi lock
  terk edilir. PostgreSQL, Redis veya eşdeğer atomic claim/CAS/lease sağlayan
  bir persistence kararı alınmadan bu model genişletilemez.

"Birden fazla GPU slotu" ile "birden fazla coordinator" farklı kavramlardır:
ilkine izin verilir, ikincisi bu ADR'nin kapsamı dışındadır.

## 2. Job graph ve staged-node yaşam döngüsü

Bir shot için kanonik graph şöyledir:

```text
WAN_RENDER
  -> OUTPUT_VERIFY
  -> INTERPOLATE
  -> INTERPOLATION_VERIFY
  -> FINALIZE
```

`INTERPOLATE` ve `INTERPOLATION_VERIFY`, profilin postprocess zinciri bunları
gerektiriyorsa graph'a dahil edilir. Gerektirmeyen profil bu iki node'u
oluşturmaz; `FINALIZE` yine kendi input contract'ını doğrulamadan çalışamaz.

### 2.1 Tek state modeli

Bu graph'ta `VERIFYING` status'ü yoktur. **Her graph node kendi bağımsız
`PENDING/RUNNING/COMPLETED` yaşam döngüsüne sahiptir.** `WAN_RENDER` yalnızca
attempt artifact ve manifest üretir; `OUTPUT_VERIFY` doğrulama manifesti
üretir; `FINALIZE` conditional promote yapar. Böylece bir node'un iç adımı
başka bir node'un status'üyle karıştırılmaz.

Her node ayrıca `RETRY_REQUIRED`, `FAILED`, `WAITING_DEPENDENCY`, `BLOCKED`
ve `HUMAN_REVIEW_REQUIRED` durumlarından birinde olabilir. `COMPLETED`, yalnızca
o node'un kendi output contract'ı ve checkpoint commit'i tamamlandığında
verilir.

### 2.2 Ortak job alanları

| Alan | Sözleşme |
|---|---|
| `job_id` | Kalıcı, portable, benzersiz node kimliği |
| `job_type` | `WAN_RENDER`, `OUTPUT_VERIFY`, `INTERPOLATE`, `INTERPOLATION_VERIFY` veya `FINALIZE` |
| `shot_id` | Node'un ait olduğu shot |
| `profile_version` | Örn. `draft_16fps@v1`; node oluşturulduktan sonra değişmez |
| `dependencies` | Tamamlanması gereken job ID listesi |
| `input_storage_keys` | Portable key listesi/map'i; fiziksel path içermez |
| `output_storage_key` | Node'un output veya final logical key'i |
| `attempt_count` | Claim edilmiş execution attempt sayısı |
| `max_attempts` | Node için izin verilen attempt sayısı |
| `priority` | Küçük sayı daha yüksek önceliktir; tie-break deterministic'tir |
| `estimated_cost` | Birim ve para birimi açık tahmini maliyet |
| `idempotency_key` | Aynı logical node execution'ını tanımlayan benzersiz anahtar |

Ayrıca her node şunları taşır:

- immutable `profile_snapshot` veya profile digest;
- `created_at`, `updated_at`, `revision`;
- `failure_code`, redakte `failure_detail`, immutable `retry_policy`;
- `blocked_reason` gerektiğinde;
- `lease_id`, `lease_expires_at`, `heartbeat_at`, `worker_id`, `attempt_id`,
  `fencing_token`;
- `estimated_runtime_seconds`, `actual_runtime_seconds`, `reserved_cost`,
  `actual_cost`, `cost_reconciliation_status`;
- fallback node'ları için `parent_job_id`/`fallback_of`.

Job graph, node ID ve dependency listelerinden yeniden kurulabilir; queue index
yalnızca hızlandırıcıdır ve graph'ın otoritesi değildir.

## 3. State machine

### 3.1 Geçiş tablosu

| Mevcut durum | İzin verilen sonraki durum | Koşul |
|---|---|---|
| `PENDING` | `RUNNING` | Dependency'ler tamam, budget admission başarılı ve atomic claim tamamlandı |
| `PENDING` | `WAITING_DEPENDENCY` | Upstream node henüz tamamlanmadı |
| `PENDING` | `BLOCKED` | Claim öncesi budget/model/operasyon engeli kesinleşti |
| `WAITING_DEPENDENCY` | `PENDING` | Tüm dependency'ler `COMPLETED` oldu |
| `WAITING_DEPENDENCY` | `BLOCKED` | Upstream node terminal başarısız oldu veya graph geçersizleşti |
| `RUNNING` | `COMPLETED` | Node'un kendi output contract'ı ve checkpoint commit'i tamamlandı |
| `RUNNING` | `RETRY_REQUIRED` | Retry edilebilir execution, lease veya geçici doğrulama hatası |
| `RUNNING` | `FAILED` | Retry hakkı tükendi veya retry edilemeyen teknik hata |
| `RUNNING` | `BLOCKED` | Çalışma sırasında çözülemeyen admission/cost/model engeli |
| `RETRY_REQUIRED` | `RUNNING` | Yeni budget reservation ve atomic re-claim tamamlandı |
| `RETRY_REQUIRED` | `FAILED` | Retry policy daha fazla attempt'e izin vermiyor |
| `RETRY_REQUIRED` | `BLOCKED` | Yeni attempt admission için kalıcı engel var |
| `BLOCKED` | `PENDING` | Operatör veya sistem engeli açıkça çözdü; yeni revision/event üretildi |
| `COMPLETED` | — | Node terminaldir; yeniden çalıştırma yeni node/job graph gerektirir |
| `FAILED` | — | Terminaldir; yeniden çalıştırma yeni node/job graph gerektirir |
| `HUMAN_REVIEW_REQUIRED` | — | Yalnızca açık review akışı yeni job oluşturabilir |

Lease süresi dolan `RUNNING` node coordinator recovery sırasında
`RETRY_REQUIRED` olur. Geç worker'ın sonucu fencing nedeniyle kabul edilmez.

### 3.2 `BLOCKED` ve dependency bekleyişi

Upstream'in henüz tamamlanmamış olması **normal bekleyiştir**; `BLOCKED`
değildir. Claim edilemeyen node `WAITING_DEPENDENCY` durumunda kalır. Yalnızca
upstream terminal başarısızsa veya graph artık geçerli değilse
`BLOCKED(DEPENDENCY)` yapılır.

`BLOCKED`, dışarıdan çözülmesi gereken kesin bir engeldir. `blocked_reason`
şunlardan biridir:

- `DEPENDENCY`: upstream terminal başarısız veya graph geçersiz;
- `BUDGET`: proje/job/GPU saat bütçesi admission için yeterli değil;
- `MISSING_MODEL`: profile/model/workflow bulunamıyor;
- `COST_RECONCILIATION`: actual cost henüz güvenilir biçimde mutabık değil;
- `MANUAL_INTERVENTION`: güvenlik veya açık operasyon kararı gerekiyor.

`PENDING -> BLOCKED` claim öncesi kesin engellerde kullanılabilir.
`BLOCKED -> PENDING` yalnızca engel gerçekten giderildiğinde yapılır.

`status`, yalnızca yaşam döngüsünü ifade eder; `failure_code` makine sınıfını,
`failure_detail` redakte debug bilgisini, `retry_policy` ise job creation
anındaki immutable sonraki davranış sözleşmesini ifade eder.

## 4. Claim, lease, heartbeat ve fencing

Atomic claim her attempt için şunları üretir veya artırır:

- yeni `lease_id`;
- `lease_expires_at` ve başlangıç `heartbeat_at`;
- `worker_id` ve GPU `slot_id`;
- yeni `attempt_id`;
- monoton artan `fencing_token`;
- optimistic-concurrency `revision` artışı;
- aynı transaction içindeki budget reservation.

Protokol:

```text
admit_and_claim (budget + claim tek atomic repository işlemi)
  -> lease oluştur
  -> render boyunca heartbeat
  -> lease kaybedilirse sonucu commit etme
  -> yalnızca güncel fencing token ile output/checkpoint commit et
```

Heartbeat lease süresinin en geç üçte ikisi dolmadan gönderilir. API'nin
sözleşmesi şöyledir:

```text
heartbeat(
  job_id,
  lease_id,
  attempt_id,
  fencing_token,
  expected_revision,
  requested_lease_extension
) -> HeartbeatResult(
  accepted,
  revision,
  lease_expires_at,
  heartbeat_at,
  fencing_token
)
```

Kabul edilen heartbeat `revision` değerini artırır ve **yeni revision ile
uzatılmış `lease_expires_at` değerini döndürür**. Worker sonraki conditional
write için dönen revision'ı kullanır; ilk heartbeat'teki stale
`expected_revision` tekrar kullanılmaz. Lease/fencing uyuşmazlığı `accepted=false`
veya typed conflict sonucu üretir; worker output commit etmeyi bırakır.

Heartbeat ve tüm commit'ler `job_id + lease_id + attempt_id + fencing_token +
expected_revision` ile koşulludur. Eski worker'ın provider çağrısı hemen
kesilemese bile yalnızca attempt-specific key'e yazabilir; final key'e promote
ve `COMPLETED` checkpoint yazamaz.

## 5. Idempotency ve output commit

Execution en az bir kez olabilir; commit ve finalizasyon idempotent olmak
zorundadır.

Attempt key'leri:

```text
wan/attempts/{job_id}/{attempt_id}/render.mp4
wan/attempts/{job_id}/{attempt_id}/manifest.json
```

Final logical key:

```text
wan/final/{job_id}.mp4
```

Aynı attempt key zaten varsa artifact store byte size ve SHA-256 karşılaştırır:
eşleşiyorsa yeniden kullanılabilir, farklı artifact aynı key'e yazılamaz.
Yeni claim yeni `attempt_id` ve yeni attempt key'i üretir.

Node semantiği:

1. `WAN_RENDER` attempt artifact ve manifest'i artifact store'a yazar.
2. `OUTPUT_VERIFY` artifact HEAD/byte size/SHA-256 ve ffprobe/quality
   contract'ını kontrol eder; doğrulama manifestini output olarak commit eder.
3. Gerekliyse `INTERPOLATE` yeni attempt-specific artifact üretir.
4. `INTERPOLATION_VERIFY` aynı kontrolleri interpolated artifact için yapar.
5. `FINALIZE` doğrulanmış artifact'i güncel fencing token ile conditional
   promote eder; aynı fingerprint ile node checkpoint'ini `COMPLETED` yapar.

`FINALIZE` tamamlanmadan logical final key üretim çıktısı sayılmaz. Promote
sonrası checkpoint crash olursa reconciler yalnızca doğrulanmış manifest,
fingerprint ve geçerli fencing token eşleşiyorsa aynı commit'i tekrarlar.
Stale token ile yazılan artifact veya checkpoint kabul edilmez.

## 6. Kalıcı store port'ları ve authority

Genel `StoragePort` büyütülmez. Wan pipeline iki ayrı dar port kullanır:

### 6.1 `WanCheckpointStorePort`

Checkpoint store job state'in **tek otoritesidir**. En az şu semantiği sağlar:

```text
load(checkpoint_key)
list(prefix) -> checkpoint keys
put_if_revision(
  checkpoint_key,
  expected_revision,
  envelope
) -> CheckpointWriteResult(
  accepted,
  revision,
  checksum,
  conflict
)
acquire_coordinator_lock(owner_id, ttl)
renew_coordinator_lock(owner_id, ttl)
release_coordinator_lock(owner_id)
```

`put_if_revision` expected revision ile koşulludur; başarılı yazıda yazılan
revision ve checksum döner, conflict durumunda mevcut revision döner ve stale
writer state'i ezemez. Heartbeat de aynı CAS sözleşmesini kullanır.

### 6.2 `WanArtifactStorePort`

Artifact store job state'in otoritesi değildir. En az şu semantiği sağlar:

```text
put_if_absent_or_same(key, bytes, sha256, byte_size)
head(key) -> {exists, sha256, byte_size, metadata}
promote_if_fenced(source_key, final_key, fingerprint, fencing_token)
```

Aynı key'e farklı checksum yazılamaz. `head` byte size ve SHA-256 doğrulaması
olmaksızın `exists` sonucu completion kanıtı değildir. `promote_if_fenced`
final key'i yalnızca daha yeni veya aynı geçerli fencing token ve aynı
fingerprint ile güncelleyebilir.

Bu iki portun ayrılmasıyla local checkpoint authority ile object/artifact
storage arasında iki farklı job-state authority oluşmaz: checkpoint state'i
tek otoritedir; artifact store yalnızca immutable/conditional artifact
saklama ve promote sınırıdır.

## 7. JSON checkpoint, index ve migration

### 7.1 Authority seçimi

JSON repository v2, **mounted persistent volume üzerindeki checkpoint store**
ile sınırlıdır. Mevcut genel `StoragePort` prefix listing, HEAD ve CAS
sağlamadığı için object storage mirror'ı v2 checkpoint authority değildir.

İleride remote checkpoint store kullanılacaksa `WanCheckpointStorePort`
uygulaması zorunlu olarak `list(prefix)` ve conditional revision/CAS
sağlamalıdır. Local cache ve index birlikte kaybolduğunda job discovery ancak
bu prefix listing veya eşdeğer durable catalog ile yapılabilir; listing
olmayan object storage backend'i checkpoint store olarak kabul edilmez.

Queue index yalnızca cache'tir. Index kaybolur veya bozulursa authoritative
checkpoint store'daki tüm job checkpoint'lerinden yeniden oluşturulur.
Mounted volume baseline'ında bu, `*.json` dosyalarının taranmasıdır. Index'teki
stale ID, checkpoint yoksa claim edilemez.

### 7.2 Checkpoint envelope

Her node ayrı checkpoint'tir:

```json
{
  "schema_version": 2,
  "revision": 17,
  "committed": true,
  "checksum": "sha256-of-canonical-job-payload",
  "updated_at": "2026-09-10T12:00:00.000000Z",
  "job": {}
}
```

`committed=false` geçici yazım durumudur ve authoritative state olarak
okunamaz. Yazıcı unknown future schema'nın üzerine yazamaz.

Checkpoint yazımı CAS ile yapılır:

1. beklenen revision doğrulanır ve yeni revision atanır;
2. canonical payload ve checksum hesaplanır;
3. temp dosya UTF-8 olarak yazılır, flush/fsync yapılır;
4. atomic replace yapılır;
5. CAS sonucu ve yazılan revision doğrulanır;
6. index yalnızca checkpoint başarılı olduktan sonra güncellenir.

Remote store implementation'ı aynı semantic'i conditional put/ETag/CAS ile
sağlamalıdır; yalnızca "save" yapan mirror bu sözleşmeye uymaz.

### 7.3 Canonical checksum formatı

Checksum input'u `checksum` alanı hariç canonical `job` payload'ıdır. Format
kesin olarak şöyledir:

- JSON object key'leri lexicographic olarak `sorted keys` ile sıralanır;
- UTF-8 encode edilir;
- JSON separators compact olarak `(',', ':')` kullanılır;
- string'ler Unicode olarak korunur (`ensure_ascii=false`);
- timestamp'ler önce UTC'ye çevrilir ve tam olarak
  `YYYY-MM-DDTHH:MM:SS.ffffffZ` RFC3339 biçimine normalize edilir;
- finite float'lar RFC 8785/JCS shortest round-trip sayı biçimine normalize
  edilir; `-0.0` `0` olur, `NaN` ve `Infinity` reddedilir;
- aynı canonical input aynı SHA-256 digest'i üretir.

Bu canonicalizer plain `repr()` veya platforma bağlı `json.dumps` çıktısı
olamaz. Timestamp, float, nested key sıralaması ve Unicode için fixture testleri
zorunludur.

### 7.4 Migration ve retention

- Mevcut render prototype envelope'ı `schema_version=1`, bu sözleşmenin
  hedefi `schema_version=2`'dir.
- `v1 -> v2` migration açık, deterministik ve test edilebilir bir fonksiyondur.
- Migration öncesi checkpoint korunur; migration checksum/event'i yazılır.
- Varsayılan retention: attempt artifact'leri terminal durumdan 30 gün,
  terminal checkpoint'leri 180 gün, audit/event kayıtları 365 gün. Aktif veya
  review/reconciliation bekleyen node silinemez.

## 8. Profil sürümleme

Profil adı tek başına yeterli değildir:

```text
draft_16fps@v1
final_24fps@v1
```

Profile snapshot en az şunları içerir:

- frame count ve FPS;
- step count;
- scheduler/sampler;
- resolution;
- model revision;
- workflow hash;
- postprocess chain;
- verification policy version.

Job oluşturulurken profil adı, versiyonu ve snapshot digest'i node'a kopyalanır.
Registry değişse bile mevcut node'un anlamı değişmez.

4 -> 40 step fallback ordinary retry değildir. Manifest açıkça izin verirse
parent job'ın profilini mutate etmek yerine yeni profile snapshot, yeni child
job, yeni budget/attempt/lease/idempotency kaydı ve `fallback_of` dependency'si
oluşturulur. `PROFILE_FALLBACK_CREATED` event'i yazılır.

## 9. Retry ve fallback matrisi

| Hata | Retry | Profil değişir mi? | Son durum |
|---|---:|---:|---|
| Timeout | Evet | Hayır | `RETRY_REQUIRED` veya `FAILED` |
| Broken MP4 | Evet | Hayır | `RETRY_REQUIRED` veya `FAILED` |
| FFprobe failure | Evet | Hayır | `RETRY_REQUIRED` veya `FAILED` |
| Wrong FPS | Evet | Hayır | `RETRY_REQUIRED` veya `FAILED` |
| Wrong frame count | Evet | Hayır | `RETRY_REQUIRED` veya `FAILED` |
| Low visual quality | Evet | Hayır | `RETRY_REQUIRED` veya `FAILED` |
| Identity drift | Hayır | Hayır | `HUMAN_REVIEW_REQUIRED` |
| Motion artifact | Hayır | Hayır | `HUMAN_REVIEW_REQUIRED` |
| Budget exceeded | Hayır | Hayır | `BLOCKED` (`BUDGET`) |
| Missing model/workflow | Hayır | Hayır | `BLOCKED` (`MISSING_MODEL`) |
| Invalid dependency graph | Hayır | Hayır | `BLOCKED` (`DEPENDENCY`) |
| Actual cost unknown | Hayır | Hayır | `BLOCKED` (`COST_RECONCILIATION`) |

Retry policy node creation anında snapshot edilir. Her retry yeni attempt,
new budget reservation ve yeni attempt event'i üretir. Fallback yalnızca
`fallback_policy.allow_step_fallback=true` ve policy koşulları sağlandığında
ayrı child job olarak açılır.

`actual_cost` bilinmiyorsa `HUMAN_REVIEW_REQUIRED` kullanılmaz; bu yaratıcı
kalite incelemesi değildir. Node finalization'ı `BLOCKED(COST_RECONCILIATION)`
ile durur ve reliable provider usage veya açık reconciliation sonucu gelmeden
bütçe tamamlanmış sayılmaz.

## 10. Budget admission ve reconciliation

İş akışı kavramsal olarak şöyledir:

```text
estimate cost
  -> reserve budget
  -> claim job
  -> execute
  -> reconcile actual cost
```

Ancak tek coordinator JSON modelinde ilk iki adım **tek atomic repository
işlemidir**: `admit_and_claim(job_id, worker_id, slot_id, estimate)` repository
lock/CAS altında dependency, budget, expected revision ve lease'i birlikte
kontrol eder. Başarısız claim için kalıcı reservation bırakılmaz.

Reservation şu alanlara bağlanır:

- `job_id`, `attempt_id`, `idempotency_key`;
- `expected_revision` ve verilen `fencing_token`;
- project/job/GPU-hour budget bucket;
- `estimated_cost`, reservation expiry ve reconciliation status.

Kontrol edilen sınırlar proje toplam bütçesi, job başına maksimum maliyet,
GPU saat limiti, hard runtime ve retry/fallback attempt'lerinin toplamıdır.
Admission geçmezse job `BLOCKED(BUDGET)` olur; claim edilmez.

Provider/process crash'ında reservation lease/recovery kaydına bağlanır ve
reconciliation tamamlanana kadar ihtiyatlı tutulur. Actual usage elde edilince
reservation reconcile edilir, kullanılmayan miktar iade edilir. Retry yeni
attempt ve yeni reservation gerektirir; önceki attempt bedava sayılmaz.

Birden fazla coordinator hedeflenirse bu atomic admission+claim semantiği
JSON ile taşınamaz; distributed transaction/claim sağlayan yeni persistence
kararı gerekir.

## 11. Provider sınırları

Gerçek adapter'lar şu dar portların arkasında kalır:

1. **`WanExecutionPort`** — render başlatma, durum izleme, çıktı toplama ve
   iptal; account-wide API, ödeme veya instance listesi açmaz.
2. **`WanComputeLifecyclePort`** — yalnızca adapter'ın kendi instance'ını
   kapatma ve auto-stop durumunu raporlama.
3. **`WanCheckpointStorePort`** — job checkpoint, list, ownership lock ve CAS.
4. **`WanArtifactStorePort`** — attempt/final artifact, HEAD/checksum ve
   fencing'li conditional promote.

Genel `StoragePort` bu sözleşme için genişletilmez. Worker/application katmanı
provider SDK'sını veya credential'larını görmez; composition root yalnızca
bu port'ları inject eder.

Mevcut `WanWorkerProviderPort.render()` fake tabanlı pre-GPU test sınırıdır;
gerçek adapter, execution başlatma/izleme/iptal ve lease kaybı davranışlarını
`WanExecutionPort` semantiğine taşımadan production provider'ı sayılamaz.

## 12. Crash recovery matrisi

| Crash noktası | Recovery sonucu | Artifact kullanımı |
|---|---|---|
| Claim sonrası | Lease expiry sonrası node `RETRY_REQUIRED`; fencing artar | Artifact yoksa yeni attempt; varsa yalnızca manifest/head ile doğrulanır |
| Render sırasında | Provider execution orphan/recovery kaydı alır | Final key'e erişemez; tamamlanmamış attempt temizlenebilir |
| Upload sırasında | Artifact HEAD/checksum incelenir | Tam ve eşleşiyorsa yeniden upload edilmez; değilse yeni attempt |
| Upload + checkpoint crash | Reconciler manifesti ve checkpoint CAS'ı inceler | Verify başarılıysa aynı artifact yeniden kullanılır |
| Verification sırasında | Verify node yeniden claim edilir | Attempt artifact korunur; render tekrarlanmaz |
| Finalize promote + checkpoint crash | Fingerprint ve fencing ile reconciliation yapılır | Aynı fenced artifact idempotent biçimde commit edilir |
| Auto-stop sırasında | Stop başarısızlığı ayrı operasyon event'idir | Node sonuçları değişmez; drained queue'da stop yeniden denenir |

Recovery, dosya varlığına bakarak sessizce `COMPLETED` yazamaz; normal node
transition, CAS ve event üretmelidir.

## 13. Gözlemlenebilirlik ve güvenlik

Her attempt için dayanıklı yapılandırılmış event kaydı tutulur. Minimum event
türleri:

```text
JOB_CLAIMED
HEARTBEAT
RENDER_STARTED
RENDER_FINISHED
VERIFY_FAILED
OUTPUT_COMMITTED
JOB_RETRIED
INSTANCE_STOP_REQUESTED
```

Ortak correlation alanları:

- `job_id`, `attempt_id`, `worker_id`, `slot_id`;
- `provider_instance_id`, `lease_id`, `fencing_token`;
- `profile_version`, `event_id`, `event_type`, `occurred_at`.

Log/event payload'larında API key, bearer token, signed URL, secret, credential
veya hassas prompt bulunmaz. Debug ayrıntısı redakte edilir.

## 14. Uygulama sırası ve provider gate

Aşağıdaki sıra bağlayıcıdır; sonraki adım öncekinin contract testleri geçmeden
başlatılamaz:

1. Schema v2, `v1 -> v2` migration, canonical checksum ve revision/CAS.
2. Tek coordinator ownership lock.
3. Lease, heartbeat ve fencing; heartbeat response revision/expiry döndürür.
4. Attempt manifest, iki ayrı store portu ve idempotent conditional commit.
5. Staged graph ve node başına state machine (`VERIFYING` yok).
6. Atomic budget reservation/claim ve actual-cost reconciliation.

Gerçek provider credential'ı veya GPU instance'ı ancak bu altı aşama ve aşağıdaki
contract testleri geçtikten sonra bağlanabilir:

- stale writer/fencing ve heartbeat revision testleri;
- duplicate upload, HEAD/checksum ve conditional promote testleri;
- index rebuild/prefix listing, ownership lock ve migration testleri;
- dependency wait vs terminal dependency block testleri;
- concurrent slot admission/claim ve reservation rollback testleri;
- staged graph resume ve crash recovery testleri;
- retry/fallback/low-quality/cost-reconciliation matrix testleri.

## Sonuç

SELMA Labs'in Wan üretim sınırı; **tek coordinator + N GPU slotu**, her node'un
kendi lifecycle'ına sahip staged graph, `WAITING_DEPENDENCY` ile gerçek
`BLOCKED` ayrımı, lease/heartbeat/fencing korumalı claim, en az bir kez
execution, idempotent attempt/final commit ve claim ile atomik budget
admission olarak sabitlenmiştir.

JSON repository yalnızca `WanCheckpointStorePort` olarak mounted persistent
volume üzerinde geçerlidir. Artifact'ler `WanArtifactStorePort` arkasındadır.
Çoklu coordinator veya prefix listing/CAS sağlamayan remote checkpoint ihtiyacı
doğduğu anda yeni distributed persistence kararı zorunludur.
