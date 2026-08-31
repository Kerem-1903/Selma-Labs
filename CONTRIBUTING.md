# Contributing to SELMA Labs

Thank you for helping improve SELMA Labs. The project is an early-stage,
local-first AI video production system, so small, focused changes with clear
verification are the easiest to review.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Security-sensitive findings belong in the private channel described in
[SECURITY.md](SECURITY.md), not in a public issue.

## Before you start

- Search existing issues and pull requests before opening a duplicate.
- Use an issue form for bugs, feature proposals, or provider/runtime problems.
- Keep a pull request focused on one outcome.
- For a substantial architectural change, open a feature request first so the
  approach can be discussed before implementation.

## Development setup

The standard environment requires Python 3.10 or newer plus FFmpeg and
FFprobe on `PATH`. Remotion changes also require Node.js 22 and npm. ComfyUI is
optional unless the change exercises a local generation workflow.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add only the credentials needed for your
local provider choices. Never commit `.env`, tokens, private media, model
weights, or personal filesystem paths.

For Remotion work:

```bash
cd motion
npm ci
```

## Branches and commits

Create a short-lived branch from the latest `main`. Descriptive prefixes such
as `feat/`, `fix/`, `docs/`, and `test/` are encouraged. Automated Codex work
uses the `codex/` prefix.

Write an imperative commit subject that explains the outcome, for example:

```text
fix: preserve portable asset keys during retry
```

## Project invariants

Changes must preserve these production rules:

1. Never bypass a human approval boundary.
2. Store portable storage keys instead of machine-specific absolute paths.
3. Retry only failures that are explicitly classified as transient.
4. Validate a draft before a long or expensive render.
5. Preserve render duration, seed, profile, failure, and cost evidence.
6. Require provenance and usage-rights evidence for publishable media.
7. Keep provider-specific behavior behind the existing port boundaries.

Generated or supplied media must be original, licensed, or otherwise suitable
for redistribution. Describe its source and rights in the pull request.

## Verification

Run the checks that cover your change. The complete local quality baseline is:

```bash
python -m pytest tests -q
python scripts/verify_pipeline.py
python scripts/render_smoke_test.py
python scripts/audit_workspace_tracking.py --fail-on-untracked-source
```

For Remotion changes, also run:

```bash
cd motion
npm run typecheck
npm run smoke:still
```

Provider-backed creative output may require local models, licensed inputs, or
paid credentials. If a check cannot run locally, explain why in the pull
request and provide the strongest offline evidence available.

## Pull requests

Complete the repository pull request template. A reviewable contribution:

- explains what changed and why;
- links the relevant issue when one exists;
- includes tests or a reason tests are not needed;
- calls out schema, configuration, migration, media-rights, and cost effects;
- includes screenshots or sample output for visible changes; and
- leaves the automated Quality Gates passing.

Maintainers may ask for a pull request to be split, rebased, or revised before
merge. Contributions are submitted under the repository's
[Apache License 2.0](LICENSE).
