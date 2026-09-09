"""Run a suite of cases k times, score each run, report Luck Rate, gate a build."""
import json
import time
import urllib.error
import urllib.request

from luckrate.check import check, hard


def evaluate(cases, runner, k=5):
    """runner(input) -> (steps, output). k runs per case; agents are stochastic."""
    rows = []
    for case in cases:
        for i in range(k):
            try:
                steps, output = runner(case["input"])
            except Exception as exc:
                # A suite is real money: one network blip must not discard every
                # completed run. Record the failure and keep going. It counts as
                # a hard violation because a suite that did not finish cannot
                # certify anything.
                rows.append({
                    "case": case["name"], "run": i, "output_ok": False,
                    "violations": ["run failed: {}".format(exc)],
                    "hard": ["run failed: {}".format(exc)], "steps": 0,
                })
                continue
            violations = check(steps, case.get("spec", {}), case["input"])
            rows.append({
                "case": case["name"],
                "run": i,
                "output_ok": bool(case["expect"](output)),
                "violations": violations,
                "hard": hard(violations),
                "steps": len(steps),
            })
    return rows


def report(rows):
    """Print every run and return the Luck Rate, or None if nothing passed."""
    for r in rows:
        # path_ok for Luck Rate means NO violations at all, warnings included.
        # A fabricated id is warn-only so it never fails a build, but it is
        # exactly the bad path this metric exists to surface.
        state = "pass" if r["output_ok"] and not r["violations"] else (
            "LUCKY" if r["output_ok"] else "fail")
        print("{:5}  {:<22} run={} steps={}".format(state, r["case"], r["run"], r["steps"]))
        for x in r["violations"]:
            print("       - " + x)

    green = [r for r in rows if r["output_ok"]]
    lucky = [r for r in green if r["violations"]]
    luck = len(lucky) / len(green) if green else None

    print("\noutput passed {}/{}".format(len(green), len(rows)))
    print("luck rate {}  ({} of {} green runs were lucky)".format(
        "-" if luck is None else "{:.0%}".format(luck), len(lucky), len(green)))
    return luck


def failed(rows):
    """Gate: hard violations fail on one occurrence, soft only on a majority."""
    if any(r["hard"] for r in rows):
        return True
    by_case = {}
    for r in rows:
        soft = any(x.startswith("soft:") for x in r["violations"])
        by_case.setdefault(r["case"], []).append(soft)
    return any(sum(flags) * 2 > len(flags) for flags in by_case.values())


def n8n_runner(webhook_url, api_key, base="http://localhost:5678"):
    """Trigger an n8n agent over its production webhook and read back its run.

    The workflow must respond via a Respond to Webhook node returning
    {"output": ..., "executionId": $execution.id} -- there is no other way to
    learn which execution a trigger caused.
    """
    from luckrate.adapters.n8n import from_n8n

    def run(task):
        answer = _post(webhook_url, {"message": task})
        return from_n8n(_execution(base, api_key, answer["executionId"])), answer["output"]

    return run


def _post(url, body, timeout=240):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _execution(base, api_key, execution_id, tries=20):
    """responseMode=responseNode replies only after the run completes, so this
    is not a wait-for-finish poll -- it just covers the save-after-respond race.
    """
    url = "{}/api/v1/executions/{}?includeData=true".format(base, execution_id)
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": api_key})
    for _ in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                ex = json.load(r)
            if ex.get("finished"):
                return ex
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        time.sleep(0.5)
    raise RuntimeError("execution {} never became readable".format(execution_id))
