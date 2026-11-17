async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_security_headers_allow_camera_for_our_origin_only(client):
    # Operators scan QR codes and photograph damage in the browser.
    resp = await client.get("/api/health")
    assert "camera=(self)" in resp.headers["permissions-policy"]
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_openapi_lists_the_api(client):
    paths = (await client.get("/openapi.json")).json()["paths"]
    assert "/api/auth/login" in paths
    assert "/api/users" in paths


def test_production_refuses_placeholder_secrets(monkeypatch):
    import pytest

    from app.core import settings
    from app.core.config.jwt import DEV_ACCESS_SECRET, DEV_REFRESH_SECRET
    from app.main import create_app

    monkeypatch.setattr(settings.app, "ENV", "production")
    # The placeholders themselves, whatever a developer's .env holds.
    monkeypatch.setattr(settings.jwt, "ACCESS_SECRET_KEY", DEV_ACCESS_SECRET)
    monkeypatch.setattr(settings.jwt, "REFRESH_SECRET_KEY", DEV_REFRESH_SECRET)
    with pytest.raises(RuntimeError, match="JWT_ACCESS_SECRET_KEY"):
        create_app()

    monkeypatch.setattr(settings.jwt, "ACCESS_SECRET_KEY", "a" * 48)
    monkeypatch.setattr(settings.jwt, "REFRESH_SECRET_KEY", "b" * 48)
    assert create_app()  # strong, distinct secrets start fine


async def test_assetlinks_absent_without_a_fingerprint(client):
    # Without a signing certificate there is nothing true to say.
    assert (await client.get("/.well-known/assetlinks.json")).status_code == 404


async def test_assetlinks_names_the_app_when_configured(client, monkeypatch):
    from app.core import settings

    monkeypatch.setattr(settings.app, "ANDROID_SHA256_FINGERPRINTS", "aa:bb, cc:dd")
    body = (await client.get("/.well-known/assetlinks.json")).json()
    target = body[0]["target"]
    assert target["package_name"] == settings.app.ANDROID_PACKAGE_NAME
    assert target["sha256_cert_fingerprints"] == ["AA:BB", "CC:DD"]
