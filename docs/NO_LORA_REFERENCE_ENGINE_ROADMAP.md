# Character Engine Without LoRA — 30+ Character Roadmap

Status: approved product direction; implementation roadmap started (2026-09-05).

## Product decision

SELMA Labs will accept a structured text brief, generate the character's visual
references with its own image generator, and use the human-approved canonical
image to generate the character from every required view and pose. LoRA is not
part of the default path. It remains an optional, later fallback for exceptional
characters whose identity cannot be held by reference conditioning alone.

The user-facing promise is therefore:

> Describe the character once, choose the design you want, and let SELMA Labs
> build an approved reusable reference pack for that character, then add poses.

"Text-only" describes the input experience. After the design choice, generation
is reference-driven: canonical image + view/pose contract + shared style preset.

## User input contract

The first product version should collect a guided form rather than depend on one
unstructured prompt. Only `name` and `concept` are required; all other fields can
be selected explicitly or inferred and shown back to the user before generation.

| Group | Field | Required | Example | Behaviour |
|---|---|---:|---|---|
| Identity | `name` | yes | Mira | Stable character and storage identifier |
| Identity | `concept` | yes | Underground courier who manipulates sound | Main natural-language description |
| Identity | `age_band` | no | young adult | Never infer an exact age when omitted |
| Identity | `gender_presentation` | no | feminine | Visual presentation, not identity metadata |
| Body | `body_type` | no | lean athletic | Stable silhouette guidance |
| Face | `face` | no | angular face, soft jaw | Facial geometry guidance |
| Eyes | `eyes` | no | amber, narrow | Colour and shape |
| Hair | `hair` | no | black bob, red side lock | Style, colour and immutable details |
| Marks | `signature_marks` | no | scar under left eye | Count, colour and side become QC rules |
| Outfit | `outfit` | no | cropped courier jacket | Canonical default costume |
| Props | `props` | no | folding baton | Included only in compatible action poses |
| Personality | `personality` | no | alert, restrained | Expression and posture direction |
| Style | `style_preset` | no | selma-anime-v1 | Shared project style; defaults at project level |
| Palette | `palette` | no | charcoal, burgundy | Character-level colour constraints |
| Exclusions | `avoid` | no | no cape, no tattoos | Negative prompt and validation rules |
| Views | `view_pack` | no | standard | `minimal`, `standard`, or `extended` |
| Actions | `requested_actions` | no | run, guard, land | Adds pose-controlled action references |

The form may also expose one `additional_notes` field. Free text must never
silently override explicit selections; conflicts are shown to the user before
the first generation starts.

Proposed application value object (schema version 1):

```json
{
  "schema_version": 1,
  "name": "Mira",
  "concept": "Underground courier who manipulates sound",
  "age_band": "young adult",
  "gender_presentation": "feminine",
  "body_type": "lean athletic",
  "face": "angular face, soft jaw",
  "eyes": "amber, narrow",
  "hair": "black bob with exactly one red lock on character-left",
  "signature_marks": [
    {
      "label": "red hair lock",
      "count": 1,
      "character_side": "left",
      "colour": "#9E2838"
    }
  ],
  "outfit": "cropped courier jacket, tapered trousers, black boots",
  "props": ["folding baton"],
  "personality": ["alert", "restrained"],
  "style_preset": "selma-anime-v1",
  "palette": ["charcoal", "burgundy", "amber"],
  "avoid": ["cape", "tattoos", "multiple characters"],
  "view_pack": "standard",
  "requested_actions": ["walking", "running", "guard"],
  "additional_notes": ""
}
```

## User journey and approval gates

### Gate 0 — Brief confirmation

SELMA normalizes the submitted form into a `CharacterCreationBrief` and shows a
short, editable summary. Generation starts only from the confirmed version. The
confirmed brief receives an immutable content hash so later renders can always
be traced to the exact input.

### Gate 1 — Design selection

