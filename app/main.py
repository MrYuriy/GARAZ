# FastAPI application factory: wires routers, middleware and exception handlers.
import hashlib
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from app.core import settings
from app.core.exc import ObjectNotFoundException
from app.core.exc.handlers import register_handlers
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.routers import router

# The Flutter web build (repository GARAZ_app). It is not in this repo: it is
# built elsewhere and bind-mounted here (see docker-compose). Without it the
# API simply serves no web app.
_WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"

_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}
# Safe only because the URL carries a build stamp: a new build is a new path,
# so nothing cached under the old one can ever be served in its place.
_IMMUTABLE_ASSET = {"Cache-Control": "public, max-age=31536000, immutable"}


def _build_stamp() -> str:
    """A short id that changes whenever the build does — by content, because
    the build is copied with tools that preserve modification times."""
    entry = _WEBAPP_DIR / "main.dart.js"
    if not entry.is_file():
        return "0"
    digest = hashlib.sha256()
    with entry.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:12]


def _register_flutter_app(app: FastAPI) -> None:
    """Serve the Flutter web build at /app, with every asset URL versioned.

    Flutter emits `main.dart.js` under a fixed name, and Cloudflare turns our
    `no-cache` into its own four-hour browser TTL — so a deploy would leave
    phones running yesterday's app. Assets are therefore served under
    /app/v/<stamp>/: a new build is a URL no cache has seen, and precisely
    because of that the URL is safe to mark immutable.

    Only index.html is uncached, and it carries the current stamp. An unknown
    stamp still serves the current files: a phone holding an older index must
    get a working app, not a blank page.
    """

    def index() -> HTMLResponse:
        html = (_WEBAPP_DIR / "index.html").read_text(encoding="utf-8")
        # Flutter resolves every asset against <base>, so moving that one tag
        # moves the whole app onto the versioned path.
        html = html.replace('<base href="/app/">', f'<base href="/app/v/{_build_stamp()}/">')
        return HTMLResponse(html, headers=_NO_CACHE)

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def flutter_index() -> HTMLResponse:
        return index()

    @app.get("/", include_in_schema=False)
    async def flutter_root() -> RedirectResponse:
        return RedirectResponse("/app/")

    @app.get("/app/v/{stamp}/{path:path}", include_in_schema=False)
    async def flutter_asset(stamp: str, path: str) -> Response:
        target = (_WEBAPP_DIR / path).resolve()
        # Keep the traversal inside the build directory: `path` is user input.
        if not target.is_relative_to(_WEBAPP_DIR.resolve()) or not target.is_file():
            raise ObjectNotFoundException(path, "Asset")
        return FileResponse(target, headers=_IMMUTABLE_ASSET)


def _assetlinks() -> list[dict]:
    """The statement Android checks before letting our https links — the truck
    QR codes — open the installed app instead of a browser."""
    fingerprints = settings.app.android_fingerprints
    if not fingerprints:
        return []
    return [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": settings.app.ANDROID_PACKAGE_NAME,
                "sha256_cert_fingerprints": fingerprints,
            },
        }
    ]


def _refuse_weak_secrets() -> None:
    """Anywhere but a developer's machine, refuse to start on placeholder JWT
    secrets: anyone who has read this repository could otherwise sign an
    administrator's token."""
    if settings.app.ENV in ("local", "test"):
        return
    weak = settings.jwt.weak_secrets()
    if weak:
        raise RuntimeError(f"Refusing to start with weak secrets in ENV={settings.app.ENV}: {', '.join(weak)}")


def create_app() -> FastAPI:
    _refuse_weak_secrets()
    app = FastAPI(title=settings.app.APP_NAME)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.ALLOWED_ORIGINS,
        # Auth is a Bearer token in the Authorization header, not cookies, so
        # credentialed CORS is not needed (and pairs badly with a wildcard).
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    register_handlers(app)

    @app.get("/.well-known/assetlinks.json", include_in_schema=False)
    async def android_assetlinks() -> JSONResponse:
        statement = _assetlinks()
        if not statement:
            # A statement without a certificate is a verification that fails
            # and gets cached; absent is better than wrong.
            raise ObjectNotFoundException("assetlinks.json", "Asset links")
        return JSONResponse(statement, headers=_NO_CACHE)

    # Same origin as the API, so no CORS and no second deployment.
    if (_WEBAPP_DIR / "index.html").is_file():
        _register_flutter_app(app)

    return app


# Module-level ASGI app for production servers (`uvicorn app.main:app`).
app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.app.HOST, port=settings.app.PORT)
