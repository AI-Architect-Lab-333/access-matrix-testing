"""Try every cell of the Corner Library access matrix (MATRIX.md).

The expected answer of each cell is computed from the rules in RULES.md
(function `expected` below), never from what the application answers.
Each cell runs against a fresh copy of the application on a free local port,
so no cell depends on another one.

Usage: python check_access.py [path/to/app.py]
Exit code: 0 if every cell passes, 1 otherwise.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

CALLERS = ["visitor", "unknown", "alice", "lena", "adam"]
TOKENS = {
    "visitor": None,
    "unknown": "demo-nobody",  # not a seeded token
    "alice": "demo-alice",
    "lena": "demo-lena",
    "adam": "demo-adam",
}
ROLES = {"alice": "member", "lena": "librarian", "adam": "admin"}

# Row -> (method, path, JSON body). A4 also claims the loan for bob, to check
# that the borrower is always the caller (R6).
ROWS = {
    "A1": ("GET", "/books", None),
    "A2": ("GET", "/me/loans", None),
    "A3-own": ("GET", "/loans/1", None),
    "A3-other": ("GET", "/loans/2", None),
    "A3-none": ("GET", "/loans/99", None),
    "A4": ("POST", "/loans", {"book_id": 3, "member": "bob"}),
    "A5": ("POST", "/loans/1/return", None),
    "A6": ("POST", "/books", {"title": "Demo"}),
    "A7": ("DELETE", "/books/6", None),
}

LOAN_OWNERS = {"A3-own": "alice", "A3-other": "bob", "A3-none": None}
WRITE_RULES = {  # row -> (roles allowed, success status, rule)
    "A4": ({"member"}, 201, "R6"),
    "A5": ({"librarian", "admin"}, 200, "R7"),
    "A6": ({"librarian", "admin"}, 201, "R8"),
    "A7": ({"admin"}, 204, "R9"),
}


def expected(row, caller):
    """Status code required by RULES.md, and the rule that requires it."""
    if caller == "unknown":
        return 401, "R1"
    if row == "A1":
        return 200, "R2"
    if caller == "visitor":
        return 401, "R3"
    role = ROLES[caller]
    if row == "A2":
        return 200, "R4"
    if row in LOAN_OWNERS:
        owner = LOAN_OWNERS[row]
        if owner is None:
            return 404, "R5"
        if role == "member" and owner != caller:
            return 404, "R5"
        return 200, "R5"
    allowed, success, rule = WRITE_RULES[row]
    return (success if role in allowed else 403), rule


class App:
    """A fresh copy of the application on a free port."""

    def __init__(self, app_path):
        self.proc = subprocess.Popen(
            [sys.executable, app_path, "0"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        line = self.proc.stdout.readline().strip()
        if not line.startswith("listening on "):
            self.stop()
            raise RuntimeError(f"application did not start: {line!r}")
        self.base = line[len("listening on "):]

    def call(self, caller, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data,
                                         method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if TOKENS[caller] is not None:
            request.add_header("Authorization", f"Bearer {TOKENS[caller]}")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        return status, (json.loads(raw) if raw else None)

    def stop(self):
        self.proc.kill()
        self.proc.wait()


def witness(app, row, caller, status, payload, allowed):
    """Extra checks beyond the status code. Return a problem, or None."""
    if row == "A1" and allowed:
        if [b["id"] for b in payload] != [1, 2, 3, 4, 5, 6]:
            return f"catalogue is {payload}"
    if row == "A2" and allowed:
        want = [1] if caller == "alice" else []
        if [l["id"] for l in payload] != want:
            return f"loans listed: {payload}"
    if row in ("A3-own", "A3-other") and allowed:
        want_id = 1 if row == "A3-own" else 2
        if payload.get("id") != want_id:
            return f"wrong loan: {payload}"
    if row == "A3-other" and caller == "alice":
        # R5: someone else's loan must look exactly like a missing loan.
        none = app.call("alice", "GET", "/loans/99")
        if (status, payload) != none:
            return f"differs from a missing loan {none}: {payload}"
    if row in WRITE_RULES:
        return write_effect(app, row, allowed, payload)
    return None


def write_effect(app, row, allowed, payload):
    """Read back as adam: the effect happened if allowed, nothing changed if
    refused (R10)."""
    if row == "A4":
        status, loan = app.call("adam", "GET", "/loans/3")
        if allowed:
            if status != 200 or loan.get("member") != "alice":
                return f"loan 3 after borrow: {status} {loan}"
        elif status != 404:
            return f"refused borrow created loan 3: {loan}"
    if row == "A5":
        _, loan = app.call("adam", "GET", "/loans/1")
        if loan.get("returned") is not allowed:
            return f"loan 1 after return: {loan}"
    if row in ("A6", "A7"):
        _, books = app.call("adam", "GET", "/books")
        ids = [b["id"] for b in books]
        want = {("A6", True): [1, 2, 3, 4, 5, 6, 7],
                ("A6", False): [1, 2, 3, 4, 5, 6],
                ("A7", True): [1, 2, 3, 4, 5],
                ("A7", False): [1, 2, 3, 4, 5, 6]}[(row, allowed)]
        if ids != want:
            return f"catalogue after {row}: {ids}"
    return None


def run_cell(app_path, row, caller):
    want, rule = expected(row, caller)
    method, path, body = ROWS[row]
    app = App(app_path)
    try:
        status, payload = app.call(caller, method, path, body)
        problem = None
        if status != want:
            problem = f"got {status} {payload}"
        else:
            problem = witness(app, row, caller, status, payload,
                              allowed=200 <= want < 300)
    finally:
        app.stop()
    return want, rule, status, problem


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    app_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here,
                                                                  "app.py")
    failures = 0
    grid = {}
    for row in ROWS:
        for caller in CALLERS:
            want, rule, status, problem = run_cell(app_path, row, caller)
            ok = problem is None
            grid[row, caller] = "pass" if ok else "FAIL"
            if not ok:
                failures += 1
                print(f"FAIL  {row:9} {caller:8} want {want} [{rule}]: "
                      f"{problem}")
    print()
    print(f"{'':10}" + "".join(f"{c:>9}" for c in CALLERS))
    for row in ROWS:
        print(f"{row:10}" + "".join(f"{grid[row, c]:>9}" for c in CALLERS))
    total = len(ROWS) * len(CALLERS)
    print(f"\n{total - failures}/{total} cells pass, {failures} fail")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
