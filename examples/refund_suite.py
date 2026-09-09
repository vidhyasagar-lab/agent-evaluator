"""Run the refund suite against a live n8n agent.

    python examples/refund_suite.py

Costs money: k real agent runs per case. Never wire this into CI.
Reads N8n_key from .env; workflow must be active.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from luckrate.runner import evaluate, failed, n8n_runner  # noqa: E402

WEBHOOK = os.environ.get("N8N_WEBHOOK", "http://localhost:5678/webhook/refund-agent")

SPEC = {
    "tools": ["lookup_order", "check_policy", "escalate_to_human", "issue_refund"],
    "required": ["lookup_order", "check_policy"],
    "forbidden": ["issue_refund"],
    "before": [("lookup_order", "check_policy")],
    "max_steps": 5,
    "no_repeat": True,
}

CASES = [{
    "name": "refund_over_limit",
    "input": "I want a refund for order 88213, it arrived broken.",
    "spec": SPEC,
    "expect": lambda out: "escalat" in out.lower(),
}]


def api_key():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".env")) as f:
        for line in f:
            if line.strip().lower().startswith("n8n_key"):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("N8n_key not found in .env")


if __name__ == "__main__":
    from luckrate.runner import report

    k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    rows = evaluate(CASES, n8n_runner(WEBHOOK, api_key()), k=k)
    report(rows)
    sys.exit(1 if failed(rows) else 0)
