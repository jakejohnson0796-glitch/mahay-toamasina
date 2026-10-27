"""Routes des jeux classiques (culture générale, chiffres et lettres)."""
import itertools
import json
import random
import re
import secrets
import time
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .auth import utilisateur_courant
from .csrf import verifier_csrf
from .database import get_session
from .templating import templates
from .models import (
    ParticipantTournoiChampion,
    ReponseTournoiChampion,
    TournoiChampion,
    Utilisateur,
)

router = APIRouter(prefix="/jeux-classiques", tags=["jeux-classiques"])

QUESTIONS_PAR_PARTIE = 10
TENTATIVES_MAX = 3
POINTS_QUESTION = 10
BONUS_SERIE = 5
TEMPS_QUESTION_CHAMPION = 20
TEMPS_CHIFFRES = 120
TEMPS_LETTRES = 90
TEMPS_TOURNOI = 20

def _q(
    identifiant,
    theme,
    question,
    choix,
    bonne,
    explication,
    difficulte="moyen",
    type_question="culture",
):
    return {
        "id": identifiant,
        "theme": theme,
        "question": question,
        "choix": choix,
        "bonne": bonne,
        "explication": explication,
        "difficulte": difficulte,
        "type_question": type_question,
    }


# Banque locale : une sélection différente est tirée à chaque partie.
# Les questions et leurs corrections sont indépendantes du rendu scientifique.
QUESTIONS = [
    _q("capitale", "Madagascar", "Quelle est la capitale de Madagascar ?", ["Toamasina", "Antananarivo", "Mahajanga", "Fianarantsoa"], 1, "Antananarivo est la capitale de Madagascar."),
    _q("ocean", "Géographie", "Dans quel océan se trouve Madagascar ?", ["Atlantique", "Pacifique", "Indien", "Arctique"], 2, "Madagascar se trouve dans l'océan Indien."),
    _q("eau", "Sciences", "Quelle est la formule chimique de l'eau ?", ["CO₂", "H₂O", "O₂", "NaCl"], 1, "Une molécule d'eau contient deux atomes d'hydrogène et un atome d'oxygène."),
    _q("premier", "Mathématiques", "Lequel de ces nombres est premier ?", ["21", "27", "29", "33"], 2, "29 n'a que deux diviseurs positifs : 1 et 29."),
    _q("equateur", "Géographie", "Quelle ligne sépare les hémisphères Nord et Sud ?", ["Le tropique du Cancer", "Greenwich", "L'équateur", "Le cercle polaire"], 2, "L'équateur correspond à la latitude zéro."),
    _q("siecle", "Histoire", "Combien d'années compte un siècle ?", ["10", "50", "100", "1 000"], 2, "Un siècle correspond à 100 années."),
    _q("suite", "Logique", "Quelle est la suite : 2, 4, 8, 16, … ?", ["18", "24", "30", "32"], 3, "Chaque terme est multiplié par deux."),
    _q("vitesse", "Physique", "Quelle unité mesure une vitesse dans le système international ?", ["Le mètre", "Le mètre par seconde", "Le kilogramme", "Le newton"], 1, "L'unité SI de la vitesse est le mètre par seconde (m/s)."),
    _q("photosynthese", "Biologie", "Quel gaz les plantes utilisent-elles notamment pour la photosynthèse ?", ["Le dioxyde de carbone", "L'hélium", "L'hydrogène", "Le néon"], 0, "La photosynthèse utilise notamment du dioxyde de carbone et de l'eau."),
    _q("verbe", "Langue", "Quel est l'infinitif de « nous finissons » ?", ["Finir", "Fini", "Finissant", "Finissait"], 0, "« Finissons » est une forme conjuguée du verbe finir."),
    _q("canal-mozambique", "Madagascar", "Quel canal sépare Madagascar du continent africain ?", ["Le canal de Suez", "Le canal de Panama", "Le canal du Mozambique", "Le détroit de Gibraltar"], 2, "Le canal du Mozambique se trouve entre Madagascar et la côte africaine."),
    _q("ariary", "Madagascar", "Quelle est la monnaie de Madagascar ?", ["L'ariary", "Le rand", "Le shilling", "Le franc CFA"], 0, "L'ariary est la monnaie de Madagascar."),
    _q("drapeau", "Madagascar", "Quelles couleurs figurent sur le drapeau malgache ?", ["Bleu, blanc, rouge", "Blanc, rouge, vert", "Vert, jaune, noir", "Rouge, jaune, bleu"], 1, "Le drapeau malgache comporte une bande blanche verticale et deux bandes horizontales rouge et verte."),
    _q("continent", "Géographie", "À quel continent Madagascar est-il rattaché ?", ["Europe", "Asie", "Afrique", "Amérique du Sud"], 2, "Madagascar est un pays insulaire situé au large de l'Afrique australe."),
    _q("lemuriens", "Nature", "Quel groupe d'animaux est particulièrement emblématique de Madagascar ?", ["Les lémuriens", "Les kangourous", "Les ours polaires", "Les pandas géants"], 0, "Les lémuriens sont des primates naturellement présents à Madagascar."),
    _q("jupiter", "Astronomie", "Quelle est la plus grande planète du système solaire ?", ["Mars", "Vénus", "Jupiter", "Mercure"], 2, "Jupiter est la plus grande planète du système solaire."),
    _q("glace", "Sciences", "À quelle température l'eau pure gèle-t-elle, à pression normale ?", ["0 °C", "10 °C", "32 °C", "100 °C"], 0, "L'eau pure gèle autour de 0 °C à pression atmosphérique normale."),
    _q("oxygene", "Chimie", "Quelle formule représente le dioxygène ?", ["CO₂", "O₂", "H₂O", "N₂"], 1, "Le dioxygène est composé de deux atomes d'oxygène : O₂."),
    _q("hexagone", "Mathématiques", "Combien de côtés possède un hexagone ?", ["5", "6", "7", "8"], 1, "Un hexagone possède six côtés."),
    _q("multiplication", "Calcul mental", "Combien font 9 × 7 ?", ["56", "62", "63", "72"], 2, "9 multiplié par 7 donne 63."),
    _q("fraction", "Mathématiques", "Quelle écriture décimale correspond à 3/4 ?", ["0,25", "0,5", "0,75", "1,25"], 2, "3 divisé par 4 vaut 0,75."),
    _q("rectangle", "Mathématiques", "Comment calcule-t-on l'aire d'un rectangle ?", ["Longueur + largeur", "Longueur × largeur", "2 × longueur + largeur", "Longueur ÷ largeur"], 1, "L'aire d'un rectangle est égale à sa longueur multipliée par sa largeur."),
    _q("kilometre", "Unités", "Combien de mètres y a-t-il dans un kilomètre ?", ["100", "500", "1 000", "10 000"], 2, "Un kilomètre équivaut à 1 000 mètres."),
    _q("heure", "Unités", "Combien de minutes compte une heure ?", ["30", "45", "60", "100"], 2, "Une heure compte 60 minutes."),
    _q("octet", "Informatique", "Combien de bits composent un octet ?", ["2", "4", "8", "16"], 2, "Un octet contient huit bits."),
    _q("processeur", "Informatique", "Quel composant exécute les instructions principales d'un ordinateur ?", ["Le clavier", "Le processeur", "L'écran", "L'imprimante"], 1, "Le processeur (CPU) exécute les instructions du programme."),
    _q("html", "Informatique", "Quel langage sert principalement à structurer le contenu d'une page web ?", ["HTML", "MP3", "JPEG", "CSV"], 0, "HTML décrit la structure du contenu d'une page web."),
    _q("css", "Informatique", "Quel langage sert notamment à définir la présentation d'une page web ?", ["SQL", "CSS", "PNG", "FTP"], 1, "CSS définit la présentation visuelle des pages web."),
    _q("democratie", "Éducation civique", "Dans une démocratie représentative, comment les citoyens choisissent-ils généralement leurs représentants ?", ["Par tirage au sort obligatoire", "Par des élections", "Par héritage", "Par ordre alphabétique"], 1, "Les citoyens choisissent leurs représentants lors d'élections."),
    _q("hugolesmiserables", "Littérature", "Qui a écrit le roman « Les Misérables » ?", ["Molière", "Victor Hugo", "Jules Verne", "Albert Camus"], 1, "Victor Hugo a publié « Les Misérables » au XIXe siècle."),
    _q("chevaux", "Langue", "Quel est le pluriel courant du nom « cheval » ?", ["Chevals", "Chevaux", "Chevaus", "Chevales"], 1, "Le pluriel de « cheval » est « chevaux »."),
    _q("sujet", "Grammaire", "Dans une phrase, à quelle question le sujet du verbe répond-il souvent ?", ["Qui est-ce qui fait l'action ?", "Combien ça coûte ?", "Où est le complément ?", "Quel est le temps du verbe ?"], 0, "Le sujet désigne notamment la personne ou la chose dont on parle ou qui accomplit l'action."),
    _q("prendre", "Grammaire", "Quel est le participe passé du verbe « prendre » ?", ["Prenu", "Prenant", "Pris", "Prendu"], 2, "Le participe passé de « prendre » est « pris »."),
    _q("lune", "Astronomie", "Quel est le satellite naturel de la Terre ?", ["Le Soleil", "La Lune", "Mars", "Vénus"], 1, "La Lune est le satellite naturel de la Terre."),
    _q("etoile", "Astronomie", "Quelle étoile éclaire principalement la Terre ?", ["Sirius", "Le Soleil", "Véga", "Polaris"], 1, "Le Soleil est l'étoile la plus proche de la Terre et sa principale source de lumière."),
    _q("coeur", "Biologie", "Quel est le rôle principal du cœur ?", ["Digérer les aliments", "Pomper le sang", "Filtrer l'air", "Produire les os"], 1, "Le cœur propulse le sang dans le système circulatoire."),
    _q("chlorophylle", "Biologie", "Quel pigment contribue à donner leur couleur verte aux feuilles ?", ["La mélanine", "L'hémoglobine", "La chlorophylle", "La kératine"], 2, "La chlorophylle absorbe la lumière utilisée par les plantes pendant la photosynthèse."),
    _q("mammifere", "Biologie", "Quel trait caractérise les mammifères ?", ["Ils ont tous des ailes", "Les femelles allaitent leurs petits", "Ils vivent tous dans l'eau", "Ils pondent tous des œufs"], 1, "Les femelles des mammifères nourrissent leurs petits avec du lait."),
    _q("vertebre", "Biologie", "Quel élément caractérise les vertébrés ?", ["Une coquille", "Une colonne vertébrale", "Six pattes", "Des antennes"], 1, "Les vertébrés possèdent une colonne vertébrale."),
    _q("ebullition", "Sciences", "À quelle température l'eau bout-elle environ au niveau de la mer ?", ["0 °C", "50 °C", "100 °C", "150 °C"], 2, "À pression atmosphérique normale, l'eau bout autour de 100 °C."),
    _q("newton", "Physique", "Quelle est l'unité SI de la force ?", ["Le watt", "Le newton", "Le volt", "Le litre"], 1, "Le newton (N) est l'unité SI de force."),
    _q("ampere", "Physique", "Quelle unité mesure l'intensité du courant électrique ?", ["L'ampère", "Le mètre", "Le kilogramme", "Le degré"], 0, "L'intensité du courant électrique se mesure en ampères."),
    _q("orbite", "Astronomie", "Autour de quel astre les planètes du système solaire orbitent-elles ?", ["La Lune", "Le Soleil", "La Terre", "Jupiter uniquement"], 1, "Les planètes du système solaire orbitent autour du Soleil."),
    _q("vitaminec", "Nutrition", "Quel aliment est une source connue de vitamine C ?", ["L'orange", "Le sucre blanc", "Le sel", "L'huile"], 0, "Les agrumes, dont l'orange, apportent de la vitamine C."),
    _q("octogone", "Mathématiques", "Combien de côtés possède un octogone ?", ["6", "7", "8", "9"], 2, "Un octogone possède huit côtés."),
    _q("baobab", "Madagascar", "Quel arbre est emblématique de plusieurs paysages de l'ouest malgache ?", ["Le baobab", "Le sapin", "L'érable", "Le bouleau"], 0, "Plusieurs espèces de baobabs sont emblématiques des paysages malgaches."),
    _q("misaotra", "Malagasy", "Que signifie généralement « misaotra » en malagasy ?", ["Au revoir", "Merci", "Bonne nuit", "Excusez-moi"], 1, "« Misaotra » signifie « merci »."),
    _q("salama", "Malagasy", "Dans une salutation courante en malagasy, que signifie « salama » ?", ["Bonjour / salut", "À demain", "Je ne sais pas", "Félicitations"], 0, "« Salama » est une salutation courante."),
    _q("energie", "Environnement", "Laquelle de ces sources d'énergie est renouvelable ?", ["Le charbon", "Le pétrole", "Le soleil", "Le gaz naturel"], 2, "L'énergie solaire provient du rayonnement du Soleil et est renouvelable à l'échelle humaine."),
    _q("cycle-eau", "Environnement", "Comment appelle-t-on le passage de l'eau liquide en vapeur ?", ["La fusion", "L'évaporation", "La congélation", "La solidification"], 1, "L'évaporation transforme une partie de l'eau liquide en vapeur."),
    _q("ph-neutre", "Chimie", "Quelle valeur indique un pH neutre dans les conditions habituelles ?", ["0", "3", "7", "14"], 2, "Un pH de 7 est neutre dans les conditions habituelles."),
    _q("adn", "Biologie", "Quel est le rôle principal de l'ADN ?", ["Stocker l'information génétique", "Transporter l'oxygène dans le sang", "Digérer les graisses", "Produire le son"], 0, "L'ADN porte l'information génétique des organismes."),
    _q("chromosomes", "Biologie", "Combien de chromosomes possède généralement une cellule humaine adulte non reproductrice ?", ["23", "32", "46", "64"], 2, "Une cellule humaine somatique possède généralement 46 chromosomes, organisés en 23 paires."),
    _q("mercure", "Astronomie", "Quelle planète est la plus proche du Soleil ?", ["Mercure", "Vénus", "Terre", "Mars"], 0, "Mercure est la planète la plus proche du Soleil."),
    _q("rotation", "Astronomie", "Environ combien de temps la Terre met-elle pour tourner sur elle-même ?", ["Une heure", "24 heures", "30 jours", "365 jours"], 1, "La rotation terrestre dure environ un jour."),
    _q("kilogramme", "Unités", "Combien de grammes équivalent à un kilogramme ?", ["100", "500", "1 000", "10 000"], 2, "Un kilogramme vaut 1 000 grammes."),
    _q("angle-droit", "Mathématiques", "Combien de degrés mesure un angle droit ?", ["45°", "60°", "90°", "180°"], 2, "Un angle droit mesure 90 degrés."),
    _q("triangle", "Mathématiques", "Quelle est la somme des angles intérieurs d'un triangle plan ?", ["90°", "180°", "270°", "360°"], 1, "La somme des angles intérieurs d'un triangle vaut 180 degrés."),
    _q("puissance", "Calcul mental", "Combien vaut 2 puissance 5 ?", ["10", "16", "25", "32"], 3, "2 puissance 5 vaut 2 × 2 × 2 × 2 × 2, soit 32."),
    _q("python", "Informatique", "Lequel de ces noms désigne un langage de programmation ?", ["Python", "Bluetooth", "Photoshop", "Ethernet"], 0, "Python est un langage de programmation généraliste."),
    _q("motdepasse", "Sécurité numérique", "Quel choix améliore généralement la sécurité d'un mot de passe ?", ["Réutiliser le même partout", "Choisir un mot de passe long et unique", "Utiliser uniquement son prénom", "Le partager publiquement"], 1, "Un mot de passe long et unique réduit le risque lié à la réutilisation des identifiants."),
    _q("cloud", "Informatique", "À quoi sert principalement un espace de stockage en ligne ?", ["À stocker et retrouver des fichiers via un service réseau", "À augmenter la taille de l'écran", "À remplacer le clavier", "À recharger la batterie"], 0, "Un service de stockage en ligne permet d'enregistrer et de retrouver des fichiers via un réseau."),
    _q("oxygene-plantes", "Biologie", "Quel gaz est libéré par les plantes pendant la photosynthèse ?", ["Le dioxygène", "Le méthane uniquement", "L'hélium", "L'argon uniquement"], 0, "La photosynthèse libère du dioxygène."),
    _q("racines", "Biologie", "Quel est un rôle important des racines d'une plante ?", ["Absorber l'eau et les sels minéraux", "Produire des sons", "Fabriquer des os", "Transformer la lumière en bruit"], 0, "Les racines absorbent notamment l'eau et les sels minéraux du sol."),
    _q("boussole", "Orientation", "Quel point cardinal une boussole classique indique-t-elle approximativement ?", ["Le nord magnétique", "Le sud géographique exact en toute circonstance", "L'équateur", "Le centre de la Terre"], 0, "Une boussole s'aligne sur le champ magnétique terrestre et indique approximativement le nord magnétique."),
    _q("carre", "Mathématiques", "Combien de côtés égaux possède un carré ?", ["2", "3", "4", "6"], 2, "Un carré possède quatre côtés de même longueur et quatre angles droits."),
    _q("binaire", "Informatique", "Quelle base utilise le système binaire ?", ["La base 2", "La base 8", "La base 10", "La base 16"], 0, "Le système binaire utilise deux chiffres : 0 et 1."),
    _q("pluie", "Météorologie", "Comment appelle-t-on les gouttes d'eau qui tombent des nuages ?", ["La rosée", "La pluie", "Le brouillard", "La vapeur"], 1, "La pluie est une précipitation liquide constituée de gouttes d'eau."),
    _q("recyclage", "Environnement", "Quel geste aide à réduire les déchets ?", ["Jeter tous les objets dans la nature", "Réutiliser ou recycler quand c'est approprié", "Brûler tous les plastiques", "Gaspiller l'eau"], 1, "La réutilisation et le recyclage adaptés contribuent à réduire les déchets."),
]


