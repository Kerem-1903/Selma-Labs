# Changelog

All notable changes to SELMA Labs will be documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and future releases will
use semantic versioning.

## Unreleased

### Added

- View-scoped character prompts and captions, caption/view coherence auditing,
  and fail-closed quarantine rules for unaudited reference candidates.
- Anime-safe visual IP-Adapter plus img2img reference routing and an Akira V2
  dataset-to-Golden-Set operating runbook.
- Canonical Akira Character Bible and guarded two-pass anime production pipeline.
- ComfyUI motion, LivePortrait mock, and layered FFmpeg composition boundaries.
- Script breakdown, animation orchestration, dependency injection, and CLI tools.
- Structured issue forms, contribution guidance, security policy, and quality gates.

### Changed

- Character LoRA operation now defaults to model strength `0.45`, CLIP strength
  `0.0`, and lower visual identity conditioning when an approved LoRA is active.
- Repository documentation is organized by architecture, operations, project
  status, and historical material.

### Security

- Human approval and persisted committed-candidate checks block unapproved motion
  generation.

## Release policy

The first tagged release will be created after the repository cleanup and security
automation work are merged and the documented quality gates pass on `main`.
