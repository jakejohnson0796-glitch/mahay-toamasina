import asyncio

from app.request_limits import (
    AVATAR_BODY_LIMIT,
    DEFAULT_MAX_BODY_SIZE,
    MULTIPLE_DOCUMENT_BODY_LIMIT,
    SINGLE_DOCUMENT_BODY_LIMIT,
    RequestSizeLimitMiddleware,
    limite_corps_requete,
)


def _scope(path="/test", method="POST", headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("example.test", 443),
    }


def test_rejects_oversized_content_length_before_calling_application():
    called = False
    sent = []

    async def application(scope, receive, send):
        nonlocal called
        called = True

    async def receive():
        raise AssertionError("Le corps ne doit pas être lu après un Content-Length trop grand.")

    async def send(message):
        sent.append(message)

    middleware = RequestSizeLimitMiddleware(application, default_max_body_size=4)
    asyncio.run(
        middleware(
            _scope(headers=[(b"content-length", b"5")]),
            receive,
            send,
        )
    )

    assert not called
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert sent[1]["type"] == "http.response.body"
    assert b"too large" in sent[1]["body"].lower()


def test_rejects_chunked_body_that_crosses_limit_and_returns_413():
    chunks = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]
    consumed = bytearray()
    sent = []

    async def receive():
        if chunks:
            return chunks.pop(0)
        return {"type": "http.disconnect"}

    async def application(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            consumed.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    async def send(message):
        sent.append(message)

    middleware = RequestSizeLimitMiddleware(application, default_max_body_size=4)
    asyncio.run(middleware(_scope(), receive, send))

    assert bytes(consumed) == b"abc"
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert b"too large" in sent[1]["body"].lower()


def test_allows_body_at_or_below_limit():
    chunks = [{"type": "http.request", "body": b"abcd", "more_body": False}]
    sent = []

    async def receive():
        return chunks.pop(0) if chunks else {"type": "http.disconnect"}

    async def application(scope, receive, send):
        message = await receive()
        assert message["body"] == b"abcd"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    async def send(message):
        sent.append(message)

    middleware = RequestSizeLimitMiddleware(application, default_max_body_size=4)
    asyncio.run(middleware(_scope(), receive, send))

    assert sent[0]["status"] == 200


def test_upload_routes_have_explicit_limits_and_other_routes_stay_small():
    assert limite_corps_requete("POST", "/documents/upload") == SINGLE_DOCUMENT_BODY_LIMIT
    assert limite_corps_requete("POST", "/documents/detect") == SINGLE_DOCUMENT_BODY_LIMIT
    assert limite_corps_requete("POST", "/classe/devoirs/123/rendre") == SINGLE_DOCUMENT_BODY_LIMIT
    assert limite_corps_requete("POST", "/profil/photo") == AVATAR_BODY_LIMIT
    assert limite_corps_requete("POST", "/documents/upload-multiple") == MULTIPLE_DOCUMENT_BODY_LIMIT
    assert limite_corps_requete("POST", "/connexion") == DEFAULT_MAX_BODY_SIZE
    assert limite_corps_requete("GET", "/documents/upload") == DEFAULT_MAX_BODY_SIZE
