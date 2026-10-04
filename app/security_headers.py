"""
En-tetes HTTP de securite, appliques a toutes les reponses.

Chacun bloque une categorie d'attaque precise cote navigateur — voir les
commentaires sur chaque ligne. Beaucoup de ces protections sont invisibles
tant que personne n'essaie de les exploiter, mais elles ne coutent rien
en performance et suppriment des classes entieres de vulnerabilites cote
client (clickjacking, sniffing MIME, fuite de referrer, injection de
script depuis un domaine tiers...).
"""
from starlette.middleware.base import BaseHTTPMiddleware
import base64
import hashlib
import secrets
from starlette.requests import Request
from starlette.responses import Response

# Content-Security-Policy stricte : nonce par requete pour les scripts/styles
# inline, hashes explicites pour les rares attributs style statiques, et
# aucun unsafe-inline. Les handlers JS inline sont interdits par
# script-src-attr 'none'.
# - fonts.googleapis.com / fonts.gstatic.com : Google Fonts, charge dans
#   base.html.
STYLE_ATTR_HASHES = "'sha256-a4tj1WXEmGqOxBANAF3uzawGDJwaj6X3GnmrjTUzhuc=' 'sha256-Ughnv5r8tK3/oHB3p8YQZ+vF725quB1RPhCqKGS/KTQ=' 'sha256-Tl6ZzXZTB/MAx8vGpiV6YbVR9OAUW+8yizzHJpJSSjw=' 'sha256-voJlexhB0IHK5kpJNt+JEr/9VVuMFBi2jDWsQEncIQw=' 'sha256-keBQY9zgQt16YPxO1OK2jYKUlePIU46VUoBwh/6Ip8o=' 'sha256-g6wc7vdud1aSmTLcpHjWXR0Wfvqff5mhy00lnnvIu5c=' 'sha256-jHI4GIJKbnQmioE+3fs6bBjltegdPExljL8+MHRxezo=' 'sha256-iDEby3cN6+r/ONIYfwy6Vk9669LI3j90zW2aW2ZmIzM=' 'sha256-mwyReBrBoNNQC0S1A8H2a2KaJVdunFXahDAA6xEWGCs=' 'sha256-4S4hNIn3R4fXu51NbtGixVbuBtMyv/xuWa9dnJ/K1zY=' 'sha256-kzZGHxlHI4lsz7h7xxPRFS01Nt/zW+V4fwP/Vkc46Fo=' 'sha256-GrOBwjKCuRTKrpFmQB5wym96MqxClFE3CjLoHbfUBBM=' 'sha256-9i5NxKLKkwjpZqOXGv7/Spp3mnWvN3DpF9402n0BcD0=' 'sha256-SdF6c8hZUCcetlafgmoE09DHKtasJgGYY6CWnA4DRC8=' 'sha256-02ObSVUox8Jemge0oiQ9C1xwK2uZrOMeqo8pLzcnFpU=' 'sha256-t0ERT1oxM/9A3taCws2P0LClidnwfvk0GCUBPAmPWIg=' 'sha256-IPHRyIwrUqeimQx4teFsDisoJYpGW/pLBhVCd3aHuLQ=' 'sha256-0+tUz0tLThbIy58eHWpQ9JBb/WTbkv/CyQn6FHjsmsU=' 'sha256-ELp1PPOc4V6fxTRIKOBfchPkiEl8kTmMfzr5gcHusYQ=' 'sha256-EO4NFfc7Iaif2gfVTFQER5m59dxVaWmkttwJ1GBAj3E=' 'sha256-EpRRn8UTeRTYku6zLrvPMbhfG04OfGpeku3jtDP/CLc=' 'sha256-UnTLbZnilmadVpG538KvvXqGulNXBnUb4zJoVjh8e7s=' 'sha256-+YerF4rXCYbDgnnRMoQBkNGzV2l6M6PROF3pqAxVkjY=' 'sha256-+rJRgHVNkSfEMpN4X3iKvVgfgAc6gOGutYmhxw79pSo=' 'sha256-vGaYnAV+FUX0rc8iCzhw19uXSfIwOSTd9hSi2z3p+cE=' 'sha256-nFJ+3/yrhOnSCrBolwPAUiQEtW1aoa7C2PTPVOP3MZ4=' 'sha256-pZrZ2Hlmv9UF15OvXYYmmoYFezxI9b1g1mJ5jAmb4sw=' 'sha256-YlOHamSaY0ai4QEZYjD+9Mf+UG1KI007SUtO6nnQNKQ=' 'sha256-dUjjlVOE1OUypKdELrQGXTant6MMiHSxEgfb1O+L0Eg=' 'sha256-BFxzLteMCPy4uHerpLQ7LxjbcaQ3xmZbltWeONHJBcs=' 'sha256-8Aq9Gk0LmikIIN68sxw+TSnnz9vYLLSwC5b/p18ytlk=' 'sha256-OJZfmxjKcyB8jYAH0fsVx8gg9uQT/wo70OhSWBGrI2Y=' 'sha256-aCJ6kSmQKVey0qNHti04Dz6Y8tyggd41eWs9T3+Ivic=' 'sha256-m3XTiIF20AAl/JoLbhZCLpVDCCo+QhhIqpqq9SZ30Dk=' 'sha256-ZMe51dTDf5Kw4XJzW6Q5d9fHG0n1Gp6cjO2Fdefr6bU=' 'sha256-ZNXnT2QfUqVf08oeFA6ruXeuOClPGEdNRaLrbwL/pYY=' 'sha256-BxfTixbzWASTwa9U70ecq+3c7G9Kka/BOPGy+5yUsro=' 'sha256-zncCahfL9QsEBrV4VD2l8O7sCCVPJT8+NepxD5sKeyI=' 'sha256-x/vT5vgUfR8TXmeXIl13BnqPFkTq9NwtO5NMNFGyJPU=' 'sha256-8l1h+HyFO2w7AFGmcX/h/LKG0bGH1PBa5QThd/kzTHk=' 'sha256-0EZqoz+oBhx7gF4nvY2bSqoGyy4zLjNF+SDQXGp/ZrY=' 'sha256-RNZBzkfVG/aVUvmwKQU7S1mZPIi8wfrAEiYo8A/P4KU=' 'sha256-z+1notcFA5+aTqTNLqSfIJI/ZTVrqbGnhnG68JlUJkQ=' 'sha256-fStU1NpIX5UjQN6fmHPDuLpaXG1BWyVT0hLkGeml/3I=' 'sha256-O6lUOwqJC7VnZwEb/ywPLwTjhK59NwOSnR4OAP7c92A=' 'sha256-O0r7xEOHIDP+4tsRViXednAQJXB15GGVC9+hZMTHQbk=' 'sha256-aeK9Qu/HK2d3ha2s3E6WFhUsvUUw5y29B7+k5s3+7Zs=' 'sha256-RCsCPlU52CtIRNNS7jAHKQnZEcAOjjd8Oeo0MPekLSw=' 'sha256-xrueQXnNjuluIBugmE2gl2YH0SBs74mx0xrgOC1otsY=' 'sha256-lxxbj+uRNOp6YC3gUGJeYbIeZvpgr8rLmyIdAe1lKx0=' 'sha256-SO72E1ozudjPIbowJR6fCBNOkyQHbVKMe9GxoQykopA=' 'sha256-Juw/UkSCVa2Xb3LM4V6l/FOy1AwhNJH3yYb+qpUQBqA=' 'sha256-YHAhTw3V41AYTax+5Uqi/wrp10QhgK3x5cvrusJcObY=' 'sha256-fKO2R0JtjzsXY0/57kxLN21RbYfs+fJZwkx6030/BN4=' 'sha256-mDadwrEfiIpWEKgqPnbUR6iErjFtn6c4DpzE1wAdXgg=' 'sha256-wCGyS/En2s9v9SKpNV47cV8z2c21aGL6TjI/x7xKY5I=' 'sha256-yf2CHWERaOiGm6dmAI8XtYKK7HszIriflsI/ZCviwxI=' 'sha256-NXTqLL8/I59UmOnV7tNjFWxURPt85KaZpa7nT1w/lDE=' 'sha256-5LQYgeq6PKXbnsnp014mEf3owoJ7zfTNBvW39+lX98M=' 'sha256-NeVcGVDZiJwdBoIlkevgcp0HS4lFJwtycjt8t5R67pQ=' 'sha256-qFxhV3M2fLROpszOq8NePWwYh7whaaBxJhWiEQG+bhY=' 'sha256-j3eICw/WNfqJ2hNHuLsS3Fx+BaUnvHVqHtk7+8P3WJ8=' 'sha256-c0rKpHyNBKv6WMmSdvxfaFk8BpUkrl21bObZ9eSzvsc=' 'sha256-lUYCxiUFsaokE8PelRF2iPVAtvYcACNao0xnW04g1n0=' 'sha256-SBwPDxqm+Uda71AJSTiMArAvBrup4PN6a0nyC/eKLjU=' 'sha256-jPVtngIzoWkjJVP2byeK3/iiFlTVNiI0RB7nS5Wucyo=' 'sha256-vfMrP+9ENatXjfOvPnjF44QawYxXd7oWPvQmM84orkM=' 'sha256-OmHwQWeD520xkkbNnz/eslKrrEaO5V+VBNHQvfzy5iE='"

