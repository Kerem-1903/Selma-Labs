import argparse
import asyncio
from config.container import create_container

def main():
    parser = argparse.ArgumentParser(description="Selma-Labs CLI")
    subparsers = parser.add_subparsers(dest="command")

    # character show subcommand
    character_parser = subparsers.add_parser("character")
    character_subparsers = character_parser.add_subparsers(dest="subcommand")
    show_parser = character_subparsers.add_parser("show")

    # script breakdown subcommand
    script_parser = subparsers.add_parser("script")
    script_subparsers = script_parser.add_subparsers(dest="subcommand")
    breakdown_parser = script_subparsers.add_parser("breakdown")
    breakdown_parser.add_argument("--input", required=True, help="Input script file")

    # render shot subcommand
    render_parser = subparsers.add_parser("render")
    render_subparsers = render_parser.add_subparsers(dest="subcommand")
    shot_parser = render_subparsers.add_parser("shot")
    shot_parser.add_argument("--shot-id", required=True, help="Shot ID to render")

    args = parser.parse_args()
    container = create_container()

    if args.command == "character" and args.subcommand == "show":
        print("Akira:")
        print("Traits: black hair with front red highlights, amber eyes")
        print("Wardrobe: cropped jacket with red inner lining, combat pants, knee pads, combat boots")
        print("Trigger prompt: akira_girl, black hair with red highlights, amber eyes, cropped dark jacket, red collar lining, combat pants, knee pads, combat boots")

    elif args.command == "script" and args.subcommand == "breakdown":
        script_breakdown_service = container["script_breakdown_service"]
        with open(args.input, "r") as f:
            script_text = f.read()
        shot_plans = script_breakdown_service.parse_script(script_text, script_id="script_1")
        print(f"Parsed {len(shot_plans)} shots:")
        for shot in shot_plans:
            print(f"Shot {shot.id}: {shot.prompt}")

    elif args.command == "render" and args.subcommand == "shot":
        # Mocking shot plan, background, and audio for demonstration
        from core.domain.entities.shot_animation import ShotPlan
        from core.domain.entities.character_state import CharacterState
        animation_orchestrator_service = container["animation_orchestrator_service"]

        character_state = CharacterState(
            character_id="akira",
            active_outfit_id="default",
            injuries=[],
            held_objects=[]
        )
        shot_plan = ShotPlan(
            id=args.shot_id,
            script_id="script_1",
            scene_plan_id="scene_1",
            prompt="akira_girl, looking at camera",
            duration_seconds=5.0,
            character_state=character_state
        )

        async def run_render():
            output_path = await animation_orchestrator_service.orchestrate_shot(
                shot_plan=shot_plan,
                background_image_path="dummy_bg.jpg",
                audio_path="dummy_audio.wav",
                output_path=f"output_{args.shot_id}.mp4"
            )
            print(f"Rendered shot to {output_path}")

        asyncio.run(run_render())
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