Our configured image generator creates five design candidates from the confirmed
brief. All five use the same shared style preset and deterministic seed family.
They are unapproved candidates; none can be used in scene production.

The user may:

- select one candidate as-is;
- request another five variants;
- select a candidate and request one bounded revision, such as changing hair or
  outfit while preserving the rest of the design.

The selected image becomes `canonical.png`. The approval receipt stores the
brief hash, image hash, seed, provider, model/workflow version, and approver.

### Gate 2 — View pack

The internal image generator derives views from `canonical.png`. It should use
empty-latent composition plus IP-Adapter identity conditioning. When one image
cannot establish unseen geometry reliably, the engine generates a small
multi-view design sheet and asks for one intermediate human confirmation.

The first release deliberately produces a fixed seven-view draft pack before any
pose work. This keeps design construction separate from animation geometry.

Initial draft pack:

| View | Purpose |
|---|---|
| face close-up | facial identity and hairline |
| front | front outfit construction and complete costume |
| profile left | left-side silhouette |
| profile right | right-side silhouette and asymmetry checks |
| three-quarter left | left transition between front and profile |
| three-quarter right | right transition between front and profile |
| back | back-of-outfit construction |

Every view records its closest approved conditioning image. A back view must not
pretend that a frontal canonical image contains verified back-of-outfit facts;
newly invented details are surfaced during contact-sheet review.

### Gate 3 — Pose bank

Static poses may use prompt-directed composition. Every `ACTION_*` pose must have
an explicit pose contract and OpenPose/ControlNet input. Missing action geometry
is a blocking error, never a prompt-only fallback.

The first standard action pack is walking, running, guard, crouch, and landing.
Props are included only when both the character brief and pose contract allow
them.

### Gate 4 — Contact-sheet approval

SELMA runs cheap deterministic checks first, then optional vision scoring, and
builds one contact sheet containing accepted and quarantined frames. The user
approves the character pack once, may reject individual frames, and can request
targeted regeneration. Only approved frames enter the reusable pose bank.

### Gate 5 — Scene use

Shot generation selects the nearest approved view/pose reference, combines it
with the scene, camera and lighting contract, and records reference lineage in
the keyframe metadata. Unapproved candidates and quarantine paths are never
eligible inputs.

## Output contract

Each completed character should have one versioned directory:

```text
output/production/characters/<character-id>/v1/
  canonical_source.png
  anchors/
    face_anchor.png
    fullbody_anchor.png
  canonical-approval.json
  views/
  quarantine/
  contact-sheets/
    views.png
  view-pack.json
  view-pack-approval.json
  manifest.json
```

`manifest.json` is the runtime index. Each asset entry includes view, pose,
content hash, conditioning source, generation seed, provider/workflow version,
QC results and approval state. Runtime code reads the manifest, never searches
directories by filename convention.

## Implementation roadmap

### Phase 0 — Stabilize the current branch

- [x] Wire `ViewFramingGate` into the real application container.
- [x] Make action pose references mandatory even when the entire map is omitted.
- [x] Add a gradient-background fixture to framing-gate tests.
- [ ] Add shadow and textured-background fixtures to framing-gate tests.
- [x] Put style refinement behind an explicit setting.
- [ ] Record both base/refined lineage in candidate metadata.
- [x] Keep `.freebuff/` and other workstation metadata outside version control.

Exit criterion: CLI reference generation exercises the same gates as the unit
tests, and a missing action pose fails before calling the image provider.

### Phase 1 — Character brief and design candidates

- [x] Add `CharacterCreationBrief` and schema-v1 serialization.
- [x] Add deterministic explicit-selection/avoid-list conflict validation.
- [ ] Add assisted free-text conflict interpretation before confirmation.
- [x] Add the five-candidate design-generation service.
- [x] Add canonical selection and hash-bound approval receipt.
- [x] Add CLI operations: `character create` and `character approve-design`.
- [ ] Add equivalent HTTP/API operations for the non-technical UI.

