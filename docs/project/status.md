# Project Status

SELMA Labs is an active, local-first AI video production project. The codebase
supports both the durable topic/audio factory and a guarded Akira anime pipeline.

## Current baseline

| Area | Status |
|---|---|
| Python test suite | Verified by CI and the current branch test run |
| Static analysis | Ruff correctness gate (`E9`, `F82`, `F811`, `F823`, `E722`, …) is blocking in CI and green; mypy runs advisory. Full findings in [the code review](../CODE_REVIEW.md) |
| Python and real FFmpeg render CI | Passing on `main` |
| Remotion type-check and smoke frame CI | Passing on `main` |
| Topic/audio production factory | Implemented and live-validated |
| Akira character reference workflow | Implemented |
| Reference-driven character design | Dual anchors, chained seven-view generation, automatic QC, three-attempt quarantine/retry, contact sheet and atomic human approval implemented |
| Character production infrastructure | Model lock, fail-closed preflight, WebSocket watchdog/interrupt/retry, thermal guard, atomic manifest and exclusive work lock are wired to the live ComfyUI path |
| Character turnaround engine | FLUX.2 Klein 4B FP8 runs the seven-view turnaround as a first-class engine (`comfyui-flux2-edit`) selected per capability; storyboard keyframes and pose packs stay on the SDXL/pose dialect |
| Turnaround drift evidence | Advisory per-view drift is measured against the approved source, recorded in `drift-report.json` with the calibrated band and its SHA-256, and required as acceptance evidence. The accent colour and mark side are read from the character's own `signature_marks`, because a deployment-wide colour measured a differently coloured character against the wrong palette (`accent_fraction = 0.0`, every drawn view flagged); the calibrated band is carried over so verdicts stay comparable |
| Pack rejection | A refused view pack or pose pack writes a durable rejection receipt that both approval gates and the downstream pose guard read, so a pack a human turned down can never be approved later; a rejection is scoped to one character version and cannot be rewritten |
| Targeted view re-render | `character turnaround --view VIEW` redraws named views inside an existing pack and keeps every other view byte-identical; the replaced render is archived as quarantine evidence. A full turnaround is deliberately not repeatable, so this is the only way to change one view: a seed is a pure function of the brief hash, view index, attempt and slot |
| Superseded render restore | `character turnaround --restore-superseded --view VIEW --restored-by NAME` puts an archived render back and files the render it displaces, writing a `view-pack-restore.json` receipt. Restoring is a byte operation because a seed cannot return the frame the human preferred. It refuses an approved or rejected pack, a view that was never re-rendered, mismatched archived bytes and a frame that no longer passes the QC gate, and it records fresh manifest provenance: without that the pack would fail `provenance_hashes` forever. Verified on Akira v6, where all eight automatic acceptance checks pass again afterwards |
| Series style lock | Creative receipt, pending technical lock, and a derived smoke-test receipt are implemented; `mark-production-compatible` consumes evidence produced by a real render rather than a hand-written file |
| Character LoRA | Optional fallback; disabled in the default character path |
| Human keyframe approval boundary | Enforced and fail-closed |
| Screenplay approval gate | `story review` and `story approve` run the canonical validator and the three reviewers over an existing screenplay and lock it only when the result comes back ready; no screenplay in this project had reached `LOCKED` before, because the gate had no CLI entrance |
| Shot hierarchy planning | `preproduction plan` converts a `LOCKED` screenplay into the shot hierarchy and resolves an explicitly selected Character Bible from canon; it previously failed unconditionally outside the test suite |
| Two-pass ComfyUI motion workflow | Implemented and automated-test validated |
| FFmpeg layered composition | Real integration coverage |
| LivePortrait lip sync | Explicit mock/passthrough adapter |
| Wan GPU execution contract | ADR-009 accepted; real provider/GPU blocked until lease/fencing, staged job graph, idempotent commit, recovery, retry/fallback, and budget admission gaps are implemented |

## Production boundaries

- Wan execution is currently limited to the pre-GPU fake/test boundary. The
  [accepted ADR-009 contract](../adr/ADR-009-wan-job-execution-contract.md)
  must be implemented before real provider credentials or GPU instances are
  connected.
- Provider-backed output requires the relevant local models, services, licensed
  inputs, and API credentials.