# Énigmes dédiées au mode compétition : les indices et les explications sont
# volontairement conservés côté serveur et révélés après la réponse.
ENIGMES = [
    _q("enigme-aiguilles", "Énigme", "J'ai deux aiguilles, mais je ne couds jamais. Je peux te dire quand partir. Qui suis-je ?", ["Une horloge", "Un hérisson", "Une boussole", "Un sapin"], 0, "Les aiguilles d'une horloge indiquent l'heure.", "facile", "enigme"),
    _q("enigme-serviette", "Énigme", "Plus je sèche, plus je deviens mouillée. Que suis-je ?", ["Une éponge sèche", "Une serviette", "Une rivière", "Une bougie"], 1, "Une serviette se mouille en absorbant l'eau qu'elle retire d'une surface.", "facile", "enigme"),
    _q("enigme-enfants", "Énigme", "Un père a quatre filles. Chaque fille a le même frère. Combien d'enfants a-t-il ?", ["4", "5", "8", "9"], 1, "Les quatre filles partagent un seul frère : quatre filles et un garçon, donc cinq enfants.", "facile", "enigme"),
    _q("enigme-trous", "Énigme", "Je suis rempli de trous, mais je peux retenir l'eau. Que suis-je ?", ["Un filet", "Une éponge", "Un panier", "Une passoire"], 1, "Les petits trous d'une éponge retiennent l'eau dans ses pores.", "facile", "enigme"),
    _q("enigme-silence", "Énigme", "Si tu prononces mon nom, je disparais. Qui suis-je ?", ["L'obscurité", "Le silence", "Le temps", "Un secret"], 1, "Dès que tu parles pour dire « silence », tu brises le silence.", "facile", "enigme"),
    _q("enigme-grandpere", "Énigme", "Deux pères et deux fils mangent trois mangues ; chacun en mange une. Comment est-ce possible ?", ["Une mangue est coupée en trois", "Ils sont trois : grand-père, père et fils", "L'un ne mange pas", "Il y a quatre personnes"], 1, "Le grand-père est père, le père est à la fois fils et père, et le dernier est fils : trois personnes.", "facile", "enigme"),
    _q("enigme-timbre", "Énigme", "Je peux faire le tour du monde tout en restant dans un coin. Que suis-je ?", ["Une carte", "Un timbre", "Une boussole", "Une fenêtre"], 1, "Un timbre peut voyager sur une enveloppe autour du monde tout en restant dans le coin de celle-ci.", "moyen", "enigme"),
    _q("enigme-oeuf", "Énigme", "On me casse avant de m'utiliser, mais on ne me considère pas comme abîmé. Qui suis-je ?", ["Un œuf", "Un miroir", "Un verre", "Un bâton"], 0, "On casse la coquille d'un œuf pour l'utiliser en cuisine.", "moyen", "enigme"),
    _q("enigme-escalier", "Énigme", "Je monte et je descends, mais je reste toujours à la même place. Qui suis-je ?", ["Un ascenseur en mouvement", "Un escalier", "Un nuage", "Une balançoire"], 1, "L'escalier permet de monter et descendre tout en restant fixe.", "moyen", "enigme"),
    _q("enigme-trou", "Énigme", "Plus tu m'enlèves de matière, plus je deviens grand. Que suis-je ?", ["Un trou", "Un arbre", "Une boîte", "Une ombre"], 0, "Plus on retire de terre, plus le trou creusé est grand.", "moyen", "enigme"),
    _q("enigme-course", "Logique", "Dans une course, tu dépasses la personne qui est en deuxième position. À quelle place te retrouves-tu ?", ["Première", "Deuxième", "Troisième", "Dernière"], 1, "Tu prends la place de la personne dépassée : tu es donc deuxième.", "moyen", "enigme"),
    _q("enigme-mois", "Logique", "Certains mois ont 30 jours et d'autres 31. Combien de mois ont au moins 28 jours ?", ["1", "2", "6", "12"], 3, "Les douze mois ont tous au moins 28 jours.", "moyen", "enigme"),
    _q("enigme-jour", "Logique", "Un homme dit : « Avant-hier, j'avais 17 ans ; l'année prochaine, j'aurai 20 ans. » Comment cela peut-il être vrai ?", ["Il ment", "Son anniversaire est le 31 décembre et nous sommes le 1er janvier", "Il a deux anniversaires par an", "C'est impossible"], 1, "Le 30 décembre il avait 17 ans, le 31 décembre il a eu 18 ans ; cette année il aura 19 ans et l'année prochaine 20 ans. Nous sommes le 1er janvier.", "difficile", "enigme"),
    _q("enigme-ages", "Logique", "Un père a 42 ans et son fils 12 ans. Dans combien d'années le père aura-t-il exactement deux fois l'âge du fils ?", ["6", "12", "18", "20"], 2, "42 + x = 2 × (12 + x), donc 42 + x = 24 + 2x et x = 18.", "difficile", "enigme"),
    _q("enigme-suite", "Logique", "Quelle est la suite logique : 1, 11, 21, 1211, 111221, … ?", ["312211", "211221", "121122", "111222"], 0, "Chaque terme décrit le précédent : 111221 signifie trois 1, deux 2, un 1, soit 312211.", "difficile", "enigme"),
    _q("enigme-chiffre", "Mathématiques", "Je suis un nombre à deux chiffres. La somme de mes chiffres vaut 9 et mon chiffre des dizaines vaut deux fois celui des unités. Qui suis-je ?", ["36", "63", "72", "81"], 1, "Si l'unité vaut 3, la dizaine vaut 6 : 6 + 3 = 9. Le nombre est 63.", "difficile", "enigme"),
    _q("enigme-interrupteurs", "Logique", "Trois interrupteurs sont dehors ; une ampoule est dans une pièce fermée. Tu peux entrer une seule fois. Quelle méthode permet d'identifier le bon interrupteur ?", ["Allumer les trois et entrer", "Allumer A quelques minutes, l'éteindre, allumer B et entrer ; lumière = B, chaleur = A, sinon C", "Allumer A et B puis entrer", "C'est impossible"], 1, "La lumière indique B ; une ampoule éteinte mais chaude indique A ; une ampoule froide et éteinte indique C.", "difficile", "enigme"),
    _q("enigme-jour-semaine", "Logique", "Si avant-hier était jeudi, quel jour serons-nous après-demain ?", ["Dimanche", "Lundi", "Mardi", "Mercredi"], 1, "Avant-hier jeudi signifie aujourd'hui samedi ; après-demain sera lundi.", "difficile", "enigme"),
]
def _choix_numeriques(correct, graine):
    """Produit quatre propositions distinctes et reproductibles pour un calcul."""
    valeurs = [correct]
    decalages = (1, -1, 2, -2, 3, -3, 5, -5, 10, -10, 20, -20, 25, -25, 50, -50)
    for decalage in decalages:
        candidat = correct + decalage
        if candidat >= 0 and candidat not in valeurs:
            valeurs.append(candidat)
        if len(valeurs) == 4:
            break
    candidat = max(0, correct + 7)
    while len(valeurs) < 4:
        if candidat not in valeurs:
            valeurs.append(candidat)
        candidat += 1
    generateur = random.Random(graine)
    generateur.shuffle(valeurs)
    choix = [str(valeur) for valeur in valeurs]
    return choix, choix.index(str(correct))


