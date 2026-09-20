# Changelog

All notable changes to SELMA Labs will be documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and future releases will
use semantic versioning.

## Unreleased

### Changed

- **Static analysis is a real gate now.** The `lint` job runs both ruff and mypy
  as blocking checks; the tree is clean under a
  much wider selection (`B`, `E4`, `E9`, `E722`, `F`, `I`, `S110`, `S112`, `UP`),
  so that class of defect cannot land again. 600 findings were fixed
  automatically across 273 files and the last 11 by hand. The pass found a real
  closure bug: the pose-isolation diagnostic's `with_identity` helper never bound
  its loop variable, so every variant could have been built from the last
  iteration's request.
- **`cli/main.py` is a dispatcher again.** Its 1016-line `build_parser()` became
  four per-family builders under `cli/parsers/`, taking the file from 2585 to
  1580 lines. The move is provably behaviour-neutral: `format_help()` and the
  full argument schema (dest, option strings, defaults, nargs, choices) are
  identical before and after.
- **Silent failures now speak.** Three swallowed exceptions report what they
  dropped: an unverifiable background approval receipt, an unreadable character
  bible in the dashboard, and a long-form render carrying dynamic SFX it never
  mixes -- that last one used to log that it was injecting tracks it did not
  inject. Unused loop variables in the ComfyUI providers are renamed, and the
  subtitle-immutability test that passed on any exception now asserts
  `FrozenInstanceError` specifically.
- **Two adapters that could never be instantiated are fixed.**
  `SelmaGPTScenePlanningProvider` never defined the port's abstract
  `provider_identity`, and `SelmaGPTTranslationProvider` was missing both that and
  the port's actual entry point, `translate_texts` (it only had the singular
  form). Both classes stayed abstract, so `scene_planning_provider = "selmagpt"`
  and `translation_provider = "selmagpt"` raised `TypeError` the moment the
  registry picked them. The type check found them; both now satisfy the port.
- **The type check blocks across production Python.** mypy is green and blocking
  for `core`, `infrastructure`, `config` and `cli`. The pass also exposed a
  missing single-asset vision scoring entry point, a dead hybrid ComfyUI call
  signature, and a duplicate character-asset writer; all three are fixed.
- **CI installs a lock.** `requirements-ci.lock.txt` pins all 96 transitive
  packages the quality-gate job resolves; `requirements-ci.txt` stays the
  human-edited input and documents the recompile command. The 3.11 job keeps
  installing the loose file on purpose, because it is the compatibility signal
  rather than the reproducible baseline.

- The character pose pack is now a **three-pose** library. `THREE_QUARTER_LEFT`
  and `THREE_QUARTER_RIGHT` were removed, and the two OpenPose three-quarter
  templates were deleted from the yaw rig, the generator and the catalog. The
  45-degree skeleton read as a near-frontal body (the pose pack's own
  `torso_foreshortening` evidence put it close to the front view), so the guide
  contributed a hand and no angle while the prompt already names the view; front,
  profile and back are the poses that actually read. `all_five_poses_present`
  becomes `all_three_poses_present`, the episode director's pose preferences drop
  to the three that exist, and `make_pose_templates --check` still passes. The
  turnaround's seven-view plan is untouched: the three-quarter *views* are still
  produced by the FLUX edit dialect, only the *pose templates* are gone. Existing
  five-pose packs (Kaito v7) no longer validate and must be regenerated.

### Added

