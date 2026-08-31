import os
import shutil

def cleanup():
    scripts_dir = "/app/scripts"
    archive_dir = os.path.join(scripts_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    # Move sprint files to archive (or anything named with 'sprint')
    # Actually, the instructions say "loose root-level sprint scripts"
    # But there are no such files in the root dir right now.

    # Let's search for python files in scripts folder that start with a[0-9]
    for filename in os.listdir(scripts_dir):
        if filename.startswith("a") and filename[1].isdigit() and filename.endswith(".py"):
            src = os.path.join(scripts_dir, filename)
            dst = os.path.join(archive_dir, filename)
            shutil.move(src, dst)
            print(f"Moved {filename} to archive/")

if __name__ == "__main__":
    cleanup()
