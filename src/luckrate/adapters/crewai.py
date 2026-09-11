"""CrewAI adapter for normalizing crew trajectory payloads into Step objects."""

from luckrate.schema import RESULT_CAP, Step


def from_crewai(raw):
    """Normalize a CrewAI trajectory payload into a list of Step objects.

    Handles OpenTelemetry spans or tool callback dictionaries emitted during a crew run.
    """
    steps = []

    # CrewAI trajectories can be a list of step/tool spans or a dict wrapping steps/tasks
    items = raw if isinstance(raw, list) else raw.get("steps", raw.get("tasks", []))

    for item in items:
        # Extract tool name or default to 'tool_call'
        tool_name = _get(item, "tool") or _get(item, "name", "tool_call")

        # Extract arguments and remove framework plumbing (e.g., tool_call_id, id)
        args = _get(item, "args") or _get(item, "input", {})
        if isinstance(args, dict):
            args = dict(args)
            args.pop("id", None)
            args.pop("tool_call_id", None)
        else:
            args = {"raw_input": str(args)}

        # Extract agent identifier (role or agent name)
        agent = _get(item, "agent") or _get(item, "role", "main")

        # Status flag
        status = _get(item, "status", "success")
        ok = status not in ("error", "failed", False)

        # Result string capped by RESULT_CAP
        result_val = _get(item, "result") or _get(item, "output", "")
        result = str(result_val)[:RESULT_CAP]

        # Timestamp offset if available
        t = float(_get(item, "t", 0.0))

        steps.append(
            Step(
                tool=str(tool_name),
                args=args,
                ok=ok,
                result=result,
                t=t,
                agent=str(agent),
            )
        )

    return steps


def _get(obj, key, default=None):
    """Safely fetch keys from dicts or attributes from span objects."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
