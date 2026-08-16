# SELMA Labs — Creative Quality Roadmap

## Objective

Raise SELMA's measured video quality from the current **61/100** baseline to a
repeatable **85/100 minimum**, with a **90/100 target**, without weakening the
existing hexagonal architecture or bypassing `scripts/run_factory.py`.

The current factory is technically reliable. This roadmap concentrates on the
remaining gap between a valid upload and a video that earns attention, explains
its promise clearly, and rewards the viewer with a strong payoff.

## Baseline

The music-free octopus quality-control video established this starting point:

| Quality area | Baseline |
|---|---:|
| Hook and promise | 6/15 |
| Script value and payoff | 6/15 |
| Visual–narrative match | 8/15 |
| Editing rhythm | 6/10 |
| Captions | 7/10 |
| Narration and audio | 9/12 |
| Sound design/music | 3/5 |
| Technical/mobile delivery | 7/8 |
| Packaging | 4/5 |
| Quality control | 5/5 |
| **Total** | **61/100** |

## Delivery principles

1. `scripts/run_factory.py` remains the only production entry point.
2. A title, script, storyboard, asset plan, voice track, render, and upload
   package must describe the same promise.
3. Technical checks and creative checks remain separate. Passing codecs cannot
   compensate for a weak hook or an unanswered title.
4. Creative quality gates fail closed before paid downstream stages whenever
   possible.
5. Default timing rules are format presets, not universal laws. The content may
   override them only when the reason is recorded in the run metadata.
6. Each experiment changes one principal variable so performance changes can be
   attributed to a cause.

## Sprint 18 — Narrative contract and script intelligence (P0)

**Implementation status: COMPLETE — automated validation passed; live regenerated
benchmark remains part of Sprint 25.**

### Problem solved

The title asks “why?”, but the script only describes “what”. The opening is a
technical definition, the payoff is absent, and the final section contains
filler.

### Work

- Add a `NarrativeContract` value object containing:
  - target audience;
  - one-sentence promise;
  - question to answer;
  - answer that must appear in the script;
  - hook type;
  - evidence beats;
  - payoff;
  - optional CTA;
  - target duration and justified overrides.
- Make script generation produce explicit `hook`, `context`, `evidence`, and
  `payoff` beats instead of one undifferentiated paragraph.
- Add an answer-completeness check: a question in the title must be explicitly
  resolved by the approved script.
- Add a hook check: the first spoken beat must contain the promise, surprising
  consequence, or a precise curiosity gap.
- Add information-density and filler detection. Reject generic endings such as
  “yakından bakalım”, “keşfetmeye çalışalım”, and statements that merely say a
  subject is interesting.
- Add duration-aware compression before voice generation. For the single-fact
  preset, prefer approximately 18–25 seconds unless the narrative contract
  records a reason to use another duration.
- Fact-check the rewritten hook and payoff again whenever they introduce a new
  claim.

### Acceptance criteria

- The title question and approved answer are present in the run artifact.
- The essential promise is spoken within the first 1.2 seconds in the standard
  single-fact preset.
- Every sentence has a declared role and new information contribution.
- No detected filler sentence reaches voice generation.
- The payoff resolves the opening promise rather than starting a new topic.
- Script-focused score reaches at least **12/15** on three fixture topics.
- Unit tests cover unanswered titles, fake hooks, filler endings, grounded
  rewrites, and duration overrides.

### Expected score after sprint

**69–73/100**

### Delivered

- `NarrativeContract`, sentence-level `NarrativeBeat`, and
  `NarrativeQualityReport` domain artifacts.
- A durable `NARRATIVE_QUALITY_V1` checkpoint between fact-check and voice.
- Fail-closed checks for weak hooks, unanswered title questions, filler,
  insufficient structure, repeated information, and weak payoff.
- Narrative metadata persisted with the verified script.
- Provider and grounded-rewriter prompts updated to preserve the contract.
- Default single-fact topic duration changed from 30 to 24 seconds.
- Six new tests; complete suite: **400 passed, 0 failed**.

## Sprint 19 — Semantic storyboard and explanatory visual grammar (P0)

**Implementation status: COMPLETE — automated validation passed; regenerated
benchmark scoring remains part of Sprint 25.**

### Problem solved

The footage contains the correct animal but does not explain the anatomical
claim. Attractive stock footage is being mistaken for visual storytelling.

### Work

- Extend each scene with an explicit visual job:
  - establish subject;
  - locate a part;
  - demonstrate a mechanism;
  - compare states;
  - show a consequence;
  - deliver payoff.
