"""Score a trajectory against a constraint spec.

Violations are returned as strings prefixed by severity:

    (none)   hard - fails a build on a single occurrence
    soft:         - fails only if most runs in a k-run batch fail
    warn:         - never fails a build; a review signal
"""
import json
import re

#: Values that look like identifiers but carry no provenance.
LITERALS = {"true", "false", "none", "null", "yes", "nan"}

#: Identifier-ish: no spaces, 3-40 chars. Prose arguments are skipped on purpose.
ID_RE = re.compile(r"^[\w.@:/+-]{3,40}$")


def check(steps, spec, task_input=""):
    """Return the violations a trajectory commits against a spec.

    steps:      list[Step], in call order
    spec:       dict of constraints; see README
    task_input: the agent's input, used as the provenance root
    """
    v = []
    names = [s.tool for s in steps]

    for name in dict.fromkeys(names):  # dedupe, preserve order
        if spec.get("tools") and name not in spec["tools"]:
            v.append("unknown tool: {}".format(name))
    for tool in spec.get("required", []):
        if tool not in names:
            v.append("missing required tool: {}".format(tool))
    for tool in spec.get("forbidden", []):
        if tool in names:
            v.append("called forbidden tool: {}".format(tool))
    for a, b in spec.get("before", []):
        if b in names and a not in names:
            v.append("{} called without {}".format(b, a))
        elif a in names and b in names and names.index(a) > names.index(b):
            v.append("{} must come before {}".format(a, b))

    if spec.get("max_steps") is not None and len(steps) > spec["max_steps"]:
        v.append("soft: {} steps > max {}".format(len(steps), spec["max_steps"]))

    if spec.get("no_repeat"):
        v += _repeats(steps)

    if spec.get("ground", True):
        v += _ungrounded(steps, task_input)
    return v


def _repeats(steps):
    """Identical calls that repeat work already done successfully.

    A retry after a failure is correct behaviour, so only a call that already
    SUCCEEDED makes a later identical call a repeat.

    ponytail: unbounded retries of a failing tool are left to max_steps, which
    is what catches loops. Add a retry cap only if that proves too weak.
    """
    out, done = [], set()
    for s in steps:
        key = (s.tool, json.dumps(s.args, sort_keys=True, default=str))
        if key in done:
            out.append("soft: repeated call: {}".format(s.tool))
        if s.ok:
            done.add(key)
    return out


def _ungrounded(steps, task_input):
    """Identifier-shaped args that trace to nothing the agent was given.

    Each argument is traced back to the task input or any earlier tool result.
    Untraceable identifier-shaped values are flagged.

    ponytail: substring provenance. False-positives on enums the model legitimately
    knows ("high", "pending"), which is why this is warn-only. Tighten to
    id-shaped keys if it gets noisy.
    """
    corpus, out = str(task_input), []
    for s in steps:
        for key, val in s.args.items():
            val = str(val)
            if val.lower() in LITERALS or not ID_RE.match(val):
                continue
            if val not in corpus:
                out.append("warn: ungrounded arg {}.{}={!r}".format(s.tool, key, val))
        corpus += " " + s.result
    return out


def hard(violations):
    """The violations that fail a build on a single occurrence."""
    return [x for x in violations if not x.startswith(("soft:", "warn:"))]
