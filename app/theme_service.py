"""
Theme de reflexion du jour : un sujet ouvert a debattre, affiche sur
/cercles et /quiz/reflexion, identique pour tout le monde pendant toute
une journee (heure de Madagascar), et qui change automatiquement le
lendemain.

Avant ce module, le theme etait genere par un appel a l'IA (Groq) a
CHAQUE affichage de la page (voir ai_quiz.generer_theme_reflexion,
desormais retiree) :
- si GROQ_API_KEY etait absente ou invalide sur le serveur, chaque appel
  retombait sur le meme message d'erreur fixe -> le theme semblait
  "bloque" sur toujours la meme chose ;
- meme quand l'appel reussissait, rien ne garantissait que deux
  utilisateurs (ou la meme personne deux fois) voient le meme theme le
  meme jour, puisque rien n'etait lie a la date.

Ce module remplace cette generation a la volee par une liste organisee
en dur, avec une selection deterministe basee sur la date du jour
(heure de Madagascar) : aucun appel reseau, aucun cout, et le meme
theme pour tout le monde tant que la date ne change pas.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

# Indian/Antananarivo est le veritable fuseau de Madagascar (UTC+3, pas
# d'heure d'ete). Africa/Nairobi a la meme heure aujourd'hui mais c'est
# le fuseau du Kenya : on utilise le bon nom pour rester correct si les
# regles venaient a diverger, et parce que c'est plus lisible dans les
# logs/deboggage d'un projet malgache.
FUSEAU_MADAGASCAR = ZoneInfo("Indian/Antananarivo")

# Date de reference arbitraire (avant le lancement du projet) : le jour 0
# de la rotation. Ne JAMAIS changer cette date une fois en production,
# sinon tous les themes du jour deja vus se decalent.
DATE_REFERENCE = date(2025, 1, 1)

_MOIS_FR = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


@dataclass(frozen=True)
class Theme:
    theme: str
    amorce: str
    # Categories approximatives pour un filtrage optionnel par matiere
    # (voir get_theme_du_jour). Laisser vide = theme "sujet libre",
    # propose quelle que soit la matiere choisie.
    categories: tuple = ()


# Liste extensible : pour ajouter un theme, ajoute simplement une entree
# Theme(...) ici. La rotation s'adapte automatiquement a la nouvelle
# longueur de liste (aucune autre modification necessaire).
THEMES = [
    Theme(
        "Madagascar devrait-elle miser davantage sur la transformation locale de ses matieres premieres ?",
        "Le pays exporte beaucoup de produits bruts (vanille, nickel, cobalt, graphite) qui sont "
        "transformes ailleurs, ou la valeur ajoutee reste. Industrialiser localement coute cher et "
        "prend du temps : est-ce vraiment la priorite, ou faut-il d'abord consolider d'autres bases ?",
        ("economie", "developpement", "entrepreneuriat"),
    ),
    Theme(
        "L'universite malgache devrait-elle rendre un stage en entreprise obligatoire dans chaque filiere ?",
        "Les employeurs se plaignent souvent d'un manque d'experience pratique chez les jeunes diplomes. "
        "Mais toutes les filieres ne se pretent pas facilement a un stage, et les entreprises capables "
        "d'en offrir restent concentrees dans quelques villes.",
        ("education", "universite", "emploi"),
    ),
    Theme(
        "Le numerique peut-il vraiment reduire les inegalites d'acces a l'education a Madagascar ?",
        "Les plateformes en ligne promettent un acces au savoir independant de la geographie. Mais sans "
        "electricite fiable ni connexion internet abordable dans de nombreuses regions, cette promesse "
        "risque-t-elle de creer une nouvelle fracture plutot que de la combler ?",
        ("technologie", "education", "societe"),
    ),
    Theme(
        "Faut-il enseigner davantage en malgache dans le superieur, plutot qu'en francais ?",
        "Certains soutiennent qu'apprendre dans sa langue maternelle facilite la comprehension et "
        "valorise la culture nationale. D'autres craignent une perte de competitivite face a des "
        "etudiants formes en francais ou en anglais sur le marche regional et international.",
        ("culture", "education", "societe"),
    ),
    Theme(
        "L'exode des jeunes diplomes malgaches vers l'etranger est-il un probleme ou une opportunite ?",
        "Beaucoup partent faute de debouches locaux a la hauteur de leur formation. Certains reviennent "
        "ensuite avec capital, reseau et experience ; d'autres ne reviennent jamais. Le pays perd-il "
        "vraiment, ou cette diaspora peut-elle devenir une ressource pour Madagascar ?",
        ("emploi", "societe", "developpement"),
    ),
    Theme(
        "La deforestation a Madagascar est-elle d'abord un probleme economique ou un probleme de gouvernance ?",
        "La culture sur brulis (tavy) et l'exploitation illegale de bois precieux repondent souvent a "
        "des besoins de survie immediats. Est-ce qu'un controle plus strict suffirait, ou faut-il "
        "d'abord offrir de vraies alternatives economiques aux populations concernees ?",
        ("environnement", "societe", "developpement"),
    ),
    Theme(
        "Faut-il limiter l'usage des reseaux sociaux pendant les periodes d'examens universitaires ?",
        "Certains etudiants estiment que ces plateformes nuisent gravement a leur concentration ; "
        "d'autres y trouvent au contraire des groupes d'entraide et des ressources de revision. La "
        "solution est-elle individuelle (autodiscipline) ou collective (regles imposees) ?",
        ("technologie", "education", "societe"),
    ),
    Theme(
        "L'intelligence artificielle va-t-elle remplacer certains metiers a Madagascar plus vite qu'ailleurs ?",
        "Certains pensent que l'automatisation touchera d'abord les economies deja tres numerisees. "
        "D'autres estiment qu'un pays a faible cout de main-d'oeuvre pourrait au contraire adopter ces "
        "outils plus lentement, ou au contraire les sauter directement comme il a saute le telephone fixe.",
        ("technologie", "emploi", "sciences"),
    ),
    Theme(
        "L'entrepreneuriat etudiant devrait-il etre encourage des la licence, au risque de negliger les etudes ?",
        "Lancer une petite activite pendant ses etudes peut apporter experience et revenus, mais aussi "
        "detourner du temps de revision. Les universites devraient-elles integrer cela au cursus, ou "
        "le laisser entierement a l'initiative individuelle ?",
        ("entrepreneuriat", "education", "economie"),
    ),
    Theme(
        "Le tourisme est-il une chance ou un risque pour la culture et l'environnement malgaches ?",
        "Le tourisme apporte des devises et des emplois, notamment dans des regions isolees. Mais il "
        "peut aussi fragiliser des ecosystemes uniques (recifs, forets) et transformer des pratiques "
        "culturelles en simples attractions. Ou tracer la limite ?",
        ("environnement", "culture", "economie"),
    ),
    Theme(
        "Faut-il enseigner l'histoire precoloniale de Madagascar de maniere plus approfondie a l'universite ?",
        "Une partie de l'histoire du pays avant la colonisation reste peu documentee dans les programmes "
        "actuels, davantage centres sur la periode coloniale et l'independance. Mieux la connaitre "
        "changerait-il le rapport des jeunes generations a leur identite nationale ?",
        ("histoire", "culture", "education"),
    ),
    Theme(
        "Le secteur informel doit-il etre davantage integre dans l'economie officielle, ou laisse tel quel ?",
        "Une grande partie de l'activite economique malgache echappe aux statistiques et aux impots. "
        "La formaliser pourrait ameliorer la protection sociale des travailleurs, mais aussi leur "
        "imposer des couts et des contraintes qu'ils n'ont pas aujourd'hui.",
        ("economie", "societe", "developpement"),
    ),
    Theme(
        "Les diplomes universitaires malgaches correspondent-ils vraiment aux besoins du marche du travail ?",
        "Certains employeurs jugent les formations trop theoriques face aux competences reellement "
        "demandees. Faut-il repenser les programmes, ou est-ce au marche du travail de s'adapter a "
        "une main-d'oeuvre plus qualifiee qu'avant ?",
        ("education", "emploi", "universite"),
    ),
    Theme(
        "La recherche scientifique malgache manque-t-elle surtout de moyens, ou de reconnaissance ?",
        "Des chercheurs malgaches publient des travaux reconnus a l'international sur la biodiversite "
        "ou la sante, souvent avec des moyens tres limites. Le vrai frein est-il le financement, ou "
        "le manque de valorisation locale de ces travaux ?",
        ("sciences", "education", "developpement"),
    ),
    Theme(
        "Le changement climatique menace-t-il davantage Madagascar que la plupart des autres pays ?",
        "Cyclones plus frequents, secheresse dans le Sud, erosion cotiere : l'ile est deja touchee de "
        "plein fouet alors qu'elle contribue tres peu aux emissions mondiales. Cette situation change-"
        "t-elle ce que le pays devrait exiger dans les negociations climatiques internationales ?",
        ("environnement", "societe", "actualite"),
    ),
    Theme(
        "Faut-il rendre les stages et memoires de fin d'etudes plus connectes aux problemes reels du pays ?",
        "Beaucoup de sujets de memoire restent tres academiques. Orienter davantage les etudiants vers "
        "des problematiques locales concretes (agriculture, sante, education rurale) renforcerait-il "
        "l'utilite de leurs travaux, ou nuirait-il a leur rigueur scientifique ?",
        ("education", "universite", "developpement"),
    ),
    Theme(
        "La monnaie mobile (Mvola, Orange Money...) a-t-elle plus fait pour l'inclusion financiere que les banques ?",
        "Une grande partie des Malgaches n'a jamais eu de compte bancaire, mais utilise ces services "
        "sur telephone au quotidien. Est-ce une etape transitoire avant un systeme bancaire classique, "
        "ou un modele plus adapte au pays sur le long terme ?",
        ("economie", "technologie", "developpement"),
    ),
    Theme(
        "L'agriculture malgache devrait-elle se moderniser au risque de bouleverser des pratiques ancestrales ?",
        "De nouvelles techniques agricoles pourraient ameliorer les rendements et la resilience face au "
        "climat. Mais elles impliquent aussi des couts, des risques, et parfois une rupture avec des "
        "savoirs transmis depuis des generations. Comment arbitrer ?",
        ("environnement", "economie", "culture"),
    ),
    Theme(
        "Les reseaux familiaux et communautaires freinent-ils ou favorisent-ils la reussite individuelle a Madagascar ?",
        "La solidarite familiale (fihavanana) est une valeur forte, avec ses obligations reciproques. "
        "Aide-t-elle surtout ceux qui reussissent a soutenir les autres, ou peut-elle aussi peser sur "
        "les ambitions individuelles, notamment chez les jeunes qui veulent entreprendre ou etudier loin ?",
        ("societe", "culture"),
    ),
    Theme(
        "Un jeune diplome malgache devrait-il privilegier un grand groupe, une PME, ou lancer sa propre activite ?",
        "Chaque voie a ses compromis : stabilite et formation dans un grand groupe, polyvalence dans "
        "une PME, liberte et risque dans l'entrepreneuriat. Le contexte economique actuel favorise-t-il "
        "plutot l'une de ces trois voies pour un jeune qui commence sa carriere ?",
        ("emploi", "entrepreneuriat", "economie"),
    ),
]


def _formater_date_fr(jour: date) -> str:
    """'15 aout 2026', sans dependre du locale systeme (souvent absent
    ou incoherent sur les serveurs de deploiement)."""
    return f"{jour.day} {_MOIS_FR[jour.month - 1]} {jour.year}"


def date_du_jour_madagascar() -> date:
    """La date 'du jour' au sens ou l'entend un utilisateur a Madagascar,
    quel que soit le fuseau horaire du serveur (qui peut tourner en UTC,
    comme c'est le cas sur Render)."""
    return datetime.now(FUSEAU_MADAGASCAR).date()


def get_theme_du_jour(jour: Optional[date] = None, matiere: Optional[str] = None) -> dict:
    """Renvoie le theme de reflexion du jour, deterministe : la meme
    date renvoie toujours le meme theme, pour tout le monde. Change de
    maniere previsible d'un jour a l'autre (index qui avance de 1 par
    jour), sans jamais appeler l'IA.

    jour : permet de simuler une date precise dans les tests. En usage
    normal, laisser vide (utilise la date actuelle a Madagascar).
    matiere : si fourni et qu'au moins un theme de la liste correspond,
    la rotation se fait uniquement parmi les themes de cette categorie
    (toujours deterministe par date). Sinon, rotation sur la liste
    complete.
    """
    if jour is None:
        jour = date_du_jour_madagascar()

    pool = THEMES
    if matiere:
        matiere_normalisee = matiere.strip().lower()
        filtres = [t for t in THEMES if any(matiere_normalisee in c for c in t.categories)]
        if filtres:
            pool = filtres

    ecart_jours = (jour - DATE_REFERENCE).days
    index = ecart_jours % len(pool)
    theme = pool[index]

    return {
        "theme": theme.theme,
        "amorce": theme.amorce,
        "date": jour.isoformat(),
        "date_affichee": _formater_date_fr(jour),
    }
