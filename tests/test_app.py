from fastapi.testclient import TestClient

from sample_app.main import app

client = TestClient(app)


def test_checkout_works_when_healthy():
    client.post("/fix")
    assert client.get("/checkout").status_code == 200


def test_break_causes_errors_and_fix_recovers():
    client.post("/break")
    assert client.get("/checkout").status_code == 500
    client.post("/fix")
    assert client.get("/checkout").status_code == 200