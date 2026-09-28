import pytest
from fastapi.testclient import TestClient
from shotmill.desktop_app import create_desktop_app


def test_installed_app_serves_frontend_api_and_uses_explicit_data_root(tmp_path, monkeypatch):
    frontend = tmp_path / "bundle" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<h1>Packaged ShotMill</h1>", encoding="utf-8")
    (frontend / "app.js").write_text("/* bundled application */", encoding="utf-8")
    data = tmp_path / "user-data"
    wrong = tmp_path / "development-data"
    monkeypatch.setenv("SHOTMILL_DATA_ROOT", str(wrong))
    monkeypatch.setenv("SHOTMILL_DATABASE_URL", "sqlite:///wrong.db")
    application = create_desktop_app(data, frontend)
    with TestClient(application) as client:
        assert "Packaged ShotMill" in client.get("/").text
        assert client.get("/app.js").text == "/* bundled application */"
        assert client.get("/health").json()["status"] == "ok"
        response = client.post("/api/v1/projects", json={"title": "Installed project"})
        assert response.status_code == 201, response.text
        assert (data / "shotmill.db").is_file()
        assert client.get("/shotmill.db").status_code == 404
        assert client.get("/api/v1/unknown").status_code == 404
    assert not wrong.exists()
    # Reopening with the same explicit user directory keeps the project.
    with TestClient(create_desktop_app(data, frontend)) as client:
        assert "Installed project" in client.get("/api/v1/projects").text


def test_desktop_data_cannot_be_inside_public_frontend(tmp_path):
    (tmp_path / "index.html").write_text("frontend", encoding="utf-8")
    for data in (tmp_path, tmp_path / "private"):
        with pytest.raises(ValueError, match="must not be stored"):
            create_desktop_app(data, tmp_path)


def test_missing_frontend_fails_before_initializing_data(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    data = tmp_path / "data"
    with pytest.raises(ValueError, match="index.html"):
        create_desktop_app(data, frontend)
    assert not data.exists()
