import runpy
import logging
import json
import time
from fastapi.testclient import TestClient


def load_app(path: str):
    # Ensure the service's src dir is on sys.path so service-local imports win
    import sys
    from pathlib import Path

    svc_src = str(Path(path).resolve().parent)
    # repo root is two levels up from service src (service/src -> service -> repo)
    repo_root = str(Path(path).resolve().parents[2])
    # Insert service src first so its local `middleware` package is resolved before others
    if svc_src in sys.path:
        sys.path.remove(svc_src)
    sys.path.insert(0, svc_src)
    if repo_root in sys.path:
        sys.path.remove(repo_root)
    sys.path.insert(1, repo_root)
    ns = runpy.run_path(path)
    return ns.get("app")


def test_user_service_health_and_create(caplog):
    app = load_app("user-service/src/main.py")
    client = TestClient(app)
    caplog.set_level(logging.INFO)

    # Health
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("service") == "user-service"

    # Create user with tenant header (unique tenant per test run)
    import uuid
    tenant = f"t{uuid.uuid4().hex[:8]}"
    payload = {"email": "test@example.com", "full_name": "Tester", "is_active": True}
    r = client.post("/users", json=payload, headers={"X-Tenant-ID": tenant})
    assert r.status_code == 201

    # Middleware should emit a JSON log containing tenant
    found = False
    for rec in caplog.records:
        # First try: message may contain full JSON string (older tests)
        msg = rec.getMessage()
        obj = None
        try:
            obj = json.loads(msg)
        except Exception:
            # Fallback: structured fields may be attached via `extra` on the record
            obj = {"service": rec.__dict__.get("service"), "tenant": rec.__dict__.get("tenant")}

        if obj and obj.get("service") == "user-service" and obj.get("tenant") == tenant:
            found = True
            break
    assert found, "Did not find structured JSON log for user-service with tenant"


def test_payment_service_health_and_transaction(caplog):
    app = load_app("payment-service/src/main.py")
    client = TestClient(app)
    caplog.set_level(logging.INFO)

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("service") == "payment-service"

    import uuid as _uuid
    tpay = f"pay{_uuid.uuid4().hex[:8]}"
    tx = {"user_id": "u1", "amount": 100.0, "transaction_type": "deposit", "description": "init"}
    r = client.post("/transactions", json=tx, headers={"X-Tenant-ID": tpay})
    assert r.status_code == 201

    # Check structured log
    found = False
    for rec in caplog.records:
        msg = rec.getMessage()
        obj = None
        try:
            obj = json.loads(msg)
        except Exception:
            obj = {"service": rec.__dict__.get("service"), "tenant": rec.__dict__.get("tenant")}

        if obj and obj.get("service") == "payment-service" and obj.get("tenant") == tpay:
            found = True
            break
    assert found, "Did not find structured JSON log for payment-service with tenant tpay"


def test_gemini_adk_wrapper_health_and_log(caplog):
    app = load_app("gemini_adk_wrapper/src/main.py")
    client = TestClient(app)
    caplog.set_level(logging.INFO)

    r = client.get("/health")
    assert r.status_code == 200
    assert "primary_model" in r.json()

    # Trigger a simple request to generate middleware log
    r = client.get("/health")
    assert r.status_code == 200

    found = False
    for rec in caplog.records:
        msg = rec.getMessage()
        obj = None
        try:
            obj = json.loads(msg)
        except Exception:
            obj = {"service": rec.__dict__.get("service"), "tenant": rec.__dict__.get("tenant")}

        if obj and obj.get("service") == "gemini-adk-wrapper":
            found = True
            break
    assert found, "Did not find structured JSON log for gemini-adk-wrapper"
