# Source-control safety policy

The workspace contains production source code, generated run output, local
references, and large media. They must not be committed as one undifferentiated
batch.

## Track in normal Git

- Python source under `core/`, `infrastructure/`, `config/`, and `scripts/`
- Tests under `tests/`
- Remotion source under `motion/src/`
- Configuration, lockfiles, CI workflows, and documentation

The command below fails when any source, configuration, or documentation file
is still untracked:

```powershell
.venv\Scripts\python.exe scripts\audit_workspace_tracking.py --fail-on-untracked-source
```

## Track only through Git LFS

Production video and audio (`.mp4`, `.mov`, `.webm`, `.wav`, and `.mp3`) are
covered by `.gitattributes`. Add them only after their source and commercial
usage rights have been recorded. Large binary assets must never enter ordinary
Git history.

Images may stay in normal Git after the same rights audit. Any image above
5 MB should be added to the LFS policy before it is committed.

## Keep local and regenerate

- `output/`, `.selma_runs*`, `.codex_video_review/`, `motion/out/`
- dependency caches and temporary files
- `reference/` until a rights audit explicitly approves each item

## Recovery boundary

A local commit protects against accidental edits, but not disk loss. Full
recovery requires an approved snapshot committed to Git and pushed to a remote.
No remote is currently configured, so the workspace is not yet protected from
machine or drive failure.
