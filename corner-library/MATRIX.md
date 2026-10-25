# Corner Library — access matrix

Every expected answer below is computed from `RULES.md` (rule in brackets),
never from what the application returns. Written before any code.

## Callers

| Caller | Header |
|---|---|
| visitor | no `Authorization` header |
| unknown | `Authorization: Bearer demo-nobody` (not a seeded token) |
| alice | member, `Bearer demo-alice` |
| lena | librarian, `Bearer demo-lena` |
| adam | admin, `Bearer demo-adam` |

Bob is not a caller: he owns loan 2, the target of the planted flaw.

## Cells

Each cell runs against a fresh copy of the application (seed data from
`RULES.md`), so no cell depends on another one.

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

9 rows × 5 callers = **45 cells**.

## What a green cell also checks

A status code alone does not tell a working refusal from a broken page, so:

- **Allowed reads** — the body is right, not just the code:
  - A1: the catalogue lists books 1 to 6;
  - A2: alice gets exactly loan 1; lena and adam get an empty list [R4];
  - A3-own / A3-other: the answer is the loan that was asked for.
- **Allowed writes** — the effect happened:
  - A4: the new loan belongs to alice, whatever the body says [R6];
  - A5: loan 1 is now returned;
  - A6: the new book appears in the catalogue;
  - A7: book 6 is gone from the catalogue.
- **Refused writes** — nothing changed [R10], read back as adam after the
  refusal:
  - A4: no loan 3 exists;
  - A5: loan 1 is still active;
  - A6: the catalogue still has 6 books;
  - A7: book 6 is still there.
- **A3-other vs A3-none** — for alice the two answers are identical (code and
  body), so a member cannot tell "someone else's loan" from "no loan" [R5].

## Expected runs

| Run | Expected |
|---|---|
| planted flaw (first version) | 1 red: A3-other / alice (gets 200 and bob's loan instead of 404); 44 green |
| flaw fixed | 45 green |
| guard seen failing (admin-only check of A7 removed on purpose) | 2 red: A7 / alice and A7 / lena (204 instead of 403, book 6 gone); 43 green |
| guard restored | 45 green |
