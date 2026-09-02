# SELMA Anime Pre-Production — P1–P8

This branch implements the complete pre-animation contract. It intentionally
stops before motion generation: GPU work may consume only artifacts that pass
all preceding locks.

## Pipeline

| Phase | Artifact | Hard gate |
|---|---|---|
| P1 | `EpisodeScript` draft | Structured episode, sequence, scene, dialogue and ability data |
| P2 | `StoryDevelopmentResult` | Deterministic canon report plus focused AI reviewer reports |
| P3 | Creative, world and character canon | Locked versioned bibles; human story approval is audited |
| P4 | `VisualStyleBible` | Locked palette, line, cel-shading and camera language |
| P5 | `CharacterGoldenSet` | Exactly 10 scenarios; identity ≥ 0.90, style/anatomy ≥ 0.85, each human-approved |
| P6 | `EpisodeProductionPlan` | Locked story becomes Episode → Sequence → Scene → Directed Shot |
| P7 | `AnimaticProject` | One committed storyboard frame per shot, scratch audio for dialogue, 24 FPS, human lock |
| P8 | `AnimationReadyPackage` | Locked animatic + Golden Set + every required binary asset |

No later phase repairs or silently ignores an earlier failure.

## Canon assets

The active version-controlled canon lives in `assets/preproduction/` and Akira's
combined visual/narrative identity lives in `assets/character_bibles/akira.json`.
Named third-party works appear only in originality guardrails: their presence in
a generated screenplay is a blocking imitation-risk violation.

## Local story development

The default structured story adapter uses Ollama and `qwen3:8b`. It runs the
writer, dialogue editor, continuity reviewer, character-voice reviewer and final
editor through explicit JSON contracts. Configure with:

```text
OLLAMA_API_URL=http://localhost:11434/api/generate
STORY_DEVELOPMENT_MODEL=qwen3:8b
```

The domain and application layers know no Ollama concepts; an API-backed adapter
can replace it without changing the pipeline.

## Golden Set operation

`CharacterGoldenSetService` sends the ten fixed scenarios through the configured
`KeyframeGenerationPort`, so both the offline fake and ComfyUI adapters work.
Copy `assets/preproduction/golden-set-review.example.json`, enter measured scores
and set `human_approved` only after visual inspection. A failing or incomplete set
cannot lock and P8 refuses it.

The ten scenarios are: front face, left profile, full body, run, katana grip,
two-character dialogue, rain rooftop, impact action, wide street and determined
expression.

## Animatic

`AnimaticPlanningService` verifies storyboard and scratch-audio assets before
building a contiguous 24 FPS timeline. `RemotionAnimaticExporter` materializes
provider-neutral storage objects under `motion/public/anime-animatic/<id>/` and
writes `props.json`. Preview or render the registered composition with:

```text
cd motion
npm ci
npx remotion studio --no-open
npx remotion render src/index.ts AnimeAnimatic output.mp4 --props=public/anime-animatic/<id>/props.json
```

The animatic must be watched and locked by a named human before packaging.

## P8 package contract

Every shot is copied into an isolated portable storage prefix:

```text
packages/<shot-id>/
  shot-contract.json
  start-keyframe.png
  end-keyframe.png
  background-clean.png
  character-mask.png
  dialogue.wav
  effects-spec.json
```

`AnimationReadyPackagingService` verifies every source exists and records the
exact Golden Set model and revision in `shot-contract.json`. These packages are
the only approved input to the future animation/GPU stage.

## Verification

Run Python and Remotion checks before merge:

```text
python -m pytest -q
cd motion
npm run typecheck
npx remotion still src/index.ts AnimeAnimatic smoke.png --frame=0
```