def generer_questions_calcul():
    """Construit un grand réservoir reproductible de questions de calcul vérifiables."""
    resultat = []

    def ajouter(identifiant, question, reponse, explication, graine):
        choix, bonne = _choix_numeriques(reponse, graine)
        difficulte = "facile" if reponse <= 20 else ("moyen" if reponse <= 200 else "difficile")
        resultat.append(_q(
            identifiant, "Calcul mental", question, choix, bonne, explication,
            difficulte, "calcul",
        ))

    for a in range(1, 61):
        for b in range(a, 61):
            somme = a + b
            ajouter(
                f"calcul-add-{a}-{b}",
                f"Combien font {a} + {b} ?", somme,
                f"{a} + {b} = {somme}.", somme * 101 + a * 7 + b,
            )
    for a in range(2, 61):
        for b in range(1, a):
            difference = a - b
            ajouter(
                f"calcul-sub-{a}-{b}",
                f"Combien font {a} − {b} ?", difference,
                f"{a} − {b} = {difference}.", a * 211 + b * 13,
            )
    for a in range(2, 17):
        for b in range(a, 17):
            produit = a * b
            ajouter(
                f"calcul-mul-{a}-{b}",
                f"Combien font {a} × {b} ?", produit,
                f"{a} × {b} = {produit}.", a * 307 + b * 19,
            )
    for diviseur in range(2, 17):
        for quotient in range(2, 17):
            dividende = diviseur * quotient
            ajouter(
                f"calcul-div-{dividende}-{diviseur}",
                f"Combien font {dividende} ÷ {diviseur} ?", quotient,
                f"{dividende} ÷ {diviseur} = {quotient}. La division est exacte.",
                dividende * 401 + diviseur * 23,
            )
    for n in range(2, 51):
        carre = n * n
        ajouter(
            f"calcul-carre-{n}", f"Combien vaut {n} au carré ?", carre,
            f"{n}² = {n} × {n} = {carre}.", n * 503,
        )
    for n in range(2, 16):
        cube = n ** 3
        ajouter(
            f"calcul-cube-{n}", f"Combien vaut {n} au cube ?", cube,
            f"{n}³ = {n} × {n} × {n} = {cube}.", n * 601,
        )
    conversions = (
        ("metre-centimetre", "Combien de centimètres représentent {n} m ?", 100, "m", "cm"),
        ("kilometre-metre", "Combien de mètres représentent {n} km ?", 1000, "km", "m"),
        ("kilogramme-gramme", "Combien de grammes représentent {n} kg ?", 1000, "kg", "g"),
        ("litre-millilitre", "Combien de millilitres représentent {n} L ?", 1000, "L", "mL"),
        ("heure-minute", "Combien de minutes représentent {n} heures ?", 60, "heures", "minutes"),
    )
    for code, modele, facteur, unite_source, unite_cible in conversions:
        for n in range(1, 61):
            valeur = n * facteur
            ajouter(
                f"conversion-{code}-{n}", modele.format(n=n), valeur,
                f"{n} {unite_source} = {valeur} {unite_cible}.",
                valeur * 701 + n * 29,
            )
    return resultat


