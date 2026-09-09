"""Runner tests replay recorded fixtures. No network, no LLM, no keys."""
import json
import os

from luckrate.adapters.n8n import from_n8n
from luckrate.runner import evaluate, failed, report

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

SPEC = {
    "tools": ["lookup_order", "check_policy", "escalate_to_human", "issue_refund"],
    "required": ["lookup_order", "check_policy"],
    "forbidden": ["issue_refund"],
    "before": [("lookup_order", "check_policy")],
    "max_steps": 5,
    "no_repeat": True,
}


def replay(*names):
    """A runner that returns recorded trajectories in order, cycling."""
    loaded = []
    for n in names:
        with open(os.path.join(FIXTURES, n + ".json"), encoding="utf-8") as f:
            loaded.append(from_n8n(json.load(f)))
    calls = {"i": 0}

    def run(_task):
        steps = loaded[calls["i"] % len(loaded)]
        calls["i"] += 1
        return steps, "escalated for manager approval"

    return run


def case(name="refund", expect=lambda o: "escalated" in o):
    return {"name": name, "input": "refund for order 88213, it arrived broken",
            "spec": SPEC, "expect": expect}


def test_clean_runs_are_not_lucky_and_do_not_fail(capsys):
    rows = evaluate([case()], replay("n8n_good"), k=3)
    assert len(rows) == 3
    assert report(rows) == 0.0
    assert failed(rows) is False
    assert "luck rate 0%" in capsys.readouterr().out


def test_warn_only_run_is_lucky_but_still_passes_the_gate():
    # fabricates: escalated correctly, invented the order id -> the whole point
    rows = evaluate([case()], replay("n8n_fabricates"), k=3)
    assert report(rows) == 1.0
    assert failed(rows) is False


def test_hard_violation_fails_the_gate_on_one_occurrence():
    rows = evaluate([case()], replay("n8n_good", "n8n_good", "n8n_skips"), k=3)
    assert failed(rows) is True


def test_soft_violation_needs_a_majority_to_fail():
    assert failed(evaluate([case()], replay("n8n_loops", "n8n_good", "n8n_good"), k=3)) is False
    assert failed(evaluate([case()], replay("n8n_loops", "n8n_loops", "n8n_good"), k=3)) is True


def test_luck_rate_is_undefined_when_nothing_passes_output(capsys):
    rows = evaluate([case(expect=lambda o: False)], replay("n8n_fabricates"), k=2)
    assert report(rows) is None
    assert "luck rate -" in capsys.readouterr().out
