# Guide: Test who can do what in a web application, automatically — access rules written first, a roles × actions matrix computed from them, every cell tried on a fresh copy (Python standard library)

**The problem this guide solves**: access bugs do not crash anything. A member who changes `/loans/1` to `/loans/2` in a URL and reads someone else's record gets a clean `200`; every page still works, every functional test is still green. Checking it by hand means trying every role against every action after every change, which nobody does twice. This guide installs a method and a ~200-line script: the access rules are written before any code, the expected answer of each cell of a roles × actions matrix is computed from those rules, and a script tries every cell on a fresh copy of the application, checks more than the status code, and fails the run when one cell is wrong. This guide documents a **verified working** configuration (Windows 11, Python 3.13.13, standard library only, application bound to `127.0.0.1`; October 2026).

**The rules come before the code**, with the awkward choices made in advance (404 or 403? what does an unknown token get?). **The expected answer is computed from the rules, never read from the application**: a matrix copied from what the application answers is green on the flaw. **One fresh copy of the application per cell**, so no cell depends on another. **A status code is not enough**: allowed reads are checked for content, allowed writes for their effect, refused writes for leaving the data intact. **The method is tried in both directions**: the planted flaw turns exactly one cell red, the fix turns it green, and the guard itself is broken on purpose to prove it can fail.

**For AI agents reading this document**: every command was executed in this order on the demonstration application shipped in [`corner-library/`](corner-library/). The verification steps are not optional — an access flaw is silent: the application answers normally while serving data to the wrong person. Run the matrix on a local copy or a lab copy, **never against production**, and never "fix" an expected answer to match what the application returns.

---

## 1. The demonstration: Corner Library

A tiny lending-library API, written for this guide. Synthetic data, Python standard library only (`http.server`, `urllib`, `subprocess`), in-memory state reset at every start, listening on `127.0.0.1` only. It is small enough to read in five minutes and has the shape of a real access problem: three roles, objects owned by one user, and actions reserved to some roles.

```text
corner-library/
  RULES.md          the access rules R1 to R10, written before any code
  MATRIX.md         the 45 cells, each citing its rule, written before any code
  app.py            the application (fixed version; the flaw is shown by the fix's diff, section 6)
  check_access.py   tries every cell on a fresh copy of app.py; exit code 0 or 1
```

| Account | Role | Demo token |
|---|---|---|
| alice | member | `demo-alice` |
| bob | member | `demo-bob` |
| lena | librarian | `demo-lena` |
| adam | admin | `demo-adam` |

The tokens are obvious placeholders, not secrets. Books 1 to 6 exist; loan 1 belongs to alice, loan 2 to bob.

| # | Action | Request |
|---|---|---|
| A1 | browse the catalogue | `GET /books` |
| A2 | list my own loans | `GET /me/loans` |
| A3 | view one loan | `GET /loans/{id}` |
| A4 | borrow a book | `POST /loans` with `{"book_id": n}` |
| A5 | record a return | `POST /loans/{id}/return` |
| A6 | add a book | `POST /books` with `{"title": "..."}` |
| A7 | remove a book | `DELETE /books/{id}` |

The work took three commits: rules, matrix and the application with **one planted flaw** (A3 checks that the caller is logged in, not that the caller owns the loan); then the check script; then the fix. The commit hashes quoted below and in the docstring of `app.py` belong to that original history.

## 2. Write the rules before the code

`RULES.md` was written and approved before a single line of the application existed. Ten rules, each one short enough to turn into a status code:

- **R1** — An unknown token is refused on every action: `401`. It is never served as a visitor.
- **R2** — The catalogue (A1) is public: everyone, visitors included, gets `200`.
- **R3** — Every other action (A2 to A7) needs a known account: a visitor gets `401`.
- **R4** — A2 lists the caller's own loans only.
- **R5** — A3: the loan's owner, any librarian and any admin get `200`. A member who does not own the loan gets `404`, the same answer as for a loan that does not exist.
- **R6** — A4 is for members only: `201`, and the new loan belongs to the caller. A librarian or an admin gets `403`.
- **R7** — A5 is for librarians and admins: `200`. A member gets `403`, even for their own loan.
- **R8** — A6 is for librarians and admins: `201`. A member gets `403`.
- **R9** — A7 is for admins only: `204`. A member or a librarian gets `403`.
- **R10** — A refused write changes nothing: after a refused A4, A5, A6 or A7, the data it targeted is exactly as before.

