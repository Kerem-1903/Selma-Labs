import re
from typing import List
from core.domain.entities.shot_animation import ShotPlan
from core.domain.entities.character_state import CharacterState

class ScriptBreakdownService:
    def parse_script(self, script_text: str, script_id: str) -> List[ShotPlan]:
        shot_plans = []
        lines = script_text.strip().split('\n')

        current_scene_plan_id = "default_scene"

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Basic parsing logic for dialogue and action
            # E.g. AKIRA: Hello world
            if line.startswith("AKIRA:"):
                dialogue = line[6:].strip()
                character_state = CharacterState(
                    character_id="akira",
                    active_outfit_id="default_outfit",
                    injuries=[],
                    held_objects=[]
                )
                shot_plans.append(
                    ShotPlan(
                        id=f"shot_{i}",
                        script_id=script_id,
                        scene_plan_id=current_scene_plan_id,
                        prompt=f"akira_girl speaking: {dialogue}",
                        duration_seconds=5.0, # Mock duration
                        character_state=character_state
                    )
                )
            else:
                # Treat as action description
                character_state = CharacterState(
                    character_id="akira",
                    active_outfit_id="default_outfit",
                    injuries=[],
                    held_objects=[]
                )
                shot_plans.append(
                    ShotPlan(
                        id=f"shot_{i}",
                        script_id=script_id,
                        scene_plan_id=current_scene_plan_id,
                        prompt=line,
                        duration_seconds=3.0, # Mock duration
                        character_state=character_state
                    )
                )

        return shot_plans
