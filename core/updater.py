import subprocess
import os
import sys
import time
from pathlib import Path

def run_command(command, cwd=None):
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def update_suite():
    """Execute the full update lifecycle."""
    root = Path(__file__).parent.parent.absolute()
    print(f"Starting update process in: {root}")

    # 1. Fetch changes
    print("Fetching remote changes...")
    success, output = run_command("git fetch", cwd=root)
    if not success:
        print(f"Error fetching changes: {output}")
        return False

    # 2. Check if update is actually needed (optional but good)
    # For now, we'll proceed with pull regardless as requested

    # 3. Stash local changes
    print("Stashing local changes...")
    success, output = run_command("git stash", cwd=root)
    stashed = "No local changes to save" not in output and success
    print(output)

    # 4. Pull latest version
    print("Pulling latest version...")
    success, output = run_command("git pull", cwd=root)
    if not success:
        print(f"Error pulling changes: {output}")
        if stashed:
            print("Attempting to restore stash before aborting...")
            run_command("git stash pop", cwd=root)
        return False
    print(output)

    # 5. Restore stash if needed
    if stashed:
        print("Restoring local changes...")
        success, output = run_command("git stash pop", cwd=root)
        if not success:
            print(f"Warning: Failed to pop stash: {output}")

    # 6. Update dependencies
    print("Updating dependencies...")
    # Using sys.executable to ensure we use the same python environment
    success, output = run_command(f'"{sys.executable}" -m pip install -e .', cwd=root)
    if not success:
        print(f"Warning: Failed to update dependencies: {output}")
    else:
        print("Dependencies updated successfully.")

    print("\nUpdate process complete.")
    return True

if __name__ == "__main__":
    if update_suite():
        sys.exit(0)
    else:
        sys.exit(1)
