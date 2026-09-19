# Reddedilen yaklaşımlar ve silinen ağırlıklar

Bu dosya **versiyonlanan** kayıttır. `output/diagnostics/rejected-approaches/`
klasörü `.gitignore` içindeki `output/` altında kaldığı için oradaki PNG/JSON
kanıtları yalnız yerel diskte durur; kalıcı bilgi (neden vazgeçtik, hangi
ağırlıklar silindi, nasıl geri getirilir) burada tutulur.

Bu dosyadaki hiçbir yaklaşım production çıktısı değildir, golden set'e alınmaz,
LoRA/eğitim verisi olarak kullanılmaz ve hiçbir kabul (acceptance) listesinde yer
almaz.

## 1. Neden bırakıldı

Bu yöntemlerin hiçbiri, tek bir onaylı Kaito görselinden ölçülebilir biçimde aynı
karakterin dönüş (turnaround) açılarını üretemedi. Sorun prompt veya ayar değildi;
yöntemin kendisiydi. Bu yüzden kötü yöntemi prompt ve ayarlarla kurtarmaya
çalışmayı bıraktık.

| Yöntem | Sonuç | Artefakt (yerel kanıt) |
| --- | --- | --- |
| Qwen Image Edit 2511 | Kaynak kimliği korunmadı; profil açısı gerçek profil olmadı | `qwen-kaito-*.png` / `.json` |
| Qwen Image Edit — kısa/uzun prompt A/B | Prompt mühendisliği farkı kapatmadı | `qwen-kaito-clean-ab-*` |
| Qwen Image Edit — düşük denoise | Kimlik korundu ama açı üretmedi | `qwen-kaito-left-profile-low-denoise-2511.*` |
| Animagine / Illustrious (text-only) | Kimlik transferi yok | `kaito-animagine-ab-20260912b.json` |
| IP-Adapter + OpenPose ağırlık taraması | Ağırlık taraması kimlik/açı dengesini kurmadı | `kaito-ipadapter-profile-ab/` |
| Bu yöntemlerden "golden aday" | Reddedilen yöntemin çıktısı; golden set'e alınmadı | `kaito-profile-left-golden-candidate-v1.*` |
| Eski hattın model QC ölçümü | Eski motora ait ölçüm | `kaito-model-qc-20260912.json` |

**Şu an geçerli yöntem:** FLUX.2 Klein 4B FP8 kaynak-güdümlü görüntü düzenleme
(`comfyui-flux2-edit`), `models-flux2.lock.json` ile kilitli.

## 2. 2026-09-13: silinen ağırlıklar

Kullanıcı kararı: reddedilen yaklaşımların **ham ağırlıkları** diskten kaldırılır,
kanıt niteliğindeki çıktılar ve manifestler kalır. Ağırlıklar ya kamuya açık
modeller ya da doğrudan yeniden üretilebilir eğitim çıktısıdır; bu yüzden "kanıt"
değeri taşımazlar, yalnız yer kaplarlar.

| Kaldırılan | Boyut | Nerede | Kaynak / geri getirme |
| --- | --- | --- | --- |
| `Qwen-Image-Edit-runtime/` (tüm ağaç, 42.732 dosya) | 45996978664 B (42,84 GiB) | `~/Desktop/Qwen-Image-Edit-runtime` | HF `Qwen/Qwen-Image-Edit-2511` + DiffSynth-Studio çalışma zamanı |
| ↳ `downloads/model/qwen_image_edit_2511_int8_convrot.safetensors` | 20499083824 B | aynı | HF `Qwen/Qwen-Image-Edit-2511` |
| ↳ `downloads/text/qwen_2.5_vl_7b_fp8_scaled.safetensors` | 9384670680 B | aynı | aynı depo (metin kodlayıcı) |
| ↳ `downloads/vae/qwen_image_vae.safetensors` | 253806246 B | aynı | aynı depo (VAE) |
| ↳ `downloads/lora/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors.part` | 367013888 B | aynı | hiç tamamlanmadı; yarım indirme |
| ↳ `models/Qwen/Qwen-Image-Edit-2511/**/*.incomplete` (5 dosya) | 7533344256 B | aynı | hiç tamamlanmadı; artık indirme |
| ↳ `.venv/` (torch cu128 + bağımlılıklar) | kalan kısım | aynı | yeniden kurulabilir bağımlılık |
| `.cache/huggingface/hub/models--Qwen--Qwen-Image-Edit-2511` | < 1 MB (yalnız `refs/`) | `~` | yeniden indirilebilir |
| `models/ipadapter/ip-adapter-faceid-plusv2_sdxl.bin` | 1487555181 B (1,39 GiB) | `ComfyUI/models/ipadapter` | HF `h94/IP-Adapter-FaceID` |
| `models/loras/ip-adapter-faceid-plusv2_sdxl_lora.safetensors` | 371842896 B (355 MiB) | `ComfyUI/models/loras` | aynı depo |
| `models/checkpoints/Illustrious-XL-v2.0.safetensors` | 6938040674 B (6,46 GiB) | `ComfyUI/models/checkpoints` | HF `OnomaAIResearch/Illustrious-XL-v2.0`<br>sha256 `c2a1a3eaa13d4c107dc7e00c3fe830cab427aa026362740ea094745b3422a331` |
| `models/checkpoints/sdpose_wholebody_fp16.safetensors` | 1916645792 B (1,78 GiB) | `ComfyUI/models/checkpoints` | Comfy-Org SDPose model deposu |