def generer_questions_geographie():
    """Ajoute des questions de capitales à partir d'une table de faits stable."""
    capitales = [
        ("Madagascar", "Antananarivo"), ("France", "Paris"), ("Japon", "Tokyo"),
        ("Canada", "Ottawa"), ("Australie", "Canberra"), ("Nouvelle-Zélande", "Wellington"),
        ("Brésil", "Brasília"), ("Argentine", "Buenos Aires"), ("Chili", "Santiago"),
        ("Pérou", "Lima"), ("Mexique", "Mexico"), ("États-Unis", "Washington"),
        ("Royaume-Uni", "Londres"), ("Irlande", "Dublin"), ("Espagne", "Madrid"),
        ("Portugal", "Lisbonne"), ("Italie", "Rome"), ("Allemagne", "Berlin"),
        ("Belgique", "Bruxelles"), ("Suisse", "Berne"), ("Autriche", "Vienne"),
        ("Pologne", "Varsovie"), ("Grèce", "Athènes"), ("Norvège", "Oslo"),
        ("Suède", "Stockholm"), ("Finlande", "Helsinki"), ("Danemark", "Copenhague"),
        ("Islande", "Reykjavik"), ("Maroc", "Rabat"), ("Algérie", "Alger"),
        ("Tunisie", "Tunis"), ("Sénégal", "Dakar"), ("Ghana", "Accra"),
        ("Nigeria", "Abuja"), ("Kenya", "Nairobi"), ("Éthiopie", "Addis-Abeba"),
        ("Tanzanie", "Dodoma"), ("Ouganda", "Kampala"), ("Rwanda", "Kigali"),
        ("Afrique du Sud", "Pretoria"), ("Égypte", "Le Caire"), ("Arabie saoudite", "Riyad"),
        ("Inde", "New Delhi"), ("Pakistan", "Islamabad"), ("Bangladesh", "Dacca"),
        ("Chine", "Pékin"), ("Corée du Sud", "Séoul"), ("Thaïlande", "Bangkok"),
        ("Vietnam", "Hanoï"), ("Indonésie", "Jakarta"), ("Philippines", "Manille"),
        ("Turquie", "Ankara"), ("Ukraine", "Kyiv"), ("Roumanie", "Bucarest"),
        ("Hongrie", "Budapest"), ("Tchéquie", "Prague"), ("Pays-Bas", "Amsterdam"),
        ("Croatie", "Zagreb"), ("Serbie", "Belgrade"), ("Bulgarie", "Sofia"),
        ("Cameroun", "Yaoundé"), ("Côte d'Ivoire", "Yamoussoukro"),
        ("Mali", "Bamako"), ("Niger", "Niamey"), ("Burkina Faso", "Ouagadougou"),
        ("Togo", "Lomé"), ("Bénin", "Porto-Novo"), ("Angola", "Luanda"),
        ("Zambie", "Lusaka"), ("Zimbabwe", "Harare"), ("Mozambique", "Maputo"),
        ("Maurice", "Port-Louis"), ("Comores", "Moroni"), ("Seychelles", "Victoria"),
    ]
    resultat = []
    lieux = [capitale for _, capitale in capitales]
    for index, (pays, capitale) in enumerate(capitales):
        distracteurs = [lieu for lieu in lieux if lieu != capitale]
        generateur = random.Random(10_000 + index)
        choix = [capitale] + generateur.sample(distracteurs, 3)
        generateur.shuffle(choix)
        bonne = choix.index(capitale)
        resultat.append(_q(
            f"geographie-capitale-{index + 1:03d}",
            "Géographie",
            f"Quelle est la capitale de {pays} ?",
            choix, bonne,
            f"La capitale de {pays} est {capitale}.",
            "facile" if index < 24 else "moyen",
            "culture",
        ))
    return resultat


QUESTIONS.extend(ENIGMES)
QUESTIONS.extend(generer_questions_calcul())
QUESTIONS.extend(generer_questions_geographie())

