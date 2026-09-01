# Changelog

All notable changes to SELMA Labs will be documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and future releases will
use semantic versioning.

## Unreleased

### Added

- Canonical Akira Character Bible and guarded two-pass anime production pipeline.
- ComfyUI motion, LivePortrait mock, and layered FFmpeg composition boundaries.
- Script breakdown, animation orchestration, dependency injection, and CLI tools.
- Structured issue forms, contribution guidance, security policy, and quality gates.
- Reproducible, approval-gated 10-second Akira motion smoke runner with FFprobe
  evidence reporting.

### Changed

- Repository documentation is organized by architecture, operations, project
  status, and historical material.
- Animation plans now carry an explicit lip-sync decision, camera angles route
  through a provider-neutral reference-view service, and persisted media paths
  use canonical portable storage keys.
- The bundled AnimateDiff workflow uses overlapping context windows for bounded
  GPU memory consumption.
- Motion cache identity now includes the approved source key and frame count,
  preventing stale clips from being reused across changed render inputs.

### Security

- Human approval and persisted committed-candidate checks block unapproved motion
  generation.

## Release policy

The first tagged release will be created after the repository cleanup and security
automation work are merged and the documented quality gates pass on `main`.