- Separate `subject presence` from `explanatory relevance` in visual scoring.
- Require every evidence beat to declare the objects, action, spatial relation,
  and forbidden distractions needed on screen.
- Introduce an explanatory-graphics path for facts that stock footage cannot
  show: silhouettes, labels, counters, arrows, highlights, simple diagrams, and
  tracked callouts.
- Add visual continuity rules so the opening image, explanatory middle, and
  payoff feel like one story rather than a stock compilation.
- Block unrelated dominant subjects, even when the general environment matches.
  An underwater scene containing a ray must not satisfy an octopus-specific
  intent.

### Acceptance criteria

- Every spoken evidence beat has a visual job and a verifiable on-screen target.
- Anatomy/mechanism claims receive a diagram, overlay, or genuinely explanatory
  asset; generic B-roll alone is insufficient.
- No unrelated dominant species or object appears in the final timeline.
- Human review can identify the purpose of every scene without hearing audio.
- Visual–narrative match reaches at least **12/15** on the benchmark topics.
- Tests cover subject-only false positives, dominant distractors, diagram
  fallback, and visual-job completeness.

### Expected score after sprint

**76–81/100**

### Delivered

- Narrative beats now flow into the production storyboard instead of being
  discarded after script approval.
- Every semantic visual intent records a visual job, narration context,
  required subjects/actions/relations, explanation mode, and forbidden dominant
  distractions.
- Anatomy and mechanism beats fail closed when configured as stock-only and
  receive a timed overlay/diagram path with mobile-safe visual labels.
- Stock search queries incorporate the required subject and action for
  explanatory beats rather than searching only for the general topic.
- Vision scoring separates setting relevance from subject presence, verifies
  action/relation evidence, and rejects unrelated dominant subjects such as a
  stingray in an octopus scene.
- Semantic metadata survives localization, durable checkpoint serialization,
  and render hand-off.
- Eight new tests; complete suite: **408 passed, 0 failed**.

## Sprint 20 — Asset diversity and editorial rhythm (P0)

**Implementation status: COMPLETE — automated validation passed; regenerated
benchmark scoring remains part of Sprint 25.**

### Problem solved

Verified clips repeat too visibly, low-motion sections linger, and cuts are not
always synchronized with information changes.

### Work

- Add perceptual uniqueness checks using representative frames rather than asset
  IDs alone.
- Introduce a reuse budget per asset, subject pose, camera angle, and background.
- Prefer a new visual phase over reuse when a semantic beat changes.
- Allow reuse only when the crop, tracked detail, overlay, or narrative function
  is materially different.
- Align scene boundaries with script beats and important word timings.
- Add a motion-energy signal and flag long low-motion passages that lack an
  explanatory overlay.
- Define an editorial rhythm preset for single-fact Shorts:
  - immediate hard-cut opening;
  - cuts at semantic changes;
  - pattern interrupts with a reason;
  - no decorative transition requirement;
  - deliberate closing frame suitable for a loop when appropriate.

### Acceptance criteria

- No source clip is perceptually repeated without a different visual function.
- No unrelated stock insert is used merely to create variety.
- Every major information beat has a corresponding visual transition or overlay.
- Low-motion warnings are resolved or explicitly justified.
- Editing-rhythm score reaches at least **8/10**.
- Tests cover duplicate crops, repeated poses, low-motion exceptions, and
  beat-aligned scene boundaries.

### Expected score after sprint

**81–85/100**

### Delivered

- Crop-aware perceptual hashes are generated from catalog evidence and then
  refined from representative frames of the downloaded source clip.
- Reuse budgets now cover source identity, perceptually equivalent imagery,
  subject pose, camera angle, and background—not only provider asset IDs.
- Immediate visual repeats fail closed. Non-adjacent source reuse is permitted
  only when its visual job, crop/shot grammar, explanation mode, or overlay is
  materially different.
- Vision evidence persists subject pose, observed camera angle, background
  signature, and motion energy through selection and checkpoints.
- Storyboard cuts snap to nearby phrase or important word boundaries; a durable
  `EDITORIAL_RHYTHM_V1` gate rejects cuts between spoken units.
- Representative-frame motion energy blocks long static passages unless a
  declared explanatory overlay justifies the hold.
- FFmpeg now consumes storyboard shot types and renders materially different
  wide, medium, macro, and detail crop treatments while preserving hard cuts.
- Nine new tests; complete suite at Sprint 20 completion: **417 passed, 0 failed**.

## Motion-design polish — purposeful animation layer

**Implementation status: COMPLETE — real FFmpeg render validation passed.**

- Karaoke phrases enter with a short upward settle and blur-to-sharp reveal;
  active-word emphasis is reduced to a controlled 106% scale.
