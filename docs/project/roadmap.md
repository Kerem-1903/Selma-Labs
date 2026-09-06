# Roadmap

This roadmap describes outcomes rather than fixed dates. Work enters the active
set through a tracked GitHub issue and lands through a focused pull request.

## Now — repository and production clarity

- Keep the documentation index, status page, and README aligned.
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

## Next — approve the character turnaround

- Live-generate the QC-gated seven-view pack from a selected canonical design.
- Review the generated `contact-sheets/views.png` for identity, outfit and
  silhouette continuity.
- Lock the accepted pack with `python -m selma.cli approve-view-pack --character
  <id> --version v1`.
- Start pose and animation work only after this gate passes.

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
