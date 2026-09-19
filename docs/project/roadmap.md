# Roadmap

This roadmap describes outcomes rather than fixed dates. Work enters the active
set through a tracked GitHub issue and lands through a focused pull request.

## Now — engineering hygiene

- Keep the static-analysis gate green and tighten the lint ratchet in the order
  recorded in [the code review](../CODE_REVIEW.md). Stage 2 is done and blocking:
  pyflakes, import order, pyupgrade, bugbear and the blind-except guards, with the
  whole tree clean. Next are `SIM`, the bandit rules and the remaining
  `raise ... from` sites.
- Land every future change as a focused pull request. The character-quality
  working set already reached `main`'s branch as one commit; re-splitting that
  history is not worth a rebase, so the discipline starts from here.
- Extend the dependency lock to the GPU runtime set. The quality-gate lock
  (`requirements-ci.lock.txt`) is in place and CI installs it; `requirements.txt`
  still resolves from `>=` because compiling it needs a Linux/GPU machine.
- Move the remaining `cli/main.py` handlers into `cli/*_commands.py`. The argument
  parser is extracted already (`cli/parsers/`), so what is left is command logic.
- Widen the blocking type check. `core/domain`, `config` and `cli` are clean and
  blocking; `core/application` and `infrastructure` carry 146 findings reported by
  the advisory CI step and enter the gate as they reach zero.

## Now — repository and production clarity

- Keep the documentation index, status page, and README aligned.
- Implement and test the accepted pre-GPU Wan execution contract in
  [ADR-009](../adr/ADR-009-wan-job-execution-contract.md) before connecting a
  real provider or GPU instance.
- Close or supersede stale pull requests and remove merged remote branches after
  verifying that they contain no unique work.
- Complete dependency and security automation.
- Document every public entry point and classify experimental interfaces.

## Current foundation — reference-driven character creation

- Accept a versioned structured character brief.
- Generate five design candidates with the configured SELMA image provider.
- Lock one human-selected design, then atomically record its canonical image,
  brief, face anchor and full-body anchor hashes.
- Generate the seven neutral design views—face close-up, front, left/right
  profile, left/right three-quarter and back—through the ordered reference
  chain rooted in the two locked anchors.
- Keep action poses outside this stage; they begin only after the design-view
  pack is approved.
- Keep LoRA outside the default production path.

Definition of done: every production character starts from a confirmed brief,
has one hash-locked canonical image plus two locked anchors, and exposes only
approved reference assets to shot generation.

## Next — close the pre-animation layer

The ordered commands live in
[`pre-animation-layer.md`](../operations/pre-animation-layer.md);
`scripts/check_anime_readiness.py --stage visual` is the gate.

- Regenerate the QC-gated seven-view pack with the FLUX.2 source-led dialect
  (`--seeds N` to sweep and keep the least-drifted candidate per view).
- Review the generated `contact-sheets/views.png` against the twelve signed
  human checks in the character acceptance list, with `drift-report.json` beside
  it.
- Lock the accepted pack with
  `python -m cli.main character approve-view-pack --character <id> --version <v>`.
- Complete the series style lock: creative receipt, pending production lock, and
  the derived smoke-test receipt that `mark-production-compatible` consumes.
- Generate and approve the three-pose pack, which fails closed until the
  seven-view pack is approved.
- Start animation work only after all three gates pass.

## Later — repeatable studio operation

- Install the three missing required model files, regenerate their real hashes
  in `models.lock.json`, and complete the live preflight dry-run.
- Publish versioned release notes and sample output packages.
- Add performance budgets for GPU generation and media composition.
- Expand character and shot continuity benchmarks.
- Improve contributor onboarding and label issues suitable for new contributors.

## Definition of done

A milestone is complete only when its tests pass, its operating instructions are
current, generated media has provenance and rights metadata, and the result is
recorded in the changelog or a GitHub release.
