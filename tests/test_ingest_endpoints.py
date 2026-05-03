from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_ingest_strava_returns_ok():
    result = {"records_fetched": 3, "records_inserted": 2, "records_skipped": 1}
    with patch("ingestion.pipeline.run", return_value=result):
        with TestClient(app) as client:
            response = client.post("/ingest/strava")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["source"] == "strava"
    assert data["records_inserted"] == 2


def test_ingest_whoop_returns_ok():
    result = {"records_fetched": 1, "records_inserted": 1, "records_skipped": 0}
    with patch("ingestion.pipeline.run", return_value=result):
        with TestClient(app) as client:
            response = client.post("/ingest/whoop")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["source"] == "whoop"
    assert data["records_inserted"] == 1


def test_health_still_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingest_strava_returns_500_on_pipeline_failure():
    with patch("ingestion.pipeline.run", side_effect=RuntimeError("API down")):
        with TestClient(app) as client:
            response = client.post("/ingest/strava")

    assert response.status_code == 500
    assert "API down" in response.json()["detail"]