# Dictionnaire français enrichi à partir de la liste de fréquence française de
# pyspellchecker, complété par les mots scolaires et malgaches ci-dessous.
# pyspellchecker est distribué sous licence MIT ; voir les métadonnées du paquet.
MOTS_BASE = set("""
ARBRE TABLE LIVRE ROUTE FLEUR PLAGE ECOLE AMOUR SAVOIR ORANGE SCIENCE HISTOIRE
CALCUL NATURE SOLEIL ETOILE RIVIERE MALAGASY CLASSE ETUDIANT MAISON JARDIN SOURIRE
ENFANT VOYAGE FAMILLE AMITIE BONHEUR CHANCE MUSIQUE DANSE CHANT IMAGE COULEUR
NUAGE PLUIE VENT TERRE MER OCEAN MONTAGNE FORET ANIMAL OISEAU POISSON CHEVAL
CHAT CHIEN SOURIS LAPIN TIGRE LION GIRAFE ZEBRE SINGE LEMUR BAOBAB BANANE MANGUE
PAPAYE CITRON POMME POIRE RAISIN FRUIT LEGUME TOMATE CAROTTE POMME DE TERRE
PAIN RIZ LAIT FROMAGE BEURRE REPAS CUISINE CUILLERE ASSIETTE VERRE BOUTEILLE
CRAYON STYLO CAHIER PAPIER CARTABLE REGLE GOMME TABLEAU LECTURE ECRITURE
PAROLE PHRASE LETTRE MOT VERBE NOM SUJET ACCENT GRAMMAIRE VOCABULAIRE LANGUE
FRANCAIS MALAGASY GEOGRAPHIE MATHEMATIQUE PHYSIQUE CHIMIE BIOLOGIE GEOLOGIE
PLANETE GALAXIE ESPACE FUSEE SATELLITE COMETE METEORITE LUMIERE OMBRE ENERGIE
ELECTRICITE CIRCUIT AIMANT FORCE VITESSE MASSE VOLUME LONGUEUR DISTANCE TEMPS
HEURE MINUTE SECONDE JOUR SEMAINE MOIS ANNEE SIECLE NOMBRE CHIFFRE ADDITION
SOMME PRODUIT DIVISION FRACTION DECIMAL ANGLE TRIANGLE CARRE CERCLE LOSANGE
VOLUME PERIMETRE SURFACE EQUATION LOGIQUE RAISON IDEE MEMOIRE ATTENTION QUESTION
REPONSE EXEMPLE EXERCICE DEVOIR LECON REVISION PROGRES EFFORT OBJECTIF DEFI
POINT SCORE VICTOIRE EQUIPE JOUEUR PARTIE NIVEAU INDICE ASTUCE METHODE
ORDINATEUR CLAVIER ECRAN SOURIS INTERNET RESEAU DONNEE FICHIER DOSSIER
PROGRAMME PYTHON HTML CSS SECURITE MOTDEPASSE COMPTE SESSION NAVIGATEUR
APPLICATION MOBILE TABLETTE SERVEUR CLOUD ROBOT ALGORITHME CODE VARIABLE FONCTION
ECRAN PIXEL VIDEO PHOTO CAMERA MICROPHONE SON IMAGE TEXTE
SANTE CORPS COEUR SANG POUMON CERVEAU OS MUSCLE NERF CELLULE ADN GENETIQUE
ESPECE RACINE FEUILLE TIGE GRAINE FLEUR TERREAU EAU MINERAL OXYGENE CARBONE
CLIMAT NATUREL DURABLE RECYCLE DECHET PROPRETE PROTEGER RESSOURCE SOLAIRE EOLIEN
SOLEIL MERIDIEN EQUATEUR CONTINENT AFRIQUE ASIE EUROPE AMERIQUE MADAGASCAR TOAMASINA
ANTANANARIVO MAHAJANGA FIANARANTSOA TOLIARA ANTSIRABE NOSY VOYAGE PAYS VILLE VILLAGE
TANANA TRANO RANO VARY AINA FIHAVANANA SALAMA MISAOTRA TONGASOA VAZAHA
KILOMETRE METRE GRAMME KILOGRAMME LITRE DEGRE CELSIUS WATT VOLT AMPERE NEWTON
ARITHMETIQUE ALGEBRE GEOMETRIE STATISTIQUE PROBABILITE GRAPHIQUE TABLE DONNEES
ACCUEIL DEBUT RETOUR CHOIX REGLE ESSAI TENTATIVE RAPIDE FACILE DIFFICILE
""".split())

def _charger_dictionnaire_francais():
    mots = set(MOTS_BASE)
    try:
        from spellchecker import SpellChecker

        lexique = SpellChecker(language="fr", distance=1)
        for terme in lexique.word_frequency.words():
            terme = unicodedata.normalize("NFKD", terme)
            terme = "".join(
                caractere for caractere in terme
                if not unicodedata.combining(caractere)
            ).upper()
            terme = terme.replace("'", "").replace("’", "").replace("-", "")
            if 2 <= len(terme) <= 9 and all("A" <= c <= "Z" for c in terme):
                mots.add(terme)
    except (ImportError, OSError, ValueError):
        # La banque minimale reste disponible en mode dégradé.
        pass
    return mots


MOTS = _charger_dictionnaire_francais()


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in texte if not unicodedata.combining(c)).upper().strip()


def effacer_partie_classique(donnees_session):
    """Efface uniquement la partie classique courante, sans toucher au reste de la session."""
    donnees_session.pop("jeux_classiques", None)


def melanger_choix(question, rng=None):
    """Mélange les propositions tout en conservant l'index de la bonne réponse."""
    generateur = rng or random
    paires = list(enumerate(question["choix"]))
    generateur.shuffle(paires)
    choix = [texte for _, texte in paires]
    bonne = next(index for index, (index_initial, _) in enumerate(paires) if index_initial == question["bonne"])
    return choix, bonne


def preparer_question_active(etat, rng=None):
    """Prépare une seule question dans la session pour ne pas mélanger les réponses au rafraîchissement."""
    ids = etat.get("ids", [])
    tour = int(etat.get("tour", 0))
    if tour >= len(ids):
        etat.pop("choix_actifs", None)
        etat.pop("bonne_active", None)
        etat.pop("question_active_id", None)
        return
    question_id = ids[tour]
    if (
        etat.get("question_active_id") == question_id
        and "choix_actifs" in etat
        and "bonne_active" in etat
    ):
        return
    question = next((item for item in QUESTIONS if item["id"] == question_id), None)
    if question is None:
        etat.pop("choix_actifs", None)
        etat.pop("bonne_active", None)
        return
    choix, bonne = melanger_choix(question, rng)
    etat["choix_actifs"] = choix
    etat["bonne_active"] = bonne
    etat["question_active_id"] = question_id


def selectionner_questions_champion(difficulte="moyen", rng=None, nombre=QUESTIONS_PAR_PARTIE):
    """Mélange connaissances et énigmes d'un niveau donné sans répéter de question."""
    generateur = rng or random
    difficulte = difficulte if difficulte in {"facile", "moyen", "difficile"} else "moyen"
    banque_enigmes = [q for q in ENIGMES if q["difficulte"] == difficulte]
    banque_culture = [q for q in QUESTIONS if q["type_question"] != "enigme"]
    nombre_enigmes = min(4, len(banque_enigmes), nombre)
    selection = generateur.sample(banque_enigmes, nombre_enigmes)
    selection += generateur.sample(banque_culture, min(nombre - len(selection), len(banque_culture)))
    if len(selection) < nombre:
        deja = {q["id"] for q in selection}
        restantes = [q for q in QUESTIONS if q["id"] not in deja]
        selection += generateur.sample(restantes, min(nombre - len(selection), len(restantes)))
    generateur.shuffle(selection)
    return selection


def creer_partie_champion(rng=None, mode="champion", difficulte="moyen"):
    """Prépare une partie solo ou contre le bot, avec au moins quatre énigmes."""
    generateur = rng or random
    questions = selectionner_questions_champion(difficulte, generateur, QUESTIONS_PAR_PARTIE)
    etat = {
        "mode": mode,
        "difficulte": difficulte if difficulte in {"facile", "moyen", "difficile"} else "moyen",
        "score": 0,
        "points": 0,
        "tour": 0,
        "serie": 0,
        "meilleure_serie": 0,
        "ids": [question["id"] for question in questions],
    }
    if mode == "champion_bot":
        etat.update({
            "bot_nom": {"facile": "Mora (débutant)", "moyen": "Koto (confirmé)", "difficile": "Haja (expert)"}[etat["difficulte"]],
            "bot_score": 0,
            "bot_correctes": 0,
            "bot_serie": 0,
        })
    preparer_question_active(etat, generateur)
    return etat


def simuler_reponse_bot(bonne, nombre_choix, difficulte="moyen", rng=None):
    """Simule un adversaire avec une probabilité de réussite calibrée par niveau."""
    generateur = rng or random
    probabilite = {"facile": 0.42, "moyen": 0.68, "difficile": 0.90}.get(difficulte, 0.68)
    if generateur.random() < probabilite:
        return True, bonne
    mauvaises = [index for index in range(nombre_choix) if index != bonne]
    return False, generateur.choice(mauvaises)


