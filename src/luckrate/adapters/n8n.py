"""n8n adapter. Confirmed against n8n 2.38.1 execution data.

Input is the payload from GET /api/v1/executions/<id>?includeData=true.
"""
from luckrate.schema import RESULT_CAP, Step


def from_n8n(execution):
    """Normalize an n8n execution into a trajectory.

    A run entry is a tool call exactly when it has an `ai_tool` inputOverride,
    so no node allow-list is needed.
    """
    run_data = execution["data"]["resultData"]["runData"]
    starts = [r.get("startTime", 0) for runs in run_data.values() for r in runs]
    base = min(starts) if starts else 0

    rows = []
    for node, runs in run_data.items():
        for r in runs:
            args = _args(r.get("inputOverride"))
            if args is None:
                continue
            rows.append((
                # executionIndex is a monotonic int across the whole execution;
                # startTime only has millisecond resolution.
                r.get("executionIndex", r.get("startTime", 0)),
                Step(
                    tool=node,
                    args=args,
                    ok=r.get("executionStatus") == "success",
                    result=_result(r.get("data")),
                    t=r.get("startTime", 0) - base,
                ),
            ))
    return [s for _, s in sorted(rows, key=lambda row: row[0])]


def _args(input_override):
    """Tool arguments, or None if this run is not a tool call."""
    try:
        args = dict(input_override["ai_tool"][0][0]["json"])
    except (TypeError, KeyError, IndexError):
        return None
    # The tool-calling layer injects its own call id alongside the real
    # arguments. It is identifier-shaped and grounded in nothing, so leaving it
    # in would make every single tool call raise a false "ungrounded" warning.
    args.pop("id", None)
    return args


def _result(data):
    try:
        return str(data["ai_tool"][0][0]["json"]["response"])[:RESULT_CAP]
    except (TypeError, KeyError, IndexError):
        return ""
