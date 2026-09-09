"""The canonical trajectory schema.

This is a public contract: adapters are written against it, so fields are not
added or renamed after v0.1 without a major version bump.
"""
from dataclasses import dataclass, field

#: Adapters truncate Step.result here. Provenance searches results, so cutting
#: too hard makes legitimately-sourced ids look fabricated.
RESULT_CAP = 8000


@dataclass
class Step:
    """One tool invocation in an agent's trajectory.

    tool:   node / tool name, as it appears in the agent's graph
    args:   call arguments
    ok:     did the call succeed
    result: output text; provenance checking searches this
    t:      milliseconds from run start
    agent:  which agent produced the step; multi-agent hook, unused until CrewAI
    """

    tool: str
    args: dict = field(default_factory=dict)
    ok: bool = True
    result: str = ""
    t: float = 0.0
    agent: str = "main"