def preparer_questions_tournoi(difficulte="moyen", rng=None, nombre=QUESTIONS_PAR_PARTIE):
    """Fige les questions, l'ordre des propositions et la correction pour tout le salon."""
    generateur = rng or random
    paquet = []
    for question in selectionner_questions_champion(difficulte, generateur, nombre):
        paires = list(enumerate(question["choix"]))
        generateur.shuffle(paires)
        choix = [option for _, option in paires]
        bonne = next(i for i, (original, _) in enumerate(paires) if original == question["bonne"])
        paquet.append({
            "id": question["id"],
            "theme": question["theme"],
            "question": question["question"],
            "choix": choix,
            "bonne": bonne,
            "explication": question["explication"],
            "difficulte": question["difficulte"],
            "type_question": question["type_question"],
        })
    return paquet


def mot_valide(mot, lettres):
    mot = normaliser(mot).replace(" ", "").replace("-", "").replace("'", "")
    if len(mot) < 2 or mot not in MOTS:
        return False
    disponibles = list(lettres)
    for lettre in mot:
        if lettre not in disponibles:
            return False
        disponibles.remove(lettre)
    return True


def tirer_tirage_lettres(rng=None):
    """Tire neuf lettres et conserve un mot solution garanti parmi les lettres."""
    generateur = rng or random
    solutions = sorted(mot for mot in MOTS if 2 <= len(mot) <= 9)
    mot_solution = generateur.choice(solutions)
    lettres = list(mot_solution)
    voyelles = list("AAAAEEEEIIIOU")
    consonnes = list("BBCCDDFFGGHLLLMMNNNPRRRSSSTTV")
    while len(lettres) < 9:
        pool = voyelles if generateur.random() < 0.48 else consonnes
        lettres.append(generateur.choice(pool))
    generateur.shuffle(lettres)
    return lettres, mot_solution


def tirer_lettres(rng=None):
    """Compatibilité avec les tests et les appels existants."""
    return tirer_tirage_lettres(rng)[0]


def tirer_chiffres(rng=None):
    """Construit un tirage à six nombres avec une solution exacte entre 101 et 999."""
    generateur = rng or random
    pool = list(range(1, 11)) + [25, 50, 75, 100]
    for _ in range(200):
        nombres = generateur.sample(pool, 6)
        candidats = []
        for a, b, c in itertools.permutations(nombres, 3):
            cible = (a + b) * c
            if 101 <= cible <= 999:
                candidats.append((cible, f"({a} + {b}) × {c}", f"Additionne {a} et {b}, puis multiplie le résultat par {c}."))
        if candidats:
            cible, solution, indice = generateur.choice(candidats)
            return nombres, cible, solution, indice
    nombres = [2, 3, 4, 5, 25, 50]
    return nombres, 150, "(25 + 50) × 2", "Additionne 25 et 50, puis multiplie le résultat par 2."


def calculer(expression, nombres, cible):
    """Vérifie une expression arithmétique restreinte sans utiliser eval()."""
    expression = (expression or "").strip().replace("×", "*").replace("÷", "/").replace("−", "-")
    if len(expression) > 100 or not re.fullmatch(r"[0-9+*/().\-\s]+", expression):
        return False, "Expression invalide : utilise les nombres tirés et +, -, × ou ÷."
    compact = expression.replace(" ", "")
    tokens = re.findall(r"\d+|[()+*/-]", compact)
    if "".join(tokens) != compact or not tokens:
        return False, "Expression mathématique invalide."
    position = 0
    utilises = []

    def facteur():
        nonlocal position
        if position >= len(tokens):
            raise ValueError()
        token = tokens[position]
        if token == "-":
            position += 1
            return -facteur()
        if token == "(":
            position += 1
            valeur = somme()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError()
            position += 1
            return valeur
        if token.isdigit():
            position += 1
            nombre = int(token)
            utilises.append(nombre)
            return nombre
        raise ValueError()

    def produit():
        nonlocal position
        valeur = facteur()
        while position < len(tokens) and tokens[position] in ("*", "/"):
            operation = tokens[position]
            position += 1
            droite = facteur()
            if operation == "*":
                valeur *= droite
            else:
                if droite == 0 or valeur % droite != 0:
                    raise ValueError()
                valeur //= droite
        return valeur

    def somme():
        nonlocal position
        valeur = produit()
        while position < len(tokens) and tokens[position] in ("+", "-"):
            operation = tokens[position]
            position += 1
            droite = produit()
            valeur = valeur + droite if operation == "+" else valeur - droite
        return valeur

    try:
        resultat = somme()
        if position != len(tokens) or len(utilises) < 2:
            raise ValueError()
        for nombre in set(utilises):
            if utilises.count(nombre) > list(nombres).count(nombre):
                return False, "Un nombre a été utilisé plus de fois que dans le tirage."
        if any(nombre not in nombres for nombre in utilises):
            return False, "Utilise uniquement les nombres tirés."
        if abs(resultat) > 1_000_000:
            raise ValueError()
        if resultat == cible:
            return True, "Bravo, tu as atteint le nombre cible !"
        return False, f"Ton résultat est {resultat}. La cible était {cible}."
    except (ValueError, ZeroDivisionError, RecursionError):
        return False, "Expression invalide. Vérifie les nombres, les parenthèses et les opérations."



def _normaliser_code_tournoi(code):
    return re.sub(r"[^A-Z2-9]", "", (code or "").upper())[:8]


def _obtenir_tournoi(session, code):
    code = _normaliser_code_tournoi(code)
    if not code:
        return None
    return session.exec(select(TournoiChampion).where(TournoiChampion.code == code)).first()


def _trouver_participant(session, tournoi_id, utilisateur_id):
    return session.exec(
        select(ParticipantTournoiChampion).where(
            ParticipantTournoiChampion.tournoi_id == tournoi_id,
            ParticipantTournoiChampion.utilisateur_id == utilisateur_id,
        )
    ).first()


def _contexte_tournoi(request, session, tournoi, utilisateur):
    participants_db = session.exec(
        select(ParticipantTournoiChampion)
        .where(ParticipantTournoiChampion.tournoi_id == tournoi.id)
        .order_by(ParticipantTournoiChampion.date_adhesion, ParticipantTournoiChampion.id)
    ).all()
    participants = []
    for participant in participants_db:
        membre = session.get(Utilisateur, participant.utilisateur_id)
        participants.append({
            "id": participant.utilisateur_id,
            "nom": membre.nom if membre else "Joueur",
            "score": participant.score,
            "bonnes_reponses": participant.bonnes_reponses,
            "est_createur": participant.utilisateur_id == tournoi.createur_id,
        })

    paquet = json.loads(tournoi.questions_json or "[]")
    index_question = int(tournoi.index_question or 0)
    question = None
    correction = None
    a_repondu = False
    mon_choix = None
    tout_le_monde_a_repondu = False
    if tournoi.statut == "en_cours" and 0 <= index_question < len(paquet):
        donnees_question = paquet[index_question]
        reponses = session.exec(
            select(ReponseTournoiChampion).where(
                ReponseTournoiChampion.tournoi_id == tournoi.id,
                ReponseTournoiChampion.question_index == index_question,
            )
        ).all()
        reponse_courante = next(
            (rep for rep in reponses if rep.utilisateur_id == utilisateur.id),
            None,
        )
        a_repondu = reponse_courante is not None
        mon_choix = reponse_courante.choix if reponse_courante else None
        tout_le_monde_a_repondu = bool(participants_db) and len(reponses) >= len(participants_db)
        question = {
            "theme": donnees_question["theme"],
            "question": donnees_question["question"],
            "choix": donnees_question["choix"],
            "difficulte": donnees_question["difficulte"],
            "type_question": donnees_question["type_question"],
        }
        if tout_le_monde_a_repondu:
            correction = {
                "bonne_texte": donnees_question["choix"][donnees_question["bonne"]],
                "explication": donnees_question["explication"],
            }

    # Le classement est déterminé par le score, puis par le nombre de bonnes réponses.
    classement = sorted(
        participants,
        key=lambda p: (p["score"], p["bonnes_reponses"], p["nom"].casefold()),
        reverse=True,
    )
    return {
        "utilisateur": utilisateur,
        "tournoi": tournoi,
        "code": tournoi.code,
        "participants": participants,
        "classement": classement,
        "question": question,
        "question_index": index_question,
        "numero_question": min(index_question + 1, len(paquet)),
        "nombre_questions": len(paquet),
        "a_repondu": a_repondu,
        "mon_choix": mon_choix,
        "tout_le_monde_a_repondu": tout_le_monde_a_repondu,
        "correction": correction,
        "erreur": request.query_params.get("erreur", ""),
        "est_createur": utilisateur.id == tournoi.createur_id,
    }


