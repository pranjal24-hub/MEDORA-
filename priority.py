import subprocess
import os

# Path to the compiled C++ executable
SCHEDULER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "priority-scheduler", "scheduler.exe"
)

def get_priority_order(emergencies: list[dict]) -> list[int]:
    """
    emergencies: list of dicts like [{"id": 101, "severity": "CRITICAL"}, ...]
    returns: list of ids in priority order
    """
    if not emergencies:
        return []

    # Build input text: "id severity" per line
    input_text = "\n".join(f"{e['id']} {e['severity']}" for e in emergencies)

    result = subprocess.run(
        [SCHEDULER_PATH],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode != 0:
        raise RuntimeError(f"Priority scheduler failed: {result.stderr}")

    # Parse output back into ordered list of ids
    ordered_ids = []
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if parts:
            ordered_ids.append(int(parts[0]))

    return ordered_ids