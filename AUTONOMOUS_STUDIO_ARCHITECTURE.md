# Autonomous Studio Architecture (v2 Domain Model)

This document outlines the v2 Domain Model introduced during **Sprint A1** to establish the foundation for the Autonomous Animation Studio. The goal of this architecture is to transition SELMA Labs from a "Short-Form Factory" into an intelligent production system that maintains continuity across shots and scenes, rather than generating isolated prompt-based clips.

## The Two-Axis Production Strategy

SELMA Labs now runs two complementary production tracks:

1. **Existing Short-Form Factory (v1):** The proven pipeline utilizing `PipelineRun`, `ScenePlan`, `WhisperX`, and Pexels stock footage for fast, localized content generation.
2. **Autonomous Studio (v2):** The new intelligence engine focusing on semantic shot contracts, character continuity, and selective defect repair.

## Core Domain Entities & Value Objects (Sprint A1)

To build the Autonomous Studio, we replaced string prompts with structural, immutable constraints and a living continuity state.

### 1. `Character` (Immutable Identity Constraints)
Located at `core.domain.entities.character`. A Character represents the immutable base definition (The "Character Bible").
- **Fields:** `id`, `name`, `face_identity_notes`, `body_proportions`
- **Purpose:** Prevents the AI from hallucinating a new physical form in every shot.

### 2. `Outfit` (Value Object)
Located at `core.domain.value_objects.outfit`.
- **Fields:** `id`, `character_id`, `description`, `reference_image_keys`
- **Purpose:** Decouples clothing from character identity. Allows a single character (e.g., "Akira") to change clothes (e.g., from "school_uniform" to "battle_damaged") without breaking their underlying facial/body consistency.

### 3. `CharacterState` (Mutable Runtime State)
Located at `core.domain.entities.character_state`.
- **Fields:** `character_id`, `active_outfit_id`, `injuries`, `held_objects`
- **Purpose:** Tracks the *current* state of a character at a specific moment in time (e.g., holding a broken sword, wearing the damaged outfit).

### 4. `ContinuityState` (World Snapshot)
Located at `core.domain.entities.continuity_state`.
- **Fields:** `id`, `world_snapshot` (Dict mapping `character_id` to `CharacterState`)
- **Purpose:** Acts as the automated script supervisor. When an event happens in Shot 38 (a jacket tears), `ContinuityState` ensures Shot 39 knows about it.

### 5. `ShotContract` (The Semantic Definition)
Located at `core.domain.entities.shot_contract`.
- **Fields:** `id`, `camera_constraints`, `action_constraints`, `visual_constraints`, `required_character_states`
- **Purpose:** Replaces the text prompt. A shot is defined by its camera angles, required actions, and the explicit continuity states of the actors in it.
- **Important Design Choice:** There is explicitly *no* text prompt field here. Prompts are an implementation detail of the `VideoGenerationPort` adapter, not a domain concept.

### 6. `QCReport` (Decision Matrix)
Located at `core.domain.value_objects.qc_report`.
- **Fields:** `decision` (PASS/REJECT/REPAIR), `metrics`, `defects`
- **Purpose:** Enforces quality control. Instead of a binary success/fail that discards 4 seconds of video for one bad frame, the report highlights exactly what failed (e.g., "left eye changes shape"), enabling selective regeneration.

## New Domain Ports (Sprint A1)

1. **`ConsistencyJudgePort`**:
   - `async def judge(shot_contract, video_asset) -> QCReport`
   - Evaluates a generated video asset against its `ShotContract` and returns a `QCReport`.
2. **`ContinuityRepositoryPort`**:
   - `async def save(state) / load(id)`
   - Handles the persistence of the living world snapshot across generation cycles.

## Next Steps

With the domain foundation (Sprint A1) secured and unit tested, upcoming sprints will focus on:
- **A2 Continuity Engine:** Implementing the repository and event-sourcing for character states.
- **A3 Character Bible:** Asset storage and retrieval for reference keys.
- **A4 Vision Judge:** Implementing the `ConsistencyJudgePort` using AI vision models.
- **A5 Keyframe Generation:** Creating static anchor frames before full motion.
- **A6 VideoGenerationPort:** Adapting ComfyUI, Wan, or LTX to translate `ShotContract` into dynamic prompts.
- **A7 Selective Repair Loop:** Utilizing the `QCReport` to implement targeted re-renders.