- Superseded renders can be put back: `character turnaround --restore-superseded
  --view VIEW --restored-by NAME [--reason TEXT]`. A seed is a pure function of
  the brief hash, the view index, the attempt and the slot, so re-running a view
  cannot return the frame the human was looking at -- the bytes filed as
  quarantine evidence when it was retired are the only copy. The command swaps
  those bytes back, files the render it displaces as
  `superseded_by_restored_render`, and writes a `view-pack-restore.json` receipt
  naming the human, the time, both seeds and the reason. Nothing is drawn.
  The archives behave as an undo stack, because a restore files the frame *it*
  displaces: repeating the command puts the replacement back, which is the only
  route back once a human has looked closer and reversed their own verdict. A
  frame that failed a check is never a candidate -- otherwise "restore" would be
  a way to smuggle a rejected render back in. Refused: an unnamed human, an empty
  view list, a view nothing ever displaced, the contract-copy views (`FRONT`,
  `FACE_CLOSEUP`), a pack that is already approved or already rejected, archived
  bytes that no longer match the hash they were filed under, and an archived
  frame that no longer passes the view QC gate. The restore also records a fresh manifest entry for the restored
  bytes: without it the pack would fail the `provenance_hashes` check forever,
  which is how a "recovered" pack quietly becomes unapprovable. Verified on
  Akira v6: eight automatic acceptance checks pass again after a restore.
- Targeted re-render: `character turnaround --view VIEW` draws the named views
  again and leaves every other view byte-identical. It was needed because a
  turnaround is not repeatable by design -- a seed is a pure function of the
  brief hash, the view index, the attempt and the slot, so re-running the same
  command reproduces the same frames, and the service hands an existing
  `PENDING_HUMAN_REVIEW` pack straight back without touching the GPU at all
  (measured: 4 seconds, seven identical hashes). The replaced render is archived
  as quarantine evidence under `superseded_by_targeted_rerender` instead of being
  dropped, and that filing is also what advances the attempt loop, so the
  replacement comes from a seed block that has never been drawn. Views that are
  contract copies of the approved canonical artifact (`FRONT`, `FACE_CLOSEUP`)
  are refused: re-drawing them would replace the character's identity.
- `CharacterViewQcReport.from_dict`, so stored QC evidence can be re-filed
  rather than re-measured.
- A rejected character pack is now a durable verdict instead of a note. Refusing a
  view pack or a pose pack writes a rejection receipt (`view-pack-rejection.json`,
  `rejection.json`) naming the human, the reason and the exact asset hashes turned
  down, and both approval gates read it: `approve` raises, and the pose-pack
  downstream guard refuses too, so a pack approved and *then* withdrawn stops
  feeding work. Before this, a pack a human had refused stayed
  `PENDING_HUMAN_REVIEW` on disk and any later run could still approve it. A
  refusal is scoped to one `(character, version, artifact)` triple, so the
  replacement version is unaffected, and recording a *different* refusal over an
  existing one is refused: a receipt that could be edited is not a verdict.
  Entry points: `character reject-view-pack`, `character pose-pack reject`.
### Fixed

- Two latent runtime defects that no test reached were found by the new
  undefined-name gate and fixed. `VideoMasteringService.apply_cinematic_mastering`
  could never run: a redundant in-function `import os` made `os` a local name for
  the whole method, so the first existence check raised `UnboundLocalError` on
  every call. The text-to-video fallback in `PipelineOrchestrator` built its shot
  id from an undefined `i`, and `cli/main.py` called `_load_location_bible`
  without importing it -- both `NameError` on paths the suite never exercised. A
  regression test pins the mastering guard.
- `RUNTIME_PROFILE` defaults to `offline-test`, so a production invocation that
  forgot to set it would silently select deterministic fake providers, because
  the guard only fires on an explicit `production` profile. The factory and anime
  CLI entry points now warn loudly through `warn_if_offline_test_profile`,
  without changing the test-facing default.
- `analytics_strategy_service.get_dashboard_stats` swallowed every failure and
  reported "no data" without logging it; it now logs the exception. The system
  monitor probe and two bare `except:` blocks were narrowed.