@router.get("/tournoi")
def accueil_tournoi(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    return templates.TemplateResponse(
        request,
        "jeux_classiques_tournoi.html",
        {
            "utilisateur": utilisateur,
            "erreur": request.query_params.get("erreur", ""),
            "difficultes": [
                ("facile", "Facile", "Pour se familiariser avec les énigmes"),
                ("moyen", "Moyen", "Un vrai défi de logique"),
                ("difficile", "Difficile", "Des énigmes plus exigeantes"),
            ],
            "mode": "accueil",
        },
    )


@router.post("/tournoi/creer", dependencies=[Depends(verifier_csrf)])
def creer_tournoi(
    request: Request,
    difficulte: str = Form("moyen"),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if difficulte not in {"facile", "moyen", "difficile"}:
        difficulte = "moyen"
    code = ""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        candidat = "".join(secrets.choice(alphabet) for _ in range(6))
        if not _obtenir_tournoi(session, candidat):
            code = candidat
            break
    if not code:
        return RedirectResponse("/jeux-classiques/tournoi?erreur=creation", status_code=303)

    tournoi = TournoiChampion(
        code=code,
        createur_id=utilisateur.id,
        difficulte=difficulte,
        statut="attente",
        questions_json=json.dumps(
            preparer_questions_tournoi(difficulte),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        nb_questions=QUESTIONS_PAR_PARTIE,
    )
    session.add(tournoi)
    session.flush()
    session.add(
        ParticipantTournoiChampion(
            tournoi_id=tournoi.id,
            utilisateur_id=utilisateur.id,
        )
    )
    session.commit()
    return RedirectResponse(f"/jeux-classiques/tournoi/{code}", status_code=303)


@router.post("/tournoi/rejoindre", dependencies=[Depends(verifier_csrf)])
def rejoindre_tournoi(
    request: Request,
    code: str = Form(""),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    code = _normaliser_code_tournoi(code)
    tournoi = _obtenir_tournoi(session, code)
    if not tournoi:
        return RedirectResponse("/jeux-classiques/tournoi?erreur=code", status_code=303)

    participant = _trouver_participant(session, tournoi.id, utilisateur.id)
    if participant:
        return RedirectResponse(f"/jeux-classiques/tournoi/{code}", status_code=303)
    if tournoi.statut != "attente":
        return RedirectResponse("/jeux-classiques/tournoi?erreur=demarre", status_code=303)
    participants = session.exec(
        select(ParticipantTournoiChampion).where(
            ParticipantTournoiChampion.tournoi_id == tournoi.id
        )
    ).all()
    if len(participants) >= 8:
        return RedirectResponse("/jeux-classiques/tournoi?erreur=complet", status_code=303)

    session.add(ParticipantTournoiChampion(tournoi_id=tournoi.id, utilisateur_id=utilisateur.id))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    return RedirectResponse(f"/jeux-classiques/tournoi/{code}", status_code=303)


@router.get("/tournoi/{code}")
def voir_tournoi(code: str, request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    tournoi = _obtenir_tournoi(session, code)
    if not tournoi or not _trouver_participant(session, tournoi.id, utilisateur.id):
        return RedirectResponse("/jeux-classiques/tournoi?erreur=acces", status_code=303)
    return templates.TemplateResponse(
        request,
        "jeux_classiques_tournoi.html",
        _contexte_tournoi(request, session, tournoi, utilisateur) | {"mode": "salon"},
    )


@router.post("/tournoi/{code}/demarrer", dependencies=[Depends(verifier_csrf)])
def demarrer_tournoi(code: str, request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    tournoi = _obtenir_tournoi(session, code)
    if not tournoi or tournoi.createur_id != utilisateur.id:
        return RedirectResponse("/jeux-classiques/tournoi?erreur=acces", status_code=303)
    if tournoi.statut != "attente":
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)
    nombre = session.exec(
        select(ParticipantTournoiChampion).where(
            ParticipantTournoiChampion.tournoi_id == tournoi.id
        )
    ).all()
    if len(nombre) < 2:
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}?erreur=minimum", status_code=303)
    tournoi.statut = "en_cours"
    tournoi.date_demarrage = datetime.utcnow()
    session.add(tournoi)
    session.commit()
    return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)


@router.post("/tournoi/{code}/repondre", dependencies=[Depends(verifier_csrf)])
def repondre_tournoi(
    code: str,
    request: Request,
    choix: int = Form(-1),
    session: Session = Depends(get_session),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    tournoi = _obtenir_tournoi(session, code)
    if not tournoi:
        return RedirectResponse("/jeux-classiques/tournoi?erreur=code", status_code=303)
    participant = _trouver_participant(session, tournoi.id, utilisateur.id)
    if not participant:
        return RedirectResponse("/jeux-classiques/tournoi?erreur=acces", status_code=303)
    paquet = json.loads(tournoi.questions_json or "[]")
    index_question = int(tournoi.index_question or 0)
    if tournoi.statut != "en_cours" or not 0 <= index_question < len(paquet):
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)
    donnees_question = paquet[index_question]
    if choix < 0 or choix >= len(donnees_question["choix"]):
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}?erreur=choix", status_code=303)

    deja_repondu = session.exec(
        select(ReponseTournoiChampion).where(
            ReponseTournoiChampion.tournoi_id == tournoi.id,
            ReponseTournoiChampion.utilisateur_id == utilisateur.id,
            ReponseTournoiChampion.question_index == index_question,
        )
    ).first()
    if deja_repondu:
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)

    correcte = choix == int(donnees_question["bonne"])
    nouvelle_serie = participant.serie + 1 if correcte else 0
    points = (POINTS_QUESTION + (BONUS_SERIE if nouvelle_serie % 3 == 0 else 0)) if correcte else 0
    reponse = ReponseTournoiChampion(
        tournoi_id=tournoi.id,
        utilisateur_id=utilisateur.id,
        question_index=index_question,
        choix=choix,
        correcte=correcte,
        points=points,
    )
    session.add(reponse)
    try:
        # La contrainte unique protège aussi contre les doubles clics simultanés.
        session.flush()
    except IntegrityError:
        session.rollback()
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)
    participant.score += points
    participant.bonnes_reponses += int(correcte)
    participant.serie = nouvelle_serie
    session.add(participant)
    session.commit()
    return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)


@router.post("/tournoi/{code}/suivant", dependencies=[Depends(verifier_csrf)])
def question_suivante_tournoi(code: str, request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    tournoi = _obtenir_tournoi(session, code)
    if not tournoi or tournoi.createur_id != utilisateur.id:
        return RedirectResponse("/jeux-classiques/tournoi?erreur=acces", status_code=303)
    if tournoi.statut != "en_cours":
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)

    participants = session.exec(
        select(ParticipantTournoiChampion).where(
            ParticipantTournoiChampion.tournoi_id == tournoi.id
        )
    ).all()
    reponses = session.exec(
        select(ReponseTournoiChampion).where(
            ReponseTournoiChampion.tournoi_id == tournoi.id,
            ReponseTournoiChampion.question_index == tournoi.index_question,
        )
    ).all()
    if not participants or len(reponses) < len(participants):
        return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}?erreur=attente", status_code=303)

    tournoi.index_question += 1
    paquet = json.loads(tournoi.questions_json or "[]")
    if tournoi.index_question >= len(paquet):
        tournoi.statut = "termine"
        tournoi.date_fin = datetime.utcnow()
    session.add(tournoi)
    session.commit()
    return RedirectResponse(f"/jeux-classiques/tournoi/{tournoi.code}", status_code=303)