Exit criterion: a new character can be created from the structured form and one
chosen design is stored as a locked canonical asset without manual file moves.

### Phase 2 — Generic view engine

- [x] Add a character-agnostic seven-view draft contract separate from LoRA recipes.
- [x] Require a hash-verified, human-approved canonical design as its source.
- [x] Generate face close-up, front, left/right profiles, left/right
  three-quarter and back views only.
- [x] Add the `character turnaround` CLI operation.
- [ ] Add approval and targeted regeneration for individual draft views.
- [ ] Add optional extended view presets after the seven-view flow is validated.
- Select the closest approved conditioning view for every requested output.
- Persist provider/workflow/seed/reference lineage in the manifest.
- Add the equivalent HTTP/API operation for the non-technical UI.

Exit criterion: two characters with different marks, outfits and body types can
complete the standard view pack through the same code path.

### Phase 3 — Pose engine

- Introduce a provider-neutral `PoseContract`.
- Bundle or register reusable OpenPose maps for standard actions.
- Require pose conditioning for action generation.
- Support character-authorized props and pose-specific exclusions.
- Add `character poses` CLI/API operation.

Exit criterion: walking, running, guard, crouch and landing are generated with
verifiable pose lineage and no prompt-only action fallback.

### Phase 4 — Review experience

- Generate contact sheets automatically.
- Show canonical image beside all views and poses.
- Support approve, reject and targeted regenerate per frame.
- Lock the resulting manifest with a named approval and asset hashes.

Exit criterion: a non-technical user can finish a character pack without editing
JSON or moving files.

### Phase 5 — Scene integration

- Add nearest-reference selection to shot/keyframe generation.
- Apply scene lighting and environment without mutating canonical identity data.
- Record selected character references in storyboard metadata.
- Add end-to-end tests from brief to an approved scene keyframe.

Exit criterion: a shot can select and use an approved pose-bank frame
automatically, while rejected or unapproved assets remain unreachable.

### Phase 6 — Scale and optional fallback

- Batch-test at least five visually distinct characters before claiming 30+
  character readiness.
- Measure identity drift, failed-attempt rate, generation time and manual review
  time per character.
- Keep LoRA disabled by default. Define an evidence-based escalation rule only
  if reference conditioning repeatedly misses the agreed identity threshold.

Exit criterion: measured cost and quality support scaling estimates, and LoRA is
never required merely because a character exists.

## Initial success metrics

- A new user can submit a valid brief in under five minutes.
- At least four of five design candidates are technically reviewable.
- A standard view pack needs no more than two generated attempts per accepted
  frame on average.
- Every action frame has pose-conditioning lineage.
- Every production-eligible asset has two matching hashes: generation manifest
  and human approval receipt.
- No quarantined or unapproved asset can enter scene generation.
- Median human review time is below two minutes per character contact sheet.

## Immediate next slice

Live-validate the seven-view draft pack on one newly approved character, add its
contact-sheet approval, and only then resume Phase 3 pose work.

Original user direction (2026-09-04):
- **No LoRA.** No per-character training.
- **Character comes from text** (a description), then **one chosen image
  produces every pose** the character needs.
- **Scale: ~30+ characters** for an anime — the per-character flow must be
  cheap and repeatable, not a bespoke project like Akira's was.
- Akira is the first character; the engine must be character-agnostic.

## The engine (character-agnostic, three stages)

For EVERY character the same three stages run:

```
Stage 1: text description  ->  design variants (5)  ->  human picks 1 canonical image
Stage 2: canonical image   ->  pose bank (all views/poses the shots need)
Stage 3: pose bank + scene prompt -> per-shot keyframes -> Wan 2.2 I2V
```

Nothing in the engine knows Akira. Identity lives in the canonical image, not
in weights. Style consistency across the whole anime comes from ONE shared
style preset (same checkpoint + style tokens), not per-character anything.

### Stage 1 — character from text
- Same prompt template for every character, only the identity block changes:
  age/body, face shape, eyes, hair, mark(s), outfit. Style block is constant.
- 5 seeded design variants per character; the human picks one; the chosen
  image is stored as that character's `canonical.png` (mirrors what the V2
  anchor is for Akira).
- Optional: if the story needs clean side/back shots, ask for a 3-view sheet
  (front / 3-4 / profile) at this stage — 2 extra images now, saves bad poses
  later.

### Stage 2 — pose bank from one image (proven parts)
Generation recipe per pose (validated in Akira experiments):
1. Geometry: ControlNet OpenPose when the pose must be exact (actions);
   caption-only otherwise (the clean static frames were made this way).
2. Composition: empty latent + denoise ~1.0 so framing is free.
3. Identity: IP-Adapter PLUS weight ~0.85 pointing at this character's
   canonical image (or the matching-view image if a view pack exists).
4. QC: framing gate + streak-type mark gate where a mark exists; qwen only as
   an optional pre-filter; final sign-off is a **contact sheet per character**
   (one human review, not one per frame).

Standard pose bank per character: face, front, upper body, 3-4 L/R, profile
L/R, full body, 3-4 action poses = ~10-12 frames.

### Stage 3 — video
- Wan 2.2 I2V per shot. Each shot's start image = a pose-bank frame (or a
  keyframe derived from it) + the scene prompt. Identity per shot rides on the
  keyframe; cross-shot consistency rides on reusing the same canonical image
  in Stage 2 for every shot that needs a new pose.

## What this means for the current repo

- The Akira-specific machinery (23-recipe pack, per-frame review.json, LoRA
  dataset manifest, audit gates) was built for the training path and is **not
  the per-character flow anymore**. Do not scale it to 30 characters.
- Keep the pieces that are engine-grade: framing gate, streak-style mark gate,
  staged generation driver, quarantine, txt2img + IP-Adapter recipe (w0.85),
  ComfyUI provider plumbing, pilot-approval idea (reused as "design pick").
- Build ONE generic CLI: `character create --name X --prompt ...` →
  `character poses --name X --poses face,front,3-4-l,profile-l,...` →
  `character shots --name X --script ...`.

## Cost at 30 characters (honest estimate)

| Step | Units | Local 4060 (render only, ~1.5 min) | Notes |
|---|---|---|---|
| Stage 1 designs | 30 chars × 5 = 150 | ~4 h | human picks |
| Stage 2 pose banks | 30 × 10 = 300 | ~8 h | caption-only + pose maps |
| Review | 30 contact sheets | human, ~20-30 min total | sheet per character |
| Stage 3 keyframes+video | shot count | rented GPU weekly | Wan needs more VRAM |

Rough total render: ~12-15 h local, split across characters; rented GPU
collapses it. qwen per-frame review is intentionally dropped at this scale —
it was the slowest step and the human contact-sheet review is stronger anyway.

## Known limits (same physics as Akira)

- One frontal image cannot produce a true back-of-head or strict profile
  (face yaw is pinned by the reference). Mitigations, cheapest first:
  1. use the matching view if the character has a view pack;
  2. generate a 3-view sheet at Stage 1 for characters that need it;
  3. derive pose skeletons from a rig — renders never appear, only geometry;
  4. mirror existing views, with a mark gate catching mirror errors.
- 30 characters × consistent art style needs ONE shared checkpoint/style
  preset and stable seeds; downloading 1-4 extra SDXL checkpoints (≈6.5 GB
  each) widens the style range if the anime wants distinct art directions.

## Explicitly out of scope

- LoRA / DreamBooth / any fine-tuning.
- FaceID / InsightFace (anime faces return `NO_HEAD`).
- Blender renders as final images — rig output is geometry-only.
