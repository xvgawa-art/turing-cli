import json
from pathlib import Path


def status():
    """查看当前审计状态"""
    state_path = Path("./deliverables/.turing/state.json")
    if not state_path.exists():
        print("No audit state found")
        return False

    try:
        with open(state_path) as f:
            state = json.load(f)

        print(f"Audit ID: {state.get('audit_id', 'N/A')}")
        print(f"Start Time: {state.get('start_time', 'N/A')}")

        vulns = state.get("vulnerabilities", {})
        total = len(vulns)
        completed = sum(1 for v in vulns.values() if v.get("status") == "completed")
        failed = sum(1 for v in vulns.values() if v.get("status") == "failed")

        print(f"\nVulnerabilities: {total} total, {completed} completed, {failed} failed")
        return True
    except Exception as e:
        print(f"Error reading state file: {e}")
        return False
