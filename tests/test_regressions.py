"""Bugs found by auditing the shipped code. Each failed before its fix."""
import pytest

from luckrate import Step, check
from luckrate.adapters.langgraph import from_langgraph
from luckrate.adapters.n8n import from_n8n
from luckrate.runner import evaluate, failed


def _tool_run(**kw):
    run = {"executionStatus": "success", "inputOverride": {"ai_tool": [[{"json": {}}]]}}
    run.update(kw)
    return run


def test_ordering_does_not_mix_executionindex_with_starttime():
    # 'early' ran first but carries no executionIndex. Sorting 9 against 1000
    # compares different number spaces and put 'late' first.
    ex = {"data": {"resultData": {"runData": {
        "early": [_tool_run(startTime=1000)],
        "late": [_tool_run(startTime=2000, executionIndex=9)],
    }}}}
    assert [s.tool for s in from_n8n(ex)] == ["early", "late"]


def test_tool_result_does_not_pair_with_an_idless_call():
    class AI:
        tool_calls = [{"name": "lookup_order", "args": {"order_id": "88213"}}]

    class ToolMsg:
        tool_call_id, content, status = None, "belongs to nothing", "success"

    # Both ids were None, so the result leaked onto an unrelated step.
    assert from_langgraph([AI(), ToolMsg()])[0].result == ""


def test_spec_typo_raises_instead_of_blaming_the_agent():
    spec = {"tools": ["lookup_order"], "required": ["lookup_ordr"]}
    with pytest.raises(ValueError, match="not in its 'tools' vocabulary"):
        check([Step("lookup_order", {})], spec, "")


def test_spec_validation_covers_forbidden_and_before():
    with pytest.raises(ValueError):
        check([], {"tools": ["a"], "forbidden": ["typo"]}, "")
    with pytest.raises(ValueError):
        check([], {"tools": ["a"], "before": [("a", "typo")]}, "")


def test_a_failing_run_does_not_discard_completed_runs():
    calls = {"n": 0}

    def flaky(_task):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("network blip")
        return [Step("lookup_order", {"order_id": "88213"})], "escalated"

    rows = evaluate(
        [{"name": "c", "input": "refund 88213", "spec": {}, "expect": lambda o: True}],
        flaky, k=5)

    assert len(rows) == 5                      # nothing lost
    assert sum(r["output_ok"] for r in rows) == 4
    assert failed(rows) is True                # an unfinished suite certifies nothing
