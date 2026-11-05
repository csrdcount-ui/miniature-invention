import os
import re
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def csrf_of(html: str) -> str:
    m = re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, "brak tokenu CSRF na stronie"
    return m.group(1)


def post(client, page_url, action_url, data):
    token = csrf_of(client.get(page_url).text)
    return client.post(action_url, data={**data, "csrf": token}, follow_redirects=False)


def login(client, email, password="haslo-testowe-123"):
    client.cookies.clear()
    r = post(client, "/logowanie", "/logowanie", {"email": email, "haslo": password})
    assert r.status_code == 303, r.text
    return r
