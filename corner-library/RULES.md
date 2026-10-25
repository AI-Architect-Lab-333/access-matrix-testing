# Corner Library — access rules

Written before any code and before any test run. The expected answer of every
matrix cell is computed from these rules, never from what the application
returns.

## Seed data (synthetic, reset at every start)

| Account | Role | Demo token |
|---|---|---|
| alice | member | `demo-alice` |
| bob | member | `demo-bob` |
| lena | librarian | `demo-lena` |
| adam | admin | `demo-adam` |

- Books 1 to 6.
- Loan 1: alice, book 1, active. Loan 2: bob, book 2, active.
- A caller without an `Authorization` header is a **visitor** (not a role).

## Actions

| # | Action | Request |
|---|---|---|
| A1 | browse the catalogue | `GET /books` |
| A2 | list my own loans | `GET /me/loans` |
| A3 | view one loan | `GET /loans/{id}` |
| A4 | borrow a book | `POST /loans` with `{"book_id": n}` |
| A5 | record a return | `POST /loans/{id}/return` |
| A6 | add a book | `POST /books` with `{"title": "..."}` |
| A7 | remove a book | `DELETE /books/{id}` |

## Rules

- **R1** — An unknown token is refused on every action: `401`. It is never
  served as a visitor.
- **R2** — The catalogue (A1) is public: everyone, visitors included, gets `200`.
- **R3** — Every other action (A2 to A7) needs a known account: a visitor gets
  `401`.
- **R4** — A2 lists the caller's own loans only: `200`, and every loan in the
  answer belongs to the caller.
- **R5** — A3: the loan's owner, any librarian and any admin get `200`. A member
  who does not own the loan gets `404`, the same answer as for a loan that does
  not exist, so the request tells nothing about other members' loans.
- **R6** — A4 is for members only: `201`, and the new loan belongs to the
  caller. A librarian or an admin gets `403`.
- **R7** — A5 is for librarians and admins: `200`. A member gets `403`, even for
  their own loan (returns are recorded at the desk).
- **R8** — A6 is for librarians and admins: `201`. A member gets `403`.
- **R9** — A7 is for admins only: `204`. A member or a librarian gets `403`.
- **R10** — A refused write changes nothing: after a refused A4, A5, A6 or A7,
  the data it targeted is exactly as before.

## Order of checks

Authentication first (R1, R3), then the role (R6 to R9), then ownership (R5).
A refused caller learns nothing about whether the target exists.

## The planted flaw (demonstration only)

The first version of the application breaks **R5** on purpose: A3 checks that
the caller is logged in, not that the caller owns the loan. Alice reads Bob's
loan by changing `/loans/1` to `/loans/2`.