- Explanatory cards use a 220 ms rise, restrained overshoot, staggered labels,
  and safe fade-out instead of abrupt appearance.
- Visual jobs receive semantic accents: locate pulse, mechanism direction arrow,
  comparison movement, consequence cue, and payoff confirmation.
- Camera animation now follows the scene's visual job: energetic subject reveal,
  focused anatomy push-in, directional mechanism track, and calm payoff landing.
- Hard cuts remain intact; the motion layer adds no decorative crossfades or
  opening fade from black.
- Three new animation tests, including a real ASS-to-FFmpeg render; complete
  suite: **420 passed, 0 failed**.

## Sprint 21 — Mobile caption UX (P1)

**Implementation status: COMPLETE — automated and preview-artifact validation
passed; regenerated benchmark scoring remains part of Sprint 25.**

### Problem solved

Captions are readable but sentence boundaries can be crossed, short words can
flash for only 80 ms, and 110% active scaling can push long lines outside their
safe area.

### Work

- Make `.`, `?`, and `!` hard cue boundaries by default.
- Prefer clause boundaries at commas, conjunctions, and semantic units.
- Measure the fully styled active word, including outline and scale, during line
  fitting.
- Reduce active scale to a configurable 104–106% default.
- Add a minimum visible emphasis duration for short words; merge or highlight
  without scale when the aligned duration is too short.
- Add safe-zone profiles and validate the render against the vertical YouTube
  template.
- Generate caption preview frames for the longest line, widest active word, and
  lowest-positioned cue.
- Keep a sidecar SRT for accessibility while retaining premium open captions.

### Acceptance criteria

- No cue crosses a hard sentence boundary.
- No active glyph or outline enters the unsafe region.
- No word performs an imperceptible scale pulse.
- Caption previews pass at 100%, 75%, and small-phone simulated sizes.
- Caption score reaches at least **9/10**.
- Tests cover punctuation, Turkish long words, outline width, active scaling,
  and safe-zone overflow.

### Expected score after sprint

**84–87/100**

### Delivered

- `CUE_PARTITIONING_V2` treats `.`, `?`, and `!` as inviolable boundaries,
  prefers commas and conjunctions, and permits an intentional singleton rather
  than joining separate sentences.
- Cue fitting uses the real bold font metrics plus active-word scale and outline;
  mobile safe width can override the normal two-word density preference.
- The active scale is configurable only within the controlled 104–106% range;
  words shorter than 160 ms receive color emphasis without an imperceptible
  scale pulse.
- `CAPTION_UX_V1` validates horizontal/vertical YouTube safe zones and persists a
  numeric caption score before visual search and render.
- `CAPTION_PREVIEWS_V1` extracts the longest line, widest active word, and latest
  cue from the final render, then creates 100%, 75%, and 360×640 small-phone
  versions—nine QA images per run.
- Premium open captions remain paired with the existing language-specific SRT
  sidecar in the YouTube upload package.
- Nine new tests; complete suite: **429 passed, 0 failed**.

## Sprint 22 — Voice direction and purposeful sound design (P1)

### Problem solved

Loudness is correct, but delivery is dynamically flat, pauses can reach 0.85
seconds, and the music-free version has only a limited sound-design layer.

### Work

- Derive voice direction from narrative beats: urgent hook, clear explanation,
  controlled emphasis, and payoff landing.
- Add pronunciation, emphasis, pacing, and pause directives before TTS.
- Define pause budgets by boundary type and shorten unexplained long gaps.
- Measure delivery dynamics separately from loudness compliance.
- Keep the practical narration target near -15 LUFS while allowing controlled
  short-term dynamics and a safe true peak.
- Map procedural effects to semantic events instead of fixed timestamps.
- Add reusable sound motifs for reveal, count, transition, mechanism, and payoff.
- Keep licensed background music optional; never substitute an unlicensed track.

### Acceptance criteria

- No unexplained narration gap exceeds 550 ms in the single-fact preset.
- Hook and payoff use measurably different delivery profiles.
- Loudness remains within the configured -14 to -16 LUFS production range.
- Effects correspond to declared narrative events and never mask speech.
- Narration/audio score reaches at least **11/12** and sound-design score reaches
  at least **4/5** in human review.
- Tests cover pause budgets, TTS directions, effect collisions, narration-only
  fallback, and licensed-music selection.

### Expected score after sprint

**87–90/100**

## Sprint 23 — Delivery, color, and packaging polish (P2)

### Problem solved

The current file is upload-safe, but BT.709 transfer/primary tags are not fully
written, audio is below YouTube's stereo reference bitrate, and descriptions and
hashtags can still contain generic language.