- Turnaround drift was measured with one deployment-wide accent colour
  (`character_drift_accent_colour: "#0047AB"`), so a character whose signature
  mark is a different colour was measured with the wrong one: Akira's deep-red
  lock (`#C04838`) came out as `accent_fraction = 0.0` and all five drawn views
  were flagged `palette_drift` -- an alarm the bytes could not support. The
  measurement now reads `signature_marks[].colour` and `.character_side` from the
  brief, carrying the tolerance, calibrated band and threshold source over so
  verdicts stay comparable. Kaito declares exactly the configured cobalt, so its
  reports are unchanged; characters that declare their own colour are no longer
  measured against someone else's pixels.
- A failed targeted re-render could leave a pack that refused to load. View
  images are replaced as the loop reaches each one while `view-pack.json` is
  written last, so an error in between left recorded hashes that no longer
  matched the files on disk -- and such a pack cannot be loaded again. The
  retired bytes are now journalled and put back on any failure, and the drift
  report and the contact sheet became replaceable on the re-render path only.### Tooling

- CI runs a blocking `lint` job: `ruff check .` over a correctness rule core
  (`E9`, `F63`, `F7`, `F82`, `F811`, `F823`, `E722`), plus an advisory mypy pass
  against `core`, `config` and `cli`. The correctness core found the two runtime
  defects above, so it earns its place before the style rules are enabled; the
  ratchet order is recorded in `docs/CODE_REVIEW.md`.
- The Python quality-gate matrix runs the test suite on 3.10 and 3.11; the real
  FFmpeg and smoke steps stay on the 3.10 baseline.
- `tmp/` is git-ignored, and the orphan pose-diagnostic script moved out of it to
  `scripts/run_pose_identity_isolation.py`.

### Known issues

- The profile slots are not profiles.
 `PROFILE_RIGHT` is conditioned on `FRONT`
  **plus the same wing's three-quarter render**, at `identity_strength: 1.0` with
  `identity_end_at: 0.65`, while the prompt asks for a strict side profile and the
  negatives exclude `three-quarter view` and `both visible eyes`. The model keeps
  the reference's pose. Measured by thresholding the subject against a
  corner-sampled background, normalizing for height and centring on the mask
  centroid: the right wing's two views agree at **IoU 0.973** and the left wing at
  **0.918**, while every cross-view pair sits at **0.59-0.62**. The QC detector
  labels all four side views `three_quarter_*` as well. So `akira` v6 spends seven
  slots on five distinct angles, and the profile reference the animation layer is
  supposed to key on does not exist. `kaito` v7 -- the approved reference pack --
  shows the same ordering more weakly (0.713 / 0.669 against a 0.47-0.60
  baseline), so the pattern is systemic rather than an Akira quirk. Both candidate
  levers are now measured, at one seed (424242) and one variable each --
  `scripts/run_profile_projection_experiment.py`, six renders, nothing written
  into a pack. **Reference set: real.** Conditioning the profile on `FRONT`
  alone drops the same-wing IoU from **0.945 to 0.708** (right) and **0.910 to
  0.718** (left), and the render is a different picture from the shipped frame
  (0.703 / 0.751), not a copy with a new seed. It costs framing: the subject
  width delta goes from -0.362 to **-0.422**, so the pose rotates and the body
  shrinks. **Identity window: inert.** `identity_end_at` 0.35 and 0.65 produce
  **byte-identical files** (`81431a26…` and `5abcb24c…`) with identical framing
  and palette, because the FLUX.2 edit dialect binds identity through
  `ReferenceLatent` and its provider never reads the field -- the window is a
  leftover from the IP-Adapter dialect and is now documented as dead. Neither
  lever reaches the 0.49-0.62 cross-view baseline on its own, and the two
  renders ('front' vs 'three-quarter') do not land at the requested angles:
  a 45-degree instruction from `FRONT` renders near-side, a 90-degree
  instruction renders short of profile, so at 4 steps and cfg 1.0 the text does
  not pin the yaw. That makes structural pose conditioning the remaining lever,
  not a prompt rewrite. The guide such a channel would consume is no longer part
  of the problem: the four side templates were redrawn at their stated angles in
  this release (see Fixed), so the next step is to give the FLUX.2 edit graph a
  pose input, not to write a better sentence.

