"""Cloisonnement central des comptes responsables légaux."""

def chemin_autorise_responsable(method: str, path: str, user_id: int) -> bool:
    """Liste blanche des routes permises à un compte responsable."""
    method = (method or "GET").upper()
    if method in {"GET", "HEAD"} and path.startswith("/static/"):
        return True
    if method in {"GET", "HEAD"}:
        segments = (path or "").strip("/").split("/")
        if (
            len(segments) == 4
            and segments[0] == "famille"
            and segments[1] == "bulletins"
            and segments[2].isdecimal()
            and segments[3] == "telecharger"
        ):
            return True
    if method in {"GET", "HEAD"} and path in {
        "/famille",
        "/securite",
        "/health",
        "/ready",
        "/favicon.ico",
        "/sw.js",
        "/cadre-legal",
        "/conditions-utilisation",
        "/charte-ethique",
        "/confidentialite",
        "/mentions-legales",
        "/faq",
        "/contact",
        "/a-propos",
        "/universites",
        "/mode-emploi",
    }:
        return True
    if method == "POST" and path in {
        "/deconnexion",
        "/securite/mot-de-passe",
    }:
        return True
    if method in {"GET", "POST"} and path.startswith("/securite/2fa/"):
        return True
    if method in {"GET", "HEAD"} and path == f"/profil/photo/{user_id}":
        return True
    return False
