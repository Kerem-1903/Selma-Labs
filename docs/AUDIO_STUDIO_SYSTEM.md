# SELMA Audio Studio System

Status: production architecture complete; measured reference master passes the
automatic release gate at **90/100 (9.0/10)**. A recorded human review of voice
performance can raise the same report to 100/100.

Verification date: 2026-08-14. Prices and plan terms below must be rechecked
before purchase.

## What the system now owns

- Pre-synthesis narration normalization and an auditable Turkish/English
  pronunciation lexicon.
- Content-specific voice direction: pace, stability, expression, hook,
  explanation, payoff, and maximum-pause policy.
- A time-coded sound-design plan generated from narrative and visual roles.
- Six original procedural effect families: hook impact, transition, mechanism,
  reveal, payoff, and warning.
- Four subtle procedural ambience profiles: laboratory, space, nature, tension.
- Licensed music selection plus time-coded intensity automation.
- Speech-first sidechain ducking, 48 kHz stereo mixing, high/low-pass cleanup,
  compression, limiting, -14 LUFS target, -1.5 dBTP target, AAC target 384 kbps.
- One identical audio engine for FFmpeg and Remotion delivery.
- Adaptive silence analysis, loudness/LRA/true-peak measurement, clipping and
  head/tail silence checks, stream inspection, and a blocking 90/100 gate.
- Rights records with source, attribution, commercial and YouTube permission,
  evidence reference, and SHA-256 file integrity.

## The 100-point audio gate

| Area | Points | Blocking conditions |
|---|---:|---|
| Integrated loudness | 15 | Outside -15 to -13 LUFS |
| True peak and clipping | 10 | Over -1 dBFS or clipping |
| Speech continuity | 10 | Excess pause/head/tail silence |
| Delivery stream | 15 | Not 48 kHz stereo AAC or measured below 224 kbps |
| Semantic effects | 10 | Hook/payoff coverage affects score |
| Effect collision policy | 5 | Cues closer than the plan's safe gap |
| Ambience | 5 | Missing semantic ambience affects score |
| Music decision/ducking | 8 | Requires cleared automated music or explicit narration-only |
| Mobile dynamics | 5 | Excessive loudness range affects score |
| Rights evidence | 7 | Missing permission/evidence/checksum |
| Human voice performance | 10 | Optional for 90; at least 4/5 for 100 |

Technical and rights failures cannot be hidden by a high total score. A failed
report stops the pipeline before the YouTube package is created.

## Free stack to use now

1. **FFmpeg + the built-in studio graph** — current default; no recurring cost.
2. **Original procedural SFX and ambience** — current default; generated inside
   the project and therefore free of third-party asset claims.
3. **Original local music** — current included track; checksum and rights proof
   are enforced by schema v2.
4. **YouTube Audio Library** — preferred external music/SFX source. Preserve the
   track URL/title, the license shown at download time, attribution when
   required, a screenshot or receipt, and the downloaded file's checksum.
5. **Freesound** — accept only CC0 or CC-BY entries; reject CC-BY-NC for a
   monetized channel. Preserve the exact item page and attribution.
6. **Pixabay** — usable only with a dated source record and Content ID evidence;
   keep the original filename, page URL, download record, and checksum.
7. **Channel-owned human recording** — safest zero-subscription Turkish voice.
   DeepFilterNet can be added for local noise suppression before SELMA's mix.

Piper is a capable free local engine, but engine licensing and voice-model
licensing are separate. The current Turkish DFKI Piper model card is
CC-BY-NC-SA; it must not be used for commercial publishing. Do not activate a
Piper voice until its own model card explicitly permits the intended use.

## Paid roadmap (inactive now)

| Priority | Product | Intended role | Current decision |
|---:|---|---|---|
| 1 | ElevenLabs Multilingual v2/v3 | Primary expressive Turkish narration | Keep adapter; activate only on a plan with commercial rights. API list price observed: $0.10/1k chars for Multilingual v2/v3, $0.05/1k for Turbo/Flash. |
| 2 | Epidemic Sound Creator/Pro | Music, stems, SFX, optional voice | Best single catalog upgrade. Creator observed at $9.99/month annually for one monetized channel; Pro $16.99/month annually for broader commercial/client use. |
| 3 | Artlist Music & SFX | Alternative catalog and stems | Compare actual channel/license scope at purchase; observed Social $9.99/month annually and Pro Music+SFX $24.92/month annually. |
| 4 | Google Cloud TTS / AWS Polly | Reliable fallback narration | Add only if Turkish voice audition beats the current provider. AWS observed at $4/M Standard and $16/M Neural characters; check live regional pricing. |
| 5 | Auphonic paid | Independent mastering/repair fallback | Free tier adds a jingle, so it is not a publishable default. Paid tier is optional when remote restoration is worth the handoff. |
| 6 | Adobe Audition | Manual rescue and spectral repair | Optional specialist workstation; observed at US$22.99/month on an annual billed-monthly plan. |

No paid service in this table is called automatically. A provider is activated
only after its budget, commercial license, privacy terms, and output quality are
approved.

## Reference master

- Video: `output/audio_studio_reference.mp4`
- Evidence: `output/audio_studio_reference_report.json`
- Integrated loudness: -14.01 LUFS
- True peak: -1.5 dBFS
- Loudness range: 2.1 LU
- Longest adaptive silence: 0.6121 s
- Delivery: 48 kHz, stereo AAC, measured 249371 bps
- Automated score: 90/100; no blocking failures

The reference uses an already cached narration sample and the project's original
music, so verification did not make a new paid API request.

## Operating rule

Never import an audio asset based only on the words “royalty free.” The manifest
must prove the exact file, its source, the allowed use, attribution requirements,
and integrity. When evidence is unclear, the correct result is narration-only or
a blocked run—not a guessed license.

## Primary references

- YouTube Audio Library: https://support.google.com/youtube/answer/3376882
- YouTube music safety: https://support.google.com/youtube/answer/15577610
- Freesound licensing FAQ: https://freesound.org/help/faq/
- Pixabay licensing FAQ: https://pixabay.com/service/faq/
- Piper engine and voice guidance: https://github.com/OHF-Voice/piper1-gpl
- DeepFilterNet: https://github.com/Rikorose/DeepFilterNet
- ElevenLabs TTS docs: https://elevenlabs.io/docs/overview/capabilities/text-to-speech
- ElevenLabs API pricing: https://join.elevenlabs.io/api/developer-api
- AWS Polly pricing: https://aws.amazon.com/polly/pricing/
- Google Cloud TTS pricing: https://cloud.google.com/text-to-speech/pricing/
- Auphonic pricing: https://auphonic.com/pricing
- Epidemic Sound pricing: https://www.epidemicsound.com/pricing/
- Artlist pricing: https://artlist.io/page/pricing?type=music-and-sfx
