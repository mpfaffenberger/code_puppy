from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_puppy.api.routers import config as config_router


def test_config_schema_endpoint_returns_mapping_without_config_schema_symbol():
    app = FastAPI()
    app.include_router(config_router.router, prefix="/config")

    with TestClient(app) as client:
        resp = client.get("/config/schema")

    assert resp.status_code == 200
    payload = resp.json()
    assert "keys" in payload
    assert isinstance(payload["keys"], dict)