- The two-pass motion adapter will not run unless its keyframe is explicitly
  approved and persisted as `COMMITTED` by the human-review workflow.
- LivePortrait does not yet perform real mouth animation; the current adapter is
  intentionally labelled as a mock.
- Historical live-render measurements are preserved under
  [`docs/archive/status`](../archive/status/) and are not presented as current
  benchmark results.

## Current production target

The active milestone is production hardening around the approved character
turnaround. Every view is screened before entering `views/`; rejected attempts
retain image and JSON evidence under `quarantine/`, and only a complete contact
sheet can receive `view-pack-approval.json`. Pose and animation work must verify
that receipt. LoRA is not required by the default path.

`scripts/check_anime_readiness.py --stage visual` now reports `READY`.
The series style is `APPROVED` with a signed creative receipt
(`config/series/selma-anime-v1/style-approval.json`), the technical lock is
`PRODUCTION_COMPATIBLE` because `series smoke-production-lock` derived its
receipt from a real render rather than a hand-written file, and `canonical_cast`
holds one member: `kaito` v1, registered from its newly authored Character
Bible. All four earlier `FAIL` rows are gone. The two animation-stage rows are still
red, and measuring them showed that neither is a code problem.

The screenplay gate is now open and used: `ep01`'s "Birinci Taslak" was reviewed,
passed the canonical validator with zero violations and all three reviewers, and
was locked as `LOCKED` by a named human signature
(`assets/preproduction/episodes/ep01/episode-script.locked.json`), with the
approval recorded under `output/preproduction/story-approvals/`. Its shot
hierarchy is `output/preproduction/ep01-plan-locked.json`: 3 sequences, 10
scenes, 25 shots, 82.0 s. The earlier `episode plan` numbers (25 shots, 1802
frames) came from the rule-based director over the same draft and were produced
before the screenplay could be locked.

That measurement also exposes a real limit rather than a solved problem: the
breakdown service conditions every shot on the single Character Bible it is
given, so 6 of `ep01`'s 25 shots (24%) are labelled with a character who is not
in the scene at all (`ep01-sc01` is Elias and Lena; `ep01-sc05` is Ivo and Sera).
A multi-character episode needs a per-scene identity selection that does not
exist yet. The plan is therefore trustworthy for single-character episodes and
incomplete for this one.

`remote_worker` cannot be closed here at all. `docs/ANIME_VISUAL_ANIMATION_REQUIREMENTS.md`
states that `config/production/wan2.2-worker.json` is created only when a rental
instance exists and that a template worker must never be marked `READY`, so the
row stays red until an 80 GB instance is actually rented and its container image,
model revision and persistent storage are pinned. It is a rental decision, not a
change to make.

`episode_package` was measured by running the episode chain as far as it goes
without a GPU. `ep01` plans to 10 scenes, 25 shots and 1802 frames (75.1 s) under
the rule-based director, and what it needs is data, not infrastructure: **seven
characters** (`akira` 10 shots, `elias` 4, `mnemos` 3, `sera` 3, `mina` 2, `ivo`
2, `lena` 1), **eight locations** with 15 background recipes, and it was given no
Location Bible, no background candidate pack and no pose-pack manifest. Only
`akira` and `kaito` have Character Bibles, and this plan never uses `kaito`. The
director also draws on only two of the three poses (`FRONT_NEUTRAL` 16 shots,
`BACK_FULL_BODY` 9).

Kaito's bible records the cobalt streak as a structured mark but deliberately
claims no calibrated anchor or head bbox. That is a measurement result, not an
omission: in the approved 1024 px canonical source only 27 pixels fall within
`delta_e <= 18` of `#0047AB` inside the measured head zone, scattered over the
lower face and collar rather than the hairline, so the streak is not separable
from the blue jacket trim and background at this resolution. The mark therefore
steers (`enforcement: steer`) instead of sealing, and acceptance item 3 stays a
human judgement.

The character evidence itself is now current. Canonical version 7 re-locks the
same approved source image (`dc022b75c1ad768c`) with deterministically derived
anchors, so no locked byte was overwritten and the pack could be regenerated on
the source-aspect canvas. The v7 turnaround produced seven of seven views from
fifteen renders: the copy views (FRONT, FACE_CLOSEUP) are never swept, and the
five drawn views land on 992x992 with ten sibling candidates quarantined.

Its drift report is the first comparable one. `summary.canvas_comparable` is
true, no view carries a signature-mark alarm, and the measurement collapses to a
single actionable defect — `palette_drift` on all five drawn views
(`palette_distance` 0.119-0.280). The v6 report still sits beside it: every view
flagged with five or six reasons, including the byte-identical approved face
anchor reported as missing its own signature mark. Measurement, not the
character, was the broken part there.

Version 7 is the first approved pack in the project's history
(`view-pack-approval.json`, signed by `LOQ`): all eight automatic checks verified,
twelve human checks signed, seven view hashes locked. Pose production is now
unblocked and `require_view_pack_approval` correctly refuses v6.

Why nothing was ever approved before is itself the finding. The
`provenance_hashes` automatic check required model, prompt and workflow hashes
from every view, including `FRONT` and `FACE_CLOSEUP`. Those two are copies of
approved artifacts, so no model ran and their hashes are empty by construction —
the gate could not be satisfied at any version. Packs v5, v6 and v7 all failed it
on exactly those two views. A view may now claim inheritance only when its bytes
match the approved artifact it copies; every other view still needs full
generation provenance.

The signature streak is not measurable at this resolution
(`mark_measurable: false`), so acceptance item 3 stays a human call.

The three-pose pack is generated and now **passes its whole measurable QC
(3/3)**, but it is still **not approved**: five human checks remain, and they are
the user's to sign.

The earlier `1/5` result was an acceptance-policy defect, not a generator
defect. The attempt loop locked the first structurally valid render whatever the
quality gate said, so a cropped or wrongly facing seed entered the pack and
became a flaw the human approval list had to cover. A render that fails a
measurable criterion is now quarantined and the next seed is spent; if every
attempt fails the pack stops `BLOCKED` rather than shipping a known-bad pose.

With the same generator settings the measured result is 5/5, and no pose needed
more than three seeds. The quarantine record names what was rejected:
`FRONT_NEUTRAL` seed 1 lost the feet, `THREE_QUARTER_LEFT` seed 1 was not
detected at all, `PROFILE_LEFT` seeds 1 and 2 faced the wrong way (reversed, then
front), `THREE_QUARTER_RIGHT` seed 1 lost the feet, and `BACK_FULL_BODY` seeds 1
and 2 rendered three-quarter with a visible face. This corrects the earlier
diagnosis that identity conditioning was overriding the OpenPose guide: the guide
works, and the old loop simply never insisted on a passing seed.

One distinction stays unmeasurable and is recorded rather than faked. The facial
keypoints and the face detector both read a true anime profile as a
three-quarter view, so `PROFILE_LEFT` is accepted as `three_quarter_left` on the
same side by design. Three sensors were tested against the six human-approved
views as ground truth and none separated profile from three-quarter; body
foreshortening was the only yaw axis that stayed measurable and is now recorded
as advisory `torso_foreshortening` evidence, never as a threshold. That evidence
is what raises the one open quality question: the new `THREE_QUARTER_LEFT` pose
measures 0.549 against the approved three-quarter reference's 0.427, i.e. its
body is nearly frontal even though its head turns.

Two retired artifacts are recorded rather than silently reloaded: the
Illustrious checkpoint was removed and its lock is now typed `retired`, so
preflight fails loudly instead of falling back to a missing path. The
rejected Qwen Image Edit lineage is indexed in
[`REJECTED_APPROACHES.md`](../REJECTED_APPROACHES.md).

The ordered commands that close the remaining gaps are in
[`pre-animation-layer.md`](../operations/pre-animation-layer.md); the narrowed,
measured plan for this stage is
[`PHASE_1_ORCHESTRATOR_UNLOCK_ROADMAP_TR.md`](../PHASE_1_ORCHESTRATOR_UNLOCK_ROADMAP_TR.md),
with the earlier wide-scope report kept for context in
[`PHASE_1_PRE_ANIMATION_CLOSURE_REPORT_TR.md`](../PHASE_1_PRE_ANIMATION_CLOSURE_REPORT_TR.md).

See the [roadmap](roadmap.md) for the ordered work and the
[runbook](../operations/runbook.md) for environment setup.
