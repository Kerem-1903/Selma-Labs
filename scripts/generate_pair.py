import argparse, subprocess, os, sys

def main():
    parser = argparse.ArgumentParser(description="Generate start and end images using double ControlNet (OpenPose + Depth/Lineart).")
    parser.add_argument("--prompt_start", required=True, help="Prompt for the start frame.")
    parser.add_argument("--prompt_end", required=True, help="Prompt for the end frame.")
    parser.add_argument("--output_dir", default="outputs", help="Directory to save generated images.")
    parser.add_argument("--workflow", default="workflow_double_controlnet.json", help="ComfyUI workflow file.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Build the command that launches ComfyUI with the given workflow and prompts.
    # We inject the prompts via environment variables that the workflow can read.
    env = os.environ.copy()
    env["PROMPT_START"] = args.prompt_start
    env["PROMPT_END"] = args.prompt_end

    cmd = [sys.executable, "-m", "comfy.cli", "--workflow", args.workflow, "--output", args.output_dir]
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, env=env)
    print("Generation completed. Images saved in", args.output_dir)

if __name__ == "__main__":
    main()