def _construire_csp(nonce: str) -> str:
    return (
        "default-src 'self'; "
        "script-src 'self' 'nonce-" + nonce + "' 'strict-dynamic' https://cdn.jsdelivr.net; "
        "script-src-attr 'none'; "
        "style-src 'self' 'nonce-" + nonce + "' https://fonts.googleapis.com https://cdn.jsdelivr.net " + STYLE_ATTR_HASHES + "; "
        "style-src-attr 'unsafe-inline' 'unsafe-hashes' " + STYLE_ATTR_HASHES + "; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://*.supabase.co; "
        "connect-src 'self' ws: wss: https://*.supabase.co; "
        "worker-src 'self' blob:; "
        "media-src 'self' blob:; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "manifest-src 'self';"
    )



# Compatibilite pour les anciens tests/imports internes. La production
# utilise toujours _construire_csp() avec un nonce unique par requete.
_CSP = _construire_csp("compat-test-nonce")


class EnTetesSecuriteMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, https_actif: bool = False):
        super().__init__(app)
        self.https_actif = https_actif

    async def dispatch(self, request: Request, call_next) -> Response:
        # Nonce unique par requete, expose au moteur Jinja via request.state.
        request.state.csp_nonce = secrets.token_urlsafe(32)
        reponse = await call_next(request)

        # Empeche le navigateur de deviner un type de contenu different
        # de celui declare (ex: interpreter un upload comme du HTML/JS
        # execute plutot que comme le fichier statique/telecharge prevu).
        reponse.headers["X-Content-Type-Options"] = "nosniff"

        # Interdit totalement d'afficher le site dans une <iframe>, meme
        # depuis le site lui-meme : bloque le clickjacking (page
        # invisible superposee pour faire cliquer la victime a son insu).
        reponse.headers["X-Frame-Options"] = "DENY"

        # N'envoie l'URL complete comme Referer qu'aux requetes vers le
        # meme site ; pour les liens sortants vers d'autres domaines, ne
        # transmet que l'origine (pas le chemin complet, qui pourrait
        # contenir des donnees sensibles dans l'URL).
        reponse.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

       # Autorise micro/camera/geolocalisation uniquement pour l'origine du
       # site elle-meme ("self") — la classe virtuelle (LiveKit) a besoin du
       # micro/camera. Aucun domaine tiers ni iframe etranger ne peut y
       # acceder, meme si un script malveillant s'executait.
        reponse.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=(self)"

        reponse.headers["Content-Security-Policy"] = _construire_csp(request.state.csp_nonce)
        reponse.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        reponse.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        if request.session.get("user_id"):
            reponse.headers["Cache-Control"] = "no-store, max-age=0"
            reponse.headers["Pragma"] = "no-cache"

        # HSTS : force le navigateur a ne plus jamais essayer HTTP (meme
        # si quelqu'un tape/clique un lien http://) pendant 1 an, pour ce
        # domaine. Actif uniquement quand https_actif=True (production
        # avec un vrai certificat, via ENVIRONNEMENT — voir main.py),
        # jamais en developpement local ou HTTPS n'est pas configure.
        if self.https_actif:
            reponse.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return reponse
