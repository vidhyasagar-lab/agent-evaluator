"""LangGraph / LangChain adapter.

Input is the message list from a graph run -- `graph.invoke(...)["messages"]`,
or the same thing serialized to dicts. No langchain import: the two shapes are
read through one accessor, which also keeps this package dependency-free.
"""
from luckrate.schema import RESULT_CAP, Step


def from_langgraph(messages):
    """Normalize a LangChain message list into a trajectory.

    Steps are appended when the call is *issued*, not when its result arrives,
    so ordering survives and a tool call that never returned still appears.
    """
    steps, by_id = [], {}
    for m in messages:
        for tc in _get(m, "tool_calls") or []:
            step = Step(tool=_get(tc, "name", ""), args=dict(_get(tc, "args") or {}))
            by_id[_get(tc, "id")] = step
            steps.append(step)

        call_id = _get(m, "tool_call_id")
        if call_id in by_id:
            step = by_id[call_id]
            step.ok = _get(m, "status", "success") != "error"
            step.result = str(_get(m, "content", ""))[:RESULT_CAP]
    # ponytail: Step.t stays 0.0 -- LangChain messages carry no timestamps.
    # Ordering comes from the list. Fill t if a source ever provides one.
    return steps


def _get(obj, key, default=None):
    """Read a field from either a LangChain message object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