### Work

- Explicitly write BT.709 primaries, transfer, and matrix tags.
- Retain H.264 High Profile, progressive yuv420p, single final encode, and
  `+faststart`.
- Raise stereo AAC delivery to the configured 320–384 kbps range.
- Add output bitrate and visual-quality warnings without replacing CRF-based
  quality control with a rigid bitrate target.
- Generate a concise description that adds information rather than repeating the
  narration.
- Validate title–script promise consistency in the upload package.
- Replace fragmented word hashtags with natural topic/category hashtags.
- Preserve source credits, licensing evidence, captions, thumbnail selection,
  and AI disclosure review.

### Acceptance criteria

- `color_primaries`, `color_transfer`, and `color_space` all report BT.709.
- MP4 `moov` precedes `mdat`.
- Upload-package title and script satisfy the same narrative contract.
- Description contains no filler or duplicate paragraph.
- Technical/mobile score reaches **8/8** and packaging reaches **5/5**.

### Expected score after sprint

**89–92/100**

## Sprint 24 — Creative quality gate and learning loop (P0 for scale)

### Problem solved

The existing QA proves that a file is technically valid. It does not yet prevent
an unanswered promise, filler ending, irrelevant visual, perceptual repetition,
or weak payoff from being marked ready to upload.

### Work

- Expand the premium quality report with the full 100-point rubric.
- Record evidence and remediation for every deducted point.
- Define blocking gates independent of total score:
  - grounded factual claims;
  - title answered;
  - hook present;
  - payoff present;
  - no dominant irrelevant visual;
  - no caption overflow;
  - required rights metadata;
  - technical upload safety.
- Require **85/100** for `ready_to_upload`; target **90/100** for premium approval.
- Produce a visual review sheet with hook, evidence, payoff, widest caption, and
  thumbnail frames.
- Add a human-review field for voice naturalness and final creative approval.
- Store post-publish metrics by content format and hook type:
  - viewed versus swiped away;
  - engaged views;
  - average view duration;
  - average percentage viewed;
  - retention-drop timestamps;
  - subscriber conversion.
- Compare experiments to the channel's own rolling baseline; do not embed
  unsupported universal “viral” thresholds.

### Acceptance criteria

- A technically valid but creatively weak fixture is blocked.
- A score cannot hide a failure in a mandatory creative gate.
- Every deduction links to a timestamp, script beat, asset, or measurable signal.
- Experiment records identify the single principal variable changed.
- Quality reports are deterministic for deterministic fixture inputs.

## Sprint 25 — Benchmark cohort and final validation

### Work

- Select at least five single-fact topics with different visual demands:
  animal anatomy, natural mechanism, space/science, history/object, and an abstract
  concept requiring explanatory graphics.
- Run the complete factory without bypass scripts.
- Review every output against the same rubric and mandatory gates.
- Regenerate only the stage responsible for a failure.
- Create two hook variants for selected topics while keeping the rest of the
  production constant.
- Publish only after explicit approval; use private or unlisted review when a
  platform check is needed.

### Release criteria

- All benchmark videos score at least **85/100**.
- Cohort average reaches at least **88/100**.
- No blocking creative or technical failure remains.
- At least two videos reach **90/100** in human review.
- The octopus benchmark is regenerated and improves from **61/100** to at least
  **85/100**.
- The complete automated test suite remains green.

## Recommended execution order

```text
Sprint 18: Promise + script
        ↓
Sprint 19: Semantic storyboard
        ↓
Sprint 20: Assets + edit rhythm
        ↓
Sprint 21: Captions
        ↓
Sprint 22: Voice + sound
        ↓
Sprint 23: Render + packaging
        ↓
Sprint 24: Creative QA + analytics
        ↓
Sprint 25: Multi-topic validation
```

Sprint 24 is specified early but completed after the creative signals from
Sprints 18–23 exist. Its blocking gates should be added incrementally with each
sprint rather than postponed to the end.

## Definition of premium done

A video is premium only when all of the following are true:

- it earns attention immediately without misleading the viewer;
- its title promise is explicitly answered;
- every sentence contributes information or narrative momentum;
- every visual explains, demonstrates, or intentionally supports its spoken beat;
- repetition is purposeful and perceptually distinct;
- captions are synchronized, semantic, readable, and mobile-safe;
- narration sounds directed rather than merely generated;
- sound design supports meaning and never masks speech;
- delivery matches YouTube's technical recommendations;
- rights and AI disclosure decisions are recorded;
- the creative score is at least 85/100 and no mandatory gate fails;
- later iterations are driven by controlled experiments and channel-specific
  viewer data.
