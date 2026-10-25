"""Corner Library: a tiny lending-library API for the access-matrix demo.

Synthetic data only, Python standard library only, in-memory state reset at
every start. Access rules are in RULES.md; the expected answers are in
MATRIX.md.

The first version (commit 70ece2d) carried ONE planted flaw, on purpose
(RULES.md, R5): GET /loans/{id} checked that the caller was logged in, not
that the caller owned the loan. This version fixes it.

Usage: python app.py [port]    (port 0 picks a free port; default 8000)
"""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"

# Demo tokens: obvious placeholders, not secrets.
USERS = {
    "demo-alice": {"name": "alice", "role": "member"},
    "demo-bob": {"name": "bob", "role": "member"},
    "demo-lena": {"name": "lena", "role": "librarian"},
    "demo-adam": {"name": "adam", "role": "admin"},
}

TITLES = [
    "The River Atlas",
    "Notes on Clockwork",
    "A Field Guide to Moss",
    "Bread for Beginners",
    "The Quiet Lighthouse",
    "Knots and Hitches",
]


class Refused(Exception):
    def __init__(self, status, error):
        super().__init__(error)
        self.status = status
        self.error = error


class Library:
    def __init__(self):
        self.books = {i: {"id": i, "title": t} for i, t in enumerate(TITLES, 1)}
        self.loans = {
            1: {"id": 1, "book_id": 1, "member": "alice", "returned": False},
            2: {"id": 2, "book_id": 2, "member": "bob", "returned": False},
        }
        self.next_book_id = len(self.books) + 1
        self.next_loan_id = len(self.loans) + 1

    # A1 - public catalogue (R2)
    def list_books(self, user, body):
        return 200, sorted(self.books.values(), key=lambda b: b["id"])

    # A2 - the caller's own loans (R3, R4)
    def my_loans(self, user, body):
        require_login(user)
        mine = [l for l in self.loans.values() if l["member"] == user["name"]]
        return 200, sorted(mine, key=lambda l: l["id"])

    # A3 - one loan (R3, R5)
    def view_loan(self, user, body, loan_id):
        require_login(user)
        loan = self.loans.get(loan_id)
        if loan is None:
            raise Refused(404, "not_found")
        # R5: a member sees only their own loans; someone else's loan gets
        # the same answer as a missing one.
        if user["role"] == "member" and loan["member"] != user["name"]:
            raise Refused(404, "not_found")
        return 200, loan

    # A4 - borrow a book, members only (R6)
    def borrow(self, user, body):
        require_role(user, "member")
        book_id = valid_body(body).get("book_id")
        if book_id not in self.books:
            raise Refused(404, "not_found")
        # The borrower is always the caller, whatever the body says.
        loan = {"id": self.next_loan_id, "book_id": book_id,
                "member": user["name"], "returned": False}
        self.loans[loan["id"]] = loan
        self.next_loan_id += 1
        return 201, loan

    # A5 - record a return, at the desk only (R7)
    def record_return(self, user, body, loan_id):
        require_role(user, "librarian", "admin")
        loan = self.loans.get(loan_id)
        if loan is None:
            raise Refused(404, "not_found")
        loan["returned"] = True
        return 200, loan

    # A6 - add a book (R8)
    def add_book(self, user, body):
        require_role(user, "librarian", "admin")
        title = valid_body(body).get("title")
        if not isinstance(title, str) or not title.strip():
            raise Refused(400, "bad_request")
        book = {"id": self.next_book_id, "title": title.strip()}
        self.books[book["id"]] = book
        self.next_book_id += 1
        return 201, book

    # A7 - remove a book, admins only (R9)
    def remove_book(self, user, body, book_id):
        require_role(user, "admin")
        if book_id not in self.books:
            raise Refused(404, "not_found")
        del self.books[book_id]
        return 204, None


def authenticate(headers):
    """Return the account, or None for a visitor. Unknown token: 401 (R1)."""
    header = headers.get("Authorization")
    if header is None:
        return None
    token = header[len("Bearer "):] if header.startswith("Bearer ") else None
    if token not in USERS:
        raise Refused(401, "invalid_token")
    return USERS[token]


def valid_body(body):
    """The body is parsed before the checks but judged only after them."""
    if body is None:
        raise Refused(400, "bad_request")
    return body


def require_login(user):
    if user is None:
        raise Refused(401, "login_required")


def require_role(user, *roles):
    require_login(user)
    if user["role"] not in roles:
        raise Refused(403, "forbidden")


ROUTES = [
    ("GET", re.compile(r"/books"), "list_books"),
    ("POST", re.compile(r"/books"), "add_book"),
    ("DELETE", re.compile(r"/books/(\d+)"), "remove_book"),
    ("GET", re.compile(r"/me/loans"), "my_loans"),
    ("POST", re.compile(r"/loans"), "borrow"),
    ("GET", re.compile(r"/loans/(\d+)"), "view_loan"),
    ("POST", re.compile(r"/loans/(\d+)/return"), "record_return"),
]


class Handler(BaseHTTPRequestHandler):
    library = None  # set in main()

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        try:
            # Authentication comes first: a refused caller learns nothing
            # about whether the target exists.
            user = authenticate(self.headers)
            for route_method, pattern, name in ROUTES:
                match = pattern.fullmatch(self.path)
                if route_method == method and match:
                    args = [int(g) for g in match.groups()]
                    status, payload = getattr(self.library, name)(
                        user, self.read_body(), *args)
                    break
            else:
                raise Refused(404, "not_found")
        except Refused as refusal:
            status, payload = refusal.status, {"error": refusal.error}
        self.reply(status, payload)

    def read_body(self):
        """Return the JSON body as a dict, {} if empty, None if malformed."""
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    def reply(self, status, payload):
        self.send_response(status)
        if payload is None:
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = json.dumps(payload).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # keep the matrix output readable


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    Handler.library = Library()
    server = ThreadingHTTPServer((HOST, port), Handler)
    # The check script reads this line to learn the real port.
    print(f"listening on http://{HOST}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