### Fixed

- The two `THREE_QUARTER_*` OpenPose pose templates were side views. They shared
  one code path with the profiles, and the line that was meant to widen a
  three-quarter shoulder pair -- `r_shoulder = cx + tq - 0.02`, `l_shoulder = cx
  - tq + 0.02` -- moved both shoulders *inward*, so the three-quarters came out
  narrower than the profiles beside them. Measured as shoulder width over body
  height, which is scale invariant: front 0.167, profile 0.047, three-quarter
  **0.039**, where a 45-degree template has to sit near `0.167 * cos 45` =
  **0.118**. These are the production guides -- every pose in Kaito v7's pack
  records its `pose_template_hash` and they match the catalog for all five. The
  defect was latent rather than propagated: that pack came from the SDXL +
  OpenPose dialect and its five poses are genuinely distinct
  (`three-quarter-left` vs `profile-left` 0.387, cross-view baseline 0.27-0.51),
  so prompt and identity conditioning still won there. Any dialect leaning
  harder on the guide -- which is what a pose channel in the FLUX.2 edit graph
  would do -- would have inherited the duplication instead. All six templates
  are now drawn from one yaw-projected rig (`core/domain/services/
  pose_template_rig.py`, rendered by `scripts/make_pose_templates.py`), so every
  view's width follows `cos(yaw)` by construction and no per-view special case
  can reintroduce the collapse. Measured after the change: three-quarter **0.122
  / 0.121** against the 0.120 target, profiles **0.022**, back **0.167**,
  front unchanged -- and the front template renders **byte-identical** to the
  template it replaces, which is the check that the rig still describes the
  same body. Side views also gained a real stance (feet staggered front-to-back,
  face plane forward of the neck) instead of a single vertical line, and front
  and back are no longer byte-identical, so the template carries the left/right
  distinction. The generator itself moved out of the git-ignored
  `output/akira-closure/` directory, where the production assets could not be
  reproduced from the repository at all, and `python -m scripts.make_pose_templates
  --check` now fails when a template and its catalog hash disagree. Blast
  radius, stated rather than hidden: the staged copies under
  `characters/_pose_templates/` were migrated and the store accepts them, but
  Kaito v7's stored pose pack can no longer pass `_verify_manifest_assets` --
  `Pose template 'THREE_QUARTER_LEFT' changed.` That is the fail-closed guard
  doing its job, and it means that pack has to be re-rendered (v8) before it can
  be approved. It was `PENDING_HUMAN_REVIEW`, never approved, so nothing shipped
  depends on it.
- Location identifiers deleted accented letters instead of transliterating them,
  so `SAINT ORA KLİNİĞİ - NÖROLOJİ İZOLASYON ODASI` became
  `saint-ora-kl-n-n-roloj-zolasyon-odasi`: the location name was lost and any two
  locations differing only by their accents would have collapsed onto a single
  storage id. Accented letters are now folded the same way a character id already
  was, so `ep01`'s eight locations read as `saint-ora-klinigi-noroloji-izolasyon-odasi`,
  `kirmizi-hat-cati-servis-rotasi`, `eski-pazar-gecidi` and so on. Fixed before
  any background asset was named, so no existing asset needed renaming.
- The pose pack locked the first structurally valid render whatever the quality
  gate said, so a cropped or wrongly facing seed became evidence the human
  approval list had to cover. A render that fails a measurable QC criterion
  (framing, facing side, person count, no face in a back view) is now quarantined
  and the next seed is spent; if every attempt fails the pack stops `BLOCKED`
  instead of shipping a known-bad pose. Measured result with the same settings:
  5/5 poses pass, and no pose needed more than three seeds. This also corrects
  the earlier diagnosis that the OpenPose guide was being overridden by identity
  conditioning -- the guide works; the old loop simply never insisted.
