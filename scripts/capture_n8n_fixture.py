"""Fetch one n8n execution, scrub it, and save it as a test fixture.

    python scripts/capture_n8n_fixture.py <execution_id> <fixture_name>

Reads N8n_key from .env. Fixtures go to tests/fixtures/<fixture_name>.json and
are committed to a public repo, so scrubbing is not optional.
"""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("N8N_URL", "http://localhost:5678")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def api_key():
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            if line.strip().lower().startswith("n8n_key"):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("N8n_key not found in .env")


def fetch(execution_id, key):
    url = "{}/api/v1/executions/{}?includeData=true".format(BASE, execution_id)
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def scrub(ex):
    """Remove anything identifying. Replace rather than delete, so the fixture
    still exercises the adapter's parsing."""
    ex.pop("usedPrivateCredentials", None)
    for node in ex.get("workflowData", {}).get("nodes", []):
        if node.get("credentials"):
            node["credentials"] = {}
        # the Azure deployment name is account-identifying
        if "model" in node.get("parameters", {}):
            node["parameters"]["model"] = "test-deployment"
    return ex


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    execution_id, name = sys.argv[1], sys.argv[2]
    ex = scrub(fetch(execution_id, api_key()))

    out_dir = os.path.join(ROOT, "tests", "fixtures")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ex, f, indent=2, sort_keys=True)

    tools = [
        n for n, runs in ex["data"]["resultData"]["runData"].items()
        if any("ai_tool" in (r.get("inputOverride") or {}) for r in runs)
    ]
    print("{}  ({} bytes)  tool nodes: {}".format(path, os.path.getsize(path), ", ".join(tools)))


if __name__ == "__main__":
    main()