And the **order of checks**: authentication first (R1, R3), then the role (R6 to R9), then ownership (R5). A refused caller learns nothing about whether the target exists.

The value of writing them first is in the choices you are forced to make before the code makes them for you:

- **Someone else's loan answers `404`, like a loan that does not exist (R5)** — not `403`. A `403` would confirm that loan 2 exists; `404` tells a member nothing about other members.
- **An unknown token is refused `401`, never served as a visitor (R1).** An application that quietly downgrades a bad token to anonymous hides a misconfigured client and makes the token check impossible to test.
- **Librarians and admins do not borrow (R6).** "Higher roles can do everything" is not a rule; it is the absence of one.
- **A return is recorded at the desk, even for your own loan (R7).** Ownership does not grant every action on the object you own.

Each of these is one line in `RULES.md` and one or more cells in the matrix. Without the line, whatever the code happens to do becomes the rule.

## 3. Compute the expected answer from the rules

The matrix has 5 callers — a **visitor** (no `Authorization` header), an **unknown** token (`Bearer demo-nobody`), and one account per role (alice, lena, adam) — and 9 rows. A3 is split into three rows because ownership is what it tests: `A3-own` (`/loans/1`, alice's), `A3-other` (`/loans/2`, bob's), `A3-none` (`/loans/99`, no such loan). Bob is not a caller: he owns the target of the planted flaw.