- The production pose pack could never render. Its request declared three
  identity references against a workflow with two adapters, named no reference
  chain (`reference_views`), declared an `identity_mode` the SDXL provider does
  not implement, and gave its conditioning references asset IDs that did not
  match its own `reference_asset_ids` map. The pose dialect now chains exactly
  the two locked anchors and names them; a regression test drives the real
  request through the real provider and workflow instead of an offline fake.
- The pose pack's provenance fallback and its offline test double claimed three
  conditioning references while the request declared two, which failed the
  manifest's own reference/hash alignment rule.
- `preproduction plan` could only ever run from the test suite. The breakdown
  service refuses to plan without a concrete Character Bible, and the container
  is built once for every command, so nothing in production ever supplied one;
  the command failed with "requires an explicitly selected Character Bible" no
  matter which screenplay was passed. The identity is now selected explicitly
  with `--character-id` and resolved from canon, refusing when it does not
  resolve to exactly one locked bible.
- The story-development provider caught `TimeoutError`, which on Python 3.10
  does not catch `asyncio.TimeoutError`. A reviewer that exceeded its budget
  produced no domain error at all, so the CLI reported the failure as the empty
  string `SELMA command failed:`. The provider now follows the idiom the rest of
  the codebase already used, and the timeout is configurable through
  `story_development_timeout_seconds` instead of being hard-coded.
- A reviewer that returned a finding with its severity written into the `code`
  field made the whole review gate fail: the missing key raised during parsing
  and, because the reviewers run concurrently, the result was not even
  deterministic. A finding is now repaired from its own identity fields instead
  of being lost. Free prose is deliberately not scanned for severity words, so
  the repair cannot invent a blocking finding that was never claimed.

### Changed

- A repository test suite run no longer depends on how far the production
  project has actually progressed. Tests that asserted "the style was never
  approved", "the cast is empty", "the bible directory holds exactly one file"
  now stage that state on an isolated copy, so promoting the style or
  registering a character no longer breaks the suite that is meant to guard it.

### Added

- `story review` and `story approve`: the screenplay approval gate that
  `ScriptBreakdownService` and `HierarchicalShotPlanningService` both demand had
  no CLI entrance, and `output/preproduction/story-approvals/` had never been
  created, so no screenplay in this project could reach `LOCKED` through a
  command. `StoryEngineService.review()` runs the same canonical validator and
  the same three reviewers over an existing screenplay, and `approve()` is left
  untouched: it still only locks a result that came back ready, so a hand-written
  draft cannot bypass the gate that a generated one must pass.
- Non-cast voices. A crowd or an on-screen system can speak without being
  planned as a character, so `ep01`'s `MNEMOS` and `Güvenlik Görevlileri` pass
  canon validation and no longer open a five-pose pack each. Declared in the
  world bible as `non_cast_voices` and honoured by both the validator and the
  director, which stops requesting renders for an unnamed crowd with no shots.
- `character lock-narrative`: narrative canon could previously only be locked as
  a side effect of producing a reference pack, which forced art to exist before
  a character's story could be approved. The command locks the narrative on its
  own, writes a receipt stating that no visual readiness was claimed, and leaves
  the cast registry untouched so adding bibles does not disturb visual readiness.
- Advisory torso-foreshortening measurement (`torso_foreshortening`) on every
  character-view observation. Facial keypoints and the face detector both read a
  true anime profile as a three-quarter view, so neither can gate the
  profile/three-quarter distinction; body foreshortening is the only yaw axis
  that stays measurable on this art style. It is recorded as evidence and not
  used as a threshold, because the labelled samples do not separate cleanly.
- Regression tests pinning measurable-QC retry and pack-blocking behaviour, and
  the torso-foreshortening metric's declines-instead-of-guessing contract.
- FLUX.2 Klein 4B FP8 as a first-class source-led turnaround engine
  (`comfyui-flux2-edit`), resolved per generation capability so storyboard
  keyframes and pose packs keep the SDXL/pose dialect. Includes its own model
  lock, workflow template and provider.
