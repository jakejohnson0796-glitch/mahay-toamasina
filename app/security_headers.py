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
from starlette.requests import Request
from starlette.responses import Response

# Content-Security-Policy : liste blanche de ce que le navigateur a le
# droit de charger/executer sur une page de ce site.
# - 'unsafe-inline' reste necessaire pour script-src et style-src car le
#   projet utilise des <script>/style="..." inline dans les templates,
#   sans nonce genere par requete. Ce n'est pas une protection XSS
#   totale (un XSS reflete pourrait encore executer du JS inline), mais
#   ca bloque deja le cas le plus courant : injection d'un <script
#   src="https://domaine-attaquant.com/vole-la-session.js">, qui echoue
#   quoi qu'il arrive puisque seul 'self' est autorise comme SOURCE
#   externe de script. Un durcissement complet (nonces par requete sur
#   chaque <script>) est possible plus tard si besoin.
# - fonts.googleapis.com / fonts.gstatic.com : Google Fonts, charge dans
#   base.html.
_CSP = (
    "default-src 'self'; "
    # cdn.jsdelivr.net : uniquement pour charger le SDK LiveKit (salle
    # virtuelle) — voir classe_salle.html. Sans cette autorisation
    # explicite, le navigateur bloque silencieusement le <script src=...>
    # externe (aucune erreur visible sauf dans la console developpeur),
    # et toute la page semble "ne rien faire" au clic puisque le script
    # n'a jamais fini de s'executer.
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self' ws: wss: https:; "
    # worker-src : le SDK LiveKit cree des Web Workers internes (blob:)
    # pour le traitement audio/video sans bloquer l'interface.
    "worker-src 'self' blob:; "
    "media-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


class EnTetesSecuriteMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, https_actif: bool = False):
        super().__init__(app)
        self.https_actif = https_actif

    async def dispatch(self, request: Request, call_next) -> Response:
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
        reponse.headers["Permissions-Policy"] = "geolocation=(self), microphone=(self), camera=(self)"

        reponse.headers["Content-Security-Policy"] = _CSP

        # HSTS : force le navigateur a ne plus jamais essayer HTTP (meme
        # si quelqu'un tape/clique un lien http://) pendant 1 an, pour ce
        # domaine. Actif uniquement quand https_actif=True (production
        # avec un vrai certificat, via ENVIRONNEMENT — voir main.py),
        # jamais en developpement local ou HTTPS n'est pas configure.
        if self.https_actif:
            reponse.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return reponse