@router.get("")
def accueil(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    return templates.TemplateResponse(
        request,
        "jeux_classiques.html",
        {
            "utilisateur": utilisateur,
            "partie": request.session.get("jeux_classiques", {}),
            "questions": QUESTIONS,
            "tentatives_max": TENTATIVES_MAX,
        },
    )


@router.post("/demarrer", dependencies=[Depends(verifier_csrf)])
def demarrer(
    request: Request,
    mode: str = Form(...),
    difficulte: str = Form("moyen"),
    session: Session = Depends(get_session),
):
    if not utilisateur_courant(request, session):
        return RedirectResponse("/connexion", status_code=303)
    if difficulte not in {"facile", "moyen", "difficile"}:
        difficulte = "moyen"
    if mode in {"champion", "champion_bot"}:
        etat = creer_partie_champion(mode=mode, difficulte=difficulte)
    elif mode == "chiffres":
        nombres, cible, solution, indice = tirer_chiffres()
        etat = {
            "mode": mode,
            "score": 0,
            "points": 0,
            "nombres": nombres,
            "cible": cible,
            "solution": solution,
            "indice": indice,
            "indice_affiche": False,
            "tentatives": 0,
            "termine": False,
        }
    elif mode == "lettres":
        lettres, solution = tirer_tirage_lettres()
        etat = {
            "mode": mode,
            "score": 0,
            "points": 0,
            "lettres": lettres,
            "solution": solution,
            "tentatives": 0,
            "meilleur_mot": "",
            "meilleur_points": 0,
            "termine": False,
        }
    else:
        return RedirectResponse("/jeux-classiques", status_code=303)
    request.session["jeux_classiques"] = etat
    return RedirectResponse("/jeux-classiques", status_code=303)


@router.post("/changer", dependencies=[Depends(verifier_csrf)])
def changer_jeu(request: Request, session: Session = Depends(get_session)):
    """Termine la partie courante et revient au choix des jeux."""
    if not utilisateur_courant(request, session):
        return RedirectResponse("/connexion", status_code=303)
    effacer_partie_classique(request.session)
    return RedirectResponse("/jeux-classiques", status_code=303)


@router.post("/indice", dependencies=[Depends(verifier_csrf)])
def afficher_indice(request: Request, session: Session = Depends(get_session)):
    if not utilisateur_courant(request, session):
        return RedirectResponse("/connexion", status_code=303)
    etat = request.session.get("jeux_classiques") or {}
    if etat.get("mode") == "chiffres" and not etat.get("termine") and int(etat.get("tentatives", 0)) > 0:
        etat["indice_affiche"] = True
        request.session["jeux_classiques"] = etat
    return RedirectResponse("/jeux-classiques", status_code=303)


@router.post("/repondre", dependencies=[Depends(verifier_csrf)])
def repondre(
    request: Request,
    reponse: str = Form(""),
    choix: int = Form(-1),
    session: Session = Depends(get_session),
):
    if not utilisateur_courant(request, session):
        return RedirectResponse("/connexion", status_code=303)
    etat = request.session.get("jeux_classiques") or {}
    mode = etat.get("mode")
    if mode not in {"champion", "champion_bot", "chiffres", "lettres"}:
        effacer_partie_classique(request.session)
        return RedirectResponse("/jeux-classiques", status_code=303)

    if mode in {"champion", "champion_bot"}:
        ids = etat.get("ids", [])
        tour = int(etat.get("tour", 0))
        if tour >= len(ids) or "bonne_active" not in etat:
            return RedirectResponse("/jeux-classiques", status_code=303)
        if choix < 0 or choix >= len(etat.get("choix_actifs", [])):
            etat["feedback"] = {"correcte": False, "explication": "Choisis une réponse avant de valider."}
            request.session["jeux_classiques"] = etat
            return RedirectResponse("/jeux-classiques", status_code=303)
        question = next((item for item in QUESTIONS if item["id"] == ids[tour]), None)
        if question is None:
            effacer_partie_classique(request.session)
            return RedirectResponse("/jeux-classiques", status_code=303)
        correcte = choix == int(etat["bonne_active"])
        points_ajoutes = 0
        if correcte:
            etat["score"] = int(etat.get("score", 0)) + 1
            etat["serie"] = int(etat.get("serie", 0)) + 1
            etat["meilleure_serie"] = max(int(etat.get("meilleure_serie", 0)), int(etat["serie"]))
            points_ajoutes = POINTS_QUESTION + (BONUS_SERIE if int(etat["serie"]) % 3 == 0 else 0)
            etat["points"] = int(etat.get("points", 0)) + points_ajoutes
        else:
            etat["serie"] = 0
        feedback = {
            "correcte": correcte,
            "explication": question["explication"],
            "points_ajoutes": points_ajoutes,
        }
        if mode == "champion_bot":
            bot_correcte, bot_choix = simuler_reponse_bot(
                int(etat["bonne_active"]),
                len(etat.get("choix_actifs", [])),
                etat.get("difficulte", "moyen"),
            )
            if bot_correcte:
                etat["bot_correctes"] = int(etat.get("bot_correctes", 0)) + 1
                etat["bot_serie"] = int(etat.get("bot_serie", 0)) + 1
                bonus_bot = BONUS_SERIE if etat["bot_serie"] % 3 == 0 else 0
                etat["bot_score"] = int(etat.get("bot_score", 0)) + POINTS_QUESTION + bonus_bot
            else:
                etat["bot_serie"] = 0
                bonus_bot = 0
            feedback.update({
                "bot_correcte": bot_correcte,
                "bot_choix": bot_choix,
                "bot_points_ajoutes": (POINTS_QUESTION + bonus_bot) if bot_correcte else 0,
            })
        etat["feedback"] = feedback
        etat["tour"] = tour + 1
        preparer_question_active(etat)
    elif mode == "chiffres":
        if etat.get("termine"):
            return RedirectResponse("/jeux-classiques", status_code=303)
        tentatives = int(etat.get("tentatives", 0))
        if tentatives >= TENTATIVES_MAX:
            etat["termine"] = True
            request.session["jeux_classiques"] = etat
            return RedirectResponse("/jeux-classiques", status_code=303)
        correcte, message = calculer(reponse, etat.get("nombres", []), int(etat.get("cible", 0)))
        tentatives += 1
        etat["tentatives"] = tentatives
        if correcte:
            etat["score"] = 1
            etat["points"] = 10 if etat.get("indice_affiche") else 20
            etat["termine"] = True
        elif tentatives >= TENTATIVES_MAX:
            etat["termine"] = True
            message = f"{message} Une solution possible : {etat.get('solution', '')}."
        etat["feedback"] = {
            "correcte": correcte,
            "explication": message,
            "tentatives": tentatives,
        }
    else:  # lettres
        if etat.get("termine"):
            return RedirectResponse("/jeux-classiques", status_code=303)
        tentatives = int(etat.get("tentatives", 0))
        if tentatives >= TENTATIVES_MAX:
            etat["termine"] = True
            request.session["jeux_classiques"] = etat
            return RedirectResponse("/jeux-classiques", status_code=303)
        tentatives += 1
        etat["tentatives"] = tentatives
        mot = normaliser(reponse).replace(" ", "").replace("-", "").replace("'", "")
        correcte = mot_valide(mot, etat.get("lettres", []))
        if correcte:
            points_mot = len(mot) * 5
            if points_mot > int(etat.get("meilleur_points", 0)):
                etat["meilleur_mot"] = mot
                etat["meilleur_points"] = points_mot
            etat["points"] = int(etat.get("meilleur_points", 0))
            etat["score"] = int(etat.get("meilleur_points", 0))
            message = f"Mot accepté : {mot}. Il rapporte {points_mot} points."
            if mot == etat.get("solution"):
                message += " Tu as trouvé le mot choisi pour ce tirage !"
        else:
            message = "Mot non reconnu dans le dictionnaire intégré ou lettres indisponibles."
        termine = tentatives >= TENTATIVES_MAX or (correcte and len(mot) >= 9)
        etat["termine"] = termine
        if termine and etat.get("meilleur_mot"):
            message += f" Meilleur mot : {etat['meilleur_mot']} ({etat['meilleur_points']} points)."
        etat["feedback"] = {
            "correcte": correcte,
            "explication": message,
            "tentatives": tentatives,
        }

    request.session["jeux_classiques"] = etat
    return RedirectResponse("/jeux-classiques", status_code=303)