Toplam serbest bırakılan alan: **≈ 53,6 GB** (≈ 49,9 GiB).

`ip-adapter-faceid-plusv2_sdxl_lora.safetensors` bir IP-Adapter **LoRA**'sıdır,
karakter LoRA'sı değildir — LoRA verisi üretme fikriyle karıştırılmamalı.

### Silinmeyen, kanıt olarak saklanan yerel ağırlık

`selma-akira-v1-preview.safetensors` (42869516 B, 2026-09-02 20:06) yerel olarak
üretildiği ve yeniden indirilemeyeceği için **silinmedi**; aktif ComfyUI `loras/`
klasöründen çıkarılıp yanlışlıkla yüklenemeyeceği bir yere taşındı:

```
output/diagnostics/rejected-approaches/weights/selma-akira-v1-preview.safetensors
```

Türkiye'de üretim hattına girmez; "bu yöntemden LoRA verisi üretme" fikrinin
somut kalıntısı olarak durur.

## 3. Ad karışıklığı uyarısı — `qwen`

Diskte "qwen" geçen iki **farklı** şey var ve biri silinemez:

| Dosya | Rol | Durum |
| --- | --- | --- |
| `ComfyUI/models/text_encoders/qwen_3_4b.safetensors` (8044982048 B) | **FLUX.2 Klein'ın metin kodlayıcısı** — `models-flux2.lock.json` 2. girdi | **Saklanır.** Silinirse FLUX tamamen çalışmaz |
| `Qwen-Image-Edit-runtime/**/qwen_*.safetensors` | Reddedilen Qwen Image Edit 2511 hattı | Silindi (bkz. §2) |

Ad benzerliği yüzünden "qwen'i sil" işlemi FLUX'u götürebilir; silme yalnızca
runtime klasörüyle sınırlı tutuldu.

## 4. Bilinçli olarak korunan SDXL yığını

`models.lock.json` içindeki SDXL yığını (`animagine-xl-4.0-opt`,
`ip-adapter-plus_sdxl_vit-h`, `CLIP-ViT-H-14-laion2B-s32B-b79K`,
`control-lora-openposeXL2-rank256`, iki detektör) ve `mm_sdxl_v10_beta.ckpt`
(i2v) **silinmedi**. FLUX.2 Klein bir *editör*dür — kaynak görsel ister, metinden
görsel üretemez. `storyboard.keyframe` ve `character.pose_pack` yeteneklerinin tek
motoru bu SDXL yığınıdır; silinirse iki yetenek motorsuz kalır.

`config/model_profiles/illustrious-xl-v2.lock.json` artık `retired: true` taşır:
ağırlığı diskte olmadığı için o profil üretimde kullanılamaz ve preflight'ı
**gürültülü biçimde** düşürür (sessizce eski bir yola düşmez).

## 5. Bu kaydı koruyan testler

- `tests/unit/test_character_edit_dialect_chaining.py::test_rejected_approaches_directory_is_documented_evidence`
- `tests/unit/test_character_edit_dialect_chaining.py::test_no_acceptance_or_benchmark_config_sources_a_rejected_approach`
- `tests/unit/test_character_edit_dialect_chaining.py::test_flux_evidence_never_lands_in_the_rejected_folder`
- `tests/unit/test_character_edit_dialect_chaining.py::test_rejected_approach_weights_are_recorded_and_retired`
