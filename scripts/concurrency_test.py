"""Exercise four synchronized races against a running graduation server."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from itertools import cycle
from threading import Barrier
from time import time_ns

import requests


TIMEOUT = (5, 30)
SCENARIOS = ("Check-in", "Enqueue", "Call next", "Complete")


def api(session, method, url, body=None, expected=200, params=None):
    response = session.request(method, url, json=body, params=params, timeout=TIMEOUT)
    payload = response.json()
    if response.status_code != expected or payload.get("ok") is not True:
        code = payload.get("error", {}).get("code", "unexpected response")
        raise RuntimeError(f"{method} {url} returned HTTP {response.status_code} ({code})")
    return payload["data"]


def run_race(devices, url, body, conflict, counts):
    barrier = Barrier(len(devices), timeout=30)

    def post(session):
        barrier.wait()
        try:
            response = session.post(url, json=body, timeout=TIMEOUT)
        except requests.RequestException as exc:
            return type(exc).__name__, None
        try:
            payload = response.json()
        except ValueError:
            return f"{response.status_code} NON_JSON", None
        if isinstance(payload, dict):
            if payload.get("ok") is True and isinstance(payload.get("data"), dict):
                return f"{response.status_code} OK", payload["data"]
            problem = payload.get("error")
            if payload.get("ok") is False and isinstance(problem, dict) and problem.get("code"):
                return f"{response.status_code} {problem['code']}", None
        return f"{response.status_code} INVALID_ENVELOPE", None

    with ThreadPoolExecutor(max_workers=len(devices)) as pool:
        responses = list(pool.map(post, devices))
    counts.update(label for label, _ in responses)
    expected = Counter({"200 OK": 1, f"409 {conflict}": len(devices) - 1})
    if counts != expected:
        raise RuntimeError(f"Expected one HTTP 200 and {len(devices) - 1} HTTP 409 {conflict}")
    return next(data for label, data in responses if label == "200 OK")


def create_participant(admin, base, code):
    return api(admin, "POST", base + "/api/participants", {
        "participant_code": code, "name": f"Concurrency {code}", "email": f"{code.lower()}@example.org",
    }, expected=201)


def verify(base, workers):
    counts = {scenario: Counter() for scenario in SCENARIOS}
    outcomes = dict.fromkeys(SCENARIOS, "SKIP")
    scenario = "Check-in"
    failure = None
    try:
        with ExitStack() as stack:
            devices = []
            accounts = cycle((("admin", "admin123"), ("staff1", "staff123"), ("staff2", "staff123")))
            for _ in range(workers):
                session = stack.enter_context(requests.Session())
                username, password = next(accounts)
                api(session, "POST", base + "/api/auth/login", {"username": username, "password": password})
                devices.append(session)
            admin = devices[0]
            code = f"CONC-{time_ns()}"
            person = create_participant(admin, base, code)
            print(f"{workers} devices at {base}, participant {code}", flush=True)
            target = {"code": code}
            checked = run_race(devices, base + "/api/checkin", target, "ALREADY_CHECKED_IN", counts[scenario])
            if checked["id"] != person["id"] or checked["status"] != "checked_in":
                raise RuntimeError("Check-in returned an unexpected participant or state")
            outcomes[scenario] = "PASS"

            scenario = "Enqueue"
            queued = run_race(devices, base + "/api/stage/queue", target, "ALREADY_QUEUED", counts[scenario])
            if queued["participant"]["id"] != person["id"] or queued["participant"]["status"] != "queued":
                raise RuntimeError("Enqueue returned an unexpected participant or state")
            outcomes[scenario] = "PASS"

            scenario = "Call next"
            for index in range(1, 6):
                extra = create_participant(admin, base, f"{code}-{index}")
                extra_code = {"code": extra["participant_code"]}
                api(admin, "POST", base + "/api/checkin", extra_code)
                api(admin, "POST", base + "/api/stage/queue", extra_code)
            state_url = base + "/api/stage/state"
            before = api(admin, "GET", state_url)
            if before["current"] is not None:
                api(admin, "POST", base + "/api/stage/complete", {"participant_id": before["current"]["id"]})
                before = api(admin, "GET", state_url)
            if before["current"] is not None or not before["queue"]:
                raise RuntimeError("Call-next requires an empty stage and a nonempty queue")
            expected_id = before["queue"][0]["id"]
            called = run_race(devices, base + "/api/stage/call-next", {}, "STAGE_BUSY", counts[scenario])
            after = api(admin, "GET", state_url)
            on_stage = api(admin, "GET", base + "/api/participants", params={"status": "on_stage", "per_page": 1})
            if (not after["current"] or after["current"]["id"] != expected_id
                    or called["current"]["id"] != expected_id or on_stage["total"] != 1
                    or [p["id"] for p in on_stage["items"]] != [expected_id]):
                raise RuntimeError("The stage and filtered roster must show exactly the first queued participant")
            outcomes[scenario] = "PASS"

            scenario = "Complete"
            completed = run_race(devices, base + "/api/stage/complete", {"participant_id": expected_id},
                                 "NOTHING_ON_STAGE", counts[scenario])
            if (completed["completed"]["id"] != expected_id or completed["completed"]["status"] != "completed"
                    or api(admin, "GET", state_url)["current"] is not None):
                raise RuntimeError("Completion must finish the called participant and leave the stage empty")
            outcomes[scenario] = "PASS"
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        outcomes[scenario] = "FAIL"
        failure = str(exc)

    print(f"\n{'Scenario':<12} {'Result':<8} Response counts")
    for title in SCENARIOS:
        summary = ", ".join(f"{label} = {n}" for label, n in sorted(counts[title].items()))
        print(f"{title:<12} {outcomes[title]:<8} {summary or '—'}")
    if failure is not None:
        print(f"FAIL ({scenario}): {failure}")
        return 1
    print("PASS (4/4 scenarios)")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:5001", help="server base URL")
    parser.add_argument("--workers", type=int, default=20, help="number of separate logged-in devices")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    return verify(args.base.rstrip("/"), args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