- Advisory turnaround drift measurement (`character drift-report`) with a
  calibrated tolerance band, recorded in `drift-report.json` as required
  acceptance evidence.
- `series smoke-production-lock`: derives the production style-lock smoke
  receipt from a real render instead of a hand-written file, binding it to the
  pending lock digest, the workflow bytes and the locked weights.
- Per-capability character generation tournament (`character
  turnaround-tournament`) comparing model locks under identical source, seeds,
  view order, chaining policy and prompt contract.
- View-scoped character prompts and captions, caption/view coherence auditing,
  and fail-closed quarantine rules for unaudited reference candidates.
- Anime-safe visual IP-Adapter plus img2img reference routing and an Akira V2
  dataset-to-Golden-Set operating runbook.
- Canonical Akira Character Bible and guarded two-pass anime production pipeline.
- ComfyUI motion, LivePortrait mock, and layered FFmpeg composition boundaries.
- Script breakdown, animation orchestration, dependency injection, and CLI tools.
- Structured issue forms, contribution guidance, security policy, and quality gates.

### Changed

- The turnaround seed sweep (`character turnaround --seeds N`) is wired through
  to the generator and skips views that are copied from an approved artifact by
  contract, so a sweep no longer spends renders on output that is discarded.
- Drift thresholds, accent colour and mark side now come from configuration; a
  configured threshold file that is missing or corrupt fails closed instead of
  silently measuring against looser built-in defaults.
- `pose-pack generate` in production mode verifies the approved seven-view pack
  before rendering, making the documented "poses start after the turnaround is
  signed" rule executable.
- View-pack approval errors name both version numbers when an acceptance list is
  bound to a different character version.
- Character LoRA operation now defaults to model strength `0.45`, CLIP strength
  `0.0`, and lower visual identity conditioning when an approved LoRA is active.

### Fixed

- View-pack approval is possible again. The `provenance_hashes` automatic check
  demanded model, prompt and workflow hashes from *every* view, including the
  front image and the face close-up, which are copies of approved artifacts with
  no model run behind them. That requirement was unsatisfiable, so no pack could
  be approved at all from v5 onward. A view may now claim inheritance only when
  its bytes match the approved artifact it copies, read from storage at approval
  time; every other view still needs full generation provenance.
- Turnaround drift measurement now separates the subject from a graded studio backdrop by modelling the backdrop as a bilinear surface through the frame
  corners, so the subject box and the palette histogram move instead of being
  pinned to the full frame.
- The drift report measures only drawn views: `FRONT` and `FACE_CLOSEUP` are
  contract copies of approved artifacts, and measuring them flagged the approved
  face anchor against its own bytes.
- Drift views carry an explicit `mark_measurable` flag. When the source head
  holds too few accent pixels for a ratio to mean anything, the mark checks are
  skipped and say so, instead of reporting a missing signature mark the pixels
  cannot support.
- The source-led edit dialect derives its target canvas from the approved
  canonical image's aspect ratio (~1 MP, stride-aligned) and records
  `canvas_policy: source_aspect`, so a square source is no longer re-framed onto
  the fixed 768x1152 portrait canvas that the pose dialect was calibrated on.
- The `neutral_studio_background_consistent` acceptance item describes the
  approved backdrop (a neutral studio backdrop with a soft blue-grey gradient)
  instead of a plain light-gray one the canonical image never had.
- `character drift-report --pack` resolves view images under `views/` as well,
  so the documented review command runs against a real pack; the inherited
  `face-closeup` entry is no longer measured there either.
- Drift reports name `canvas_aspect_mismatch` when source and view canvases do
  not share an aspect ratio, instead of reporting box and palette deltas that
  are frame arithmetic rather than character drift.
- Repository documentation is organized by architecture, operations, project
  status, and historical material.

### Security

- Human approval and persisted committed-candidate checks block unapproved motion
  generation.

## Release policy

The first tagged release will be created after the repository cleanup and security
automation work are merged and the documented quality gates pass on `main`.
