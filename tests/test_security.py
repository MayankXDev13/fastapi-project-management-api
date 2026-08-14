"""Security surface guard: every non-public route must resolve get_current_user.

This replaces the middleware's "secure by default" enforcement with an explicit
audit: if a developer forgets the dependency on a new route, this test fails.
"""
from deps import get_current_user

# Routes that must remain reachable without authentication
PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json")
PUBLIC_PATHS = {
    "/auth/register",
    "/auth/login",
    "/auth/refresh",
    "/auth/verify-email",
    "/auth/forgot-password",
    "/auth/reset-password",
}


def _is_public(route) -> bool:
    path = route.path
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def test_every_non_public_route_resolves_get_current_user():
    from main import app

    protected = []
    unprotected = []

    for route in app.routes:
        if not hasattr(route, "methods"):
            continue  # e.g. default 404 route
        if _is_public(route):
            continue

        deps = {d.call for d in route.dependant.dependencies}
        if get_current_user in deps:
            protected.append(route.path)
        else:
            unprotected.append(f"{sorted(route.methods)} {route.path}")

    assert not unprotected, f"routes missing get_current_user: {unprotected}"
    assert len(protected) > 0


def test_public_routes_stay_public(client):
    resp = client.post("/auth/login", json={"email": "x@y.com", "password": "p"})
    assert resp.status_code == 401  # reachable without auth (bad creds, not 404/401-auth)


def test_unknown_path_returns_404_not_401(client):
    resp = client.get("/no-such-endpoint")
    assert resp.status_code == 404