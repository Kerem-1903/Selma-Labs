# Roadmap

This roadmap describes outcomes rather than fixed dates. Work enters the active
set through a tracked GitHub issue and lands through a focused pull request.

## Now — repository and production clarity

- Keep the documentation index, status page, and README aligned.
- Close or supersede stale pull requests and remove merged remote branches after
  verifying that they contain no unique work.
- Complete dependency and security automation.
- Document every public entry point and classify experimental interfaces.

## Now — Akira V2 identity lock

- Generate the face pilot and neutral identity-critical views through the
  standard visual IP-Adapter workflow with automatic QA enabled.
- Add licensed or self-rendered OpenPose maps for remaining action recipes.
- Human-approve the pilot, five-view references, and all 23 dataset samples.
- Reach `training_approved: true`, then train and register Akira V2.
- Pass and human-lock all ten Golden Set cases.

Definition of done: Akira V2 has a recorded model SHA-256, truthful reviewed
captions, zero dataset-audit blockers, and a fully passing human-locked Golden
Set. Until then, scene generation cannot treat the LoRA as production identity.

## Next — Akira pilot animation

- Produce and approve the pilot keyframe set with the locked V2 model.
- Run the two-pass motion workflow against approved candidates.
- Replace the LivePortrait mock with an integration-tested backend.
- Assemble and review the first reproducible pilot master.

## Later — repeatable studio operation

- Publish versioned release notes and sample output packages.
- Add performance budgets for GPU generation and media composition.
- Expand character and shot continuity benchmarks.
- Improve contributor onboarding and label issues suitable for new contributors.

## Definition of done

A milestone is complete only when its tests pass, its operating instructions are
current, generated media has provenance and rights metadata, and the result is
recorded in the changelog or a GitHub release.