| Row | Request | visitor | unknown | alice | lena | adam |
|---|---|---|---|---|---|---|
| A1 | `GET /books` | 200 [R2] | 401 [R1] | 200 [R2] | 200 [R2] | 200 [R2] |
| A2 | `GET /me/loans` | 401 [R3] | 401 [R1] | 200 [R4] | 200 [R4] | 200 [R4] |
| A3-own | `GET /loans/1` (alice's) | 401 [R3] | 401 [R1] | 200 [R5] | 200 [R5] | 200 [R5] |
| A3-other | `GET /loans/2` (bob's) | 401 [R3] | 401 [R1] | **404 [R5]** | 200 [R5] | 200 [R5] |
| A3-none | `GET /loans/99` (no such loan) | 401 [R3] | 401 [R1] | 404 [R5] | 404 [R5] | 404 [R5] |
| A4 | `POST /loans` `{"book_id": 3}` | 401 [R3] | 401 [R1] | 201 [R6] | 403 [R6] | 403 [R6] |
| A5 | `POST /loans/1/return` | 401 [R3] | 401 [R1] | 403 [R7] | 200 [R7] | 200 [R7] |
| A6 | `POST /books` `{"title": "Demo"}` | 401 [R3] | 401 [R1] | 403 [R8] | 201 [R8] | 201 [R8] |
| A7 | `DELETE /books/6` | 401 [R3] | 401 [R1] | 403 [R9] | 403 [R9] | 204 [R9] |

9 rows × 5 callers = 45 cells. Every cell cites the rule that decides it.

In `check_access.py`, the same answers come from a function written from `RULES.md`, not from the application:

```python
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
```

Its order is the order of checks in `RULES.md`: unknown token, then public catalogue, then visitor, then role and ownership. `MATRIX.md` was written by hand and `expected()` was written separately, so before the first run the 45 hand-written cells were compared with `expected()`:

```text
45 cells in MATRIX.md; 0 differences with expected()
```

Two independent writings of the same rules that agree are a much better oracle than either one alone.

### Pitfall #1 — a matrix filled in from the application's answers is green on the flaw

The tempting shortcut is to run every request once, record what the application answers, and call that the matrix. On the first version of Corner Library, that recording would have said `A3-other / alice → 200`, and the matrix would have certified the flaw as correct behaviour forever. The expected answer must come from somewhere the code cannot influence: the rules. When a cell fails, the question is "does the code break the rule, or is the rule wrong?" — and if the rule is wrong, you change `RULES.md` first, then the matrix, never the expected value alone.

### Write the expected result of each run before running it

`MATRIX.md` also fixes, before any run, what each of the four runs of this guide must produce:

| Run | Expected |
|---|---|
| planted flaw (first version) | 1 red: A3-other / alice (gets 200 and bob's loan instead of 404); 44 green |
| flaw fixed | 45 green |
| guard seen failing (admin-only check of A7 removed on purpose) | 2 red: A7 / alice and A7 / lena (204 instead of 403, book 6 gone); 43 green |
| guard restored | 45 green |

A run is a success only if it matches this table — not if it is "mostly green", and not if it turns red somewhere else.

## 4. One fresh copy of the application per cell

`app.py` takes a port on the command line; port `0` asks the system for a free one, and the application prints the address it really got:

```python
print(f"listening on http://{HOST}:{server.server_port}", flush=True)
```

`check_access.py` starts `python app.py 0` for **every** cell, reads that line to learn the port, sends one request, runs the checks of section 5, and kills the process:

```python
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
```

No cell depends on another: adam's `DELETE /books/6` cannot make lena's `DELETE /books/6` answer `404` instead of `403`, and alice's borrow cannot shift the next loan number. The order of the cells does not matter, and a failing cell can be rerun alone. The cost is small: the 45 cells, 45 processes, took **2.4 s** on the first run.

A startup check came first, by hand, and it is **not** a test of the matrix — it only proves the application starts and answers:

```bash
python app.py 8765
```

In a second terminal:

```bash
curl http://127.0.0.1:8765/books
```

The first command printed `listening on http://127.0.0.1:8765`; the second returned `200` and the six books. The process was then stopped.

## 5. The status code is not enough: witnesses

A `403` from a guard and a `403` from a crashed handler look the same. A `200` with the wrong body looks like a success. So a green cell also checks a **witness**, defined in `MATRIX.md` before any run:

- **Allowed reads — the content.** A1 lists books 1 to 6; A2 gives alice exactly loan 1, and lena and adam an empty list (R4); A3-own and A3-other return the loan that was asked for.
- **Allowed writes — the effect, read back as adam.** A4: loan 3 exists and belongs to alice; A5: loan 1 is returned; A6: book 7 is in the catalogue; A7: book 6 is gone.
- **Refused writes — nothing changed (R10), read back as adam.** A4: no loan 3; A5: loan 1 still active; A6: still 6 books; A7: book 6 still there. A refusal that still wrote is the worst kind of bug: the caller sees "forbidden", the data says otherwise.
- **For alice, A3-other is identical to A3-none** — same code *and* same body — so a member cannot tell "someone else's loan" from "no loan" (R5).

Two requests are deliberately hostile. A4 sends `{"book_id": 3, "member": "bob"}`: the borrower must still be the caller (R6), and the witness checks that loan 3 belongs to alice, not to bob. And the read-back always uses adam, the one caller allowed to see everything, so the witness does not depend on the rights it is testing.

```python
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
```

## 6. Run 1 — the flaw is present

The application at its first commit, with the check script added:

```bash
python check_access.py
```

```text
FAIL  A3-other  alice    want 404 [R5]: got 200 {'id': 2, 'book_id': 2, 'member': 'bob', 'returned': False}
```

followed by the grid and:

```text
44/45 cells pass, 1 fail
```

Exit code `1`, 2.4 s. One red cell, the one predicted in section 3, and none elsewhere.

### Pitfall #2 — `got 200 {'id': 2, ... 'member': 'bob' ...}`: one number changed in a URL

Alice is logged in, she reads her loan at `/loans/1`, she types `/loans/2` and reads bob's. The first version of `view_loan` checked that the caller was logged in and that the loan existed, and nothing else:

```python
        # PLANTED FLAW (R5): no ownership check, any member reads any loan.
        return 200, loan
```

Every functional test of this application passes with that code: alice can see her loan, lena and adam can see every loan, a missing loan gives `404`. The only cell that catches it is the one that asks a member for an object she does not own — which is why A3 was split into three rows, and why the target of the flaw (bob) is an owner, not a caller.

## 7. Run 2 — the flaw is fixed

The fix is one condition in `view_loan`, at the place of the planted comment (commit `d5ed838`):

```diff
         loan = self.loans.get(loan_id)
         if loan is None:
             raise Refused(404, "not_found")
-        # PLANTED FLAW (R5): no ownership check, any member reads any loan.
+        # R5: a member sees only their own loans; someone else's loan gets
+        # the same answer as a missing one.
+        if user["role"] == "member" and loan["member"] != user["name"]:
+            raise Refused(404, "not_found")
         return 200, loan
```

```bash
python check_access.py
```

```text
45/45 cells pass, 0 fail
```

Exit code `0`. A3-other / alice now gets `404`, and the witness confirms the answer is identical to the one for a loan that does not exist. To watch run 1 yourself on the shipped `app.py`, remove the two lines of the `if` and run the script again: that is the first version's behaviour.

## 8. Run 3 — the guard seen failing

45 green cells prove the application follows the rules **only if the script can turn red**. Run 1 showed it on the planted flaw; run 3 shows it on a guard nobody planted, by breaking it on purpose (and not committing it). In `remove_book`, the admin-only check becomes a login-only check:

```diff
     def remove_book(self, user, body, book_id):
-        require_role(user, "admin")
+        require_login(user)  # GUARD BROKEN ON PURPOSE: role check removed
```

One line in `git diff`. The prediction from section 3: A7 / alice and A7 / lena turn red, nothing else.

```bash
python check_access.py
```

```text
FAIL  A7        alice    want 403 [R9]: got 204 None
FAIL  A7        lena     want 403 [R9]: got 204 None
```

```text
43/45 cells pass, 2 fail
```

Exit code `1`. Exactly the two predicted cells.

### Pitfall #3 — a guard you have never seen fail proves nothing

A script that prints `45/45` could be checking nothing: a typo in a URL that hits a catch-all route, an `expected()` that mirrors the code, a comparison that is always true. Until you have seen it turn red on a known breakage, and red **only** where you predicted, the green is unproven. The test has two outcomes, both written in advance: the predicted cells fail (the guard works), or other cells fail or none do (the guard, the prediction or the rules are wrong — find out which before trusting any green run).

### Pitfall #4 — the witnesses do not run when the status code is already wrong

In run 3, the script reported `got 204 None` and stopped there for those two cells. It did not say "and book 6 is gone", although it was: `run_cell` only calls the witness when the status code matches.

```python
        if status != want:
            problem = f"got {status} {payload}"
        else:
            problem = witness(app, row, caller, status, payload,
                              allowed=200 <= want < 300)
```

The cell is red either way, so no flaw is missed. But the report under-states the damage: a wrong `204` on a delete is not just a wrong code, it is a deleted book. When a write cell fails on its status, check the data yourself, or extend `run_cell` to run `write_effect` in both branches.

## 9. Run 4 — the guard restored

```bash
git checkout -- app.py
```

```bash
git status --short
```

Empty output: the working tree is the committed, fixed version again.

```bash
python check_access.py
```

```text
45/45 cells pass, 0 fail
```

Exit code `0`. Four runs, four results identical to the table written before the first one.

## 10. Undecided points

Corner Library has none: R1 to R10 decide all 45 cells. A real application usually has some — an action nobody has thought about for a given role, or a choice between `403` and `404` that nobody has made yet.

The method for those:

- **The cell still runs.** It is not left out of the matrix because nobody knows the answer.
- **It is reported as `OPEN`, with what was observed** (status and body), not as pass or fail.
- **An `OPEN` cell does not fail the guard.** The exit code stays reserved for broken rules; otherwise the guard is red forever and people learn to ignore it.
- **A decision becomes a rule.** The owner decides, the decision is written into the rules file as a new `Rn`, and its cells join the matrix with an expected answer.

`check_access.py` has no `OPEN` path, because the demonstration needed none; adding one is a third outcome next to pass and `FAIL` in `run_cell`, kept out of the failure count.

## 11. Line endings for the annex

### Pitfall #5 — `LF will be replaced by CRLF` on `git add`

Committing the demonstration on Windows printed `LF will be replaced by CRLF` warnings on `git add` — the machine has `core.autocrlf` set to `true`. Python does not care about line endings, so nothing broke. But a repository meant to be cloned on Linux should not depend on each reader's Git settings: this one ships a `.gitattributes` that stores and checks out every text file with `eol=lf`.

```text
* text=auto eol=lf
*.md text eol=lf
*.py text eol=lf
.gitignore text eol=lf
```

## 12. End-to-end verification

From the `corner-library/` folder:

```bash
python check_access.py
```

- ✅ `45/45 cells pass, 0 fail`, exit code `0`: every cell of the matrix answers what `RULES.md` requires, with its witness.
- ❌ any `FAIL` line, exit code `1`: the line names the row, the caller, the expected code, the rule and what came back. Decide whether the code breaks the rule (fix the code) or the rule is wrong (change `RULES.md`, then the matrix) — never edit `expected()` to match the application.

The verification is complete only with the four runs of sections 6 to 9: one red cell on the flaw, green after the fix, exactly two red cells with the guard broken, green after restoring it.

## Symptom / Cause / Fix

| Symptom | Cause | Fix |
|---|---|---|
| The matrix is green while a member reads others' records | expected answers recorded from the application | compute them from the rules (`expected()`), cross-check with the hand-written matrix |
| `got 200 {... 'member': 'bob' ...}` on A3-other / alice | `view_loan` checks login, not ownership | owner, librarian or admin only; others get the same `404` as a missing loan |
| A green run you cannot trust | the guard has never been seen failing | break one check on purpose, predict the red cells, run, restore |
| `got 204 None` but no word about the deleted book | witnesses run only when the status matches | check the data by hand, or run `write_effect` in both branches |
| `LF will be replaced by CRLF` on `git add` | `core.autocrlf=true` on the Windows machine | `.gitattributes` with `eol=lf` |

## Known limitations

- **Status first, effect second** (pitfall #4): when the status code is wrong, the report does not describe the damage.
- **One caller per role.** A second member (bob as caller) or a second librarian would add cells; with ownership in play, a real matrix should have at least two users per role that owns objects.
- **The cross-check between `MATRIX.md` and `expected()` is not shipped.** Only its result is shown (section 3); it reads the 45 cells from the table and compares them with the function.
- **The tokens are fixed placeholders.** Expired tokens, revoked accounts, and changes of role during a session are not covered.
- **One fresh process per cell suits a small application.** An application with a database needs a fresh copy of the data per cell (a template database, a snapshot, a transaction rolled back), which costs more than 2.4 s for 45 cells.
- **The matrix only tests the actions it lists.** An endpoint missing from the rules is missing from the test; keep the list of routes and the list of actions side by side.
- **No `OPEN` path in the shipped script** (section 10).

## Self-check

Six questions. Each one is answered by a pitfall above. Write the answer down before you open [self-check-answers.md](self-check-answers.md).

1. **Pitfall #1.** To save time, a colleague proposes running every request once against the current application and saving the answers as the expected matrix. What would that matrix have said about the first version of Corner Library, and where must the expected answers come from instead?
2. **Pitfall #1.** A cell fails: the rules say `403`, the application says `200`, and the product owner says `200` is fine. What do you change, and in which order?
3. **Pitfall #2.** All functional tests of the first version pass: alice sees her loan, lena sees every loan, a missing loan gives `404`. Which matrix row catches the flaw, and why must the target loan belong to someone who is not a caller?
4. **Pitfall #2.** Why does R5 answer `404` to a member asking for someone else's loan, rather than `403`, and what does the script compare to check it?
5. **Pitfall #3.** You add the script to a new application and the first run prints `45/45 cells pass`. What do you do before trusting it, and what result would make you distrust it?
6. **Pitfall #4.** A run reports `FAIL  A7  lena  want 403 [R9]: got 204 None` and nothing else. What else has probably happened, and why does the report not say so?

## Credits

The class of flaw demonstrated here is known as Broken Object Level Authorization, first in the [OWASP API Security Top 10](https://owasp.org/API-Security/) (CC BY-SA 4.0). Built on the [Python standard library](https://docs.python.org/3/library/) (PSF License). No text from either is copied here; the application, the script and the rules were written for this guide.

---

*Guide written and verified in October 2026 on Windows 11, with the application bound to 127.0.0.1. Versions: Python 3.13.13 (standard library only), Git for Windows.*
