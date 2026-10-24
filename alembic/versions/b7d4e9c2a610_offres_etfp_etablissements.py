"""Ajoute les parcours ETFP et le catalogue des offres par établissement.

Revision ID: b7d4e9c2a610
Revises: a7c3e91f5b24

Import initial partiel de la cartographie officielle METFP. Les établissements
présents sur cette source sont vérifiés comme entrées du répertoire officiel ;
les offres individuelles restent à vérifier car la page ne donne pas une
année scolaire/une session garantissant leur ouverture effective.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "b7d4e9c2a610"
down_revision = "a7c3e91f5b24"
branch_labels = None
depends_on = None

SOURCE_CARTOGRAPHIE = "https://www.metfp.gov.mg/cartographie"

# Codes stables internes pour normaliser les intitulés affichés par le METFP.
# Les libellés sont conservés tels qu'ils figurent dans la cartographie autant
# que possible ; aucune de ces lignes ne prétend remplacer un référentiel RF/RFC.
PARCOURS = {
    "BTPCHEF": ("Genie Civil", "Batiment et Travaux Public", "Chef d'Equipe de chantier"),
    "BTPCOMMIS": ("Genie Civil", "Batiment et Travaux Public", "Commis de chantier"),
    "BTPCARRELEUR": ("Genie Civil", "Batiment et Travaux Public", "Carreleur"),
    "BTPDESSIN": ("Genie Civil", "Batiment et Travaux Public", "Dissanateur Projeteur Métreur"),
    "BTPMENUISIER": ("Genie Civil", "Batiment et Travaux Public", "Menusier en bois"),
    "BTPELECTRICIEN": ("Genie Civil", "Batiment et Travaux Public", "Electricien bâtiment"),
    "BTPPOSEUR": ("Genie Civil", "Batiment et Travaux Public", "Poseur de pavé"),
    "BTPARCHITECTE": ("Genie Civil", "Batiment et Travaux Public", "Architecte"),
    "BTPDECORATEUR": ("Genie Civil", "Batiment et Travaux Public", "Décorateur d'intérieur"),
    "BTPTOPGRAPHE": ("Genie Civil", "Batiment et Travaux Public", "Topographe"),
    "BTPALUMINIUM": ("Genie Civil", "Batiment et Travaux Public", "Menuisier aluminium"),
    "BTPPLOMBIER": ("Genie Civil", "Batiment et Travaux Public", "Aide plombier"),
    "BTPPLATRIER": ("Genie Civil", "Batiment et Travaux Public", "Plâtrier"),
    "BTPCONDUCTEUR_GRUE": ("Genie Civil", "Batiment et Travaux Public", "Conducteur de grue"),
    "BTPCONDUCTEUR_ENGIN": ("Genie Civil", "Batiment et Travaux Public", "Conducteur d'engin"),
    "INDSTRUCTURE": ("Industriel", "STRUCTURE METALLIQUE", "Technicien en ouvrage métallique"),
    "INDTOLIER": ("Industriel", "STRUCTURE METALLIQUE", "Tolier"),
    "INDMECANIQUE": ("Industriel", "MECANIQUE GENERALE", "Mécanicien auto moto"),
    "INDFRAISEUR": ("Industriel", "FABRICATION MECANIQUE", "Fraiseur"),
    "INDELECTROTECH": ("Industriel", "ELECTROTECHNIQUE", "Technicien en maintenance électronique"),
    "INDELECTRONIQUE": ("Industriel", "ELECTRONIQUE", "Electronicien"),
    "INDMAINTENANCE": ("Industriel", "MAINTENANCE INDUSTRIELLE", "Maintenancier industriel"),
    "INDFROID": ("Industriel", "FROID", "Technicien en froid"),
    "INDMETAUX_FEUILLE": ("Industriel", "MECANIQUE GENERALE", "Technicien métaux en feuille"),
    "INDTECH_INDUSTRIEL": ("Industriel", "GENIE INDUSTRIEL ET ENERGIE RENOUVELABLE", "Technicien en génie industriel"),
    "GESTION_COMPTABLE": ("Gestion", "GESTION COMPTABLE", "AGENT COMPTABLE"),
    "GESTION_ENTREPRISE": ("Gestion", "MANAGEMENT ET GESTION D'ENTREPRISE", "TECHNICIEN SUPERIEUR EN MANAGEMENT ET GESTION D'ENTREPRISE"),
    "AGRICULTURE_AGENT": ("Developpement Rural", "AGRICULTURE", "AGENT D'AGRICULTURE"),
    "AGRICULTURE_MARAICHERE": ("Developpement Rural", "AGRICULTURE", "AGRICULTEUR MARAICHERE"),
    "AGRICULTURE_EXPLOITANT": ("Developpement Rural", "AGRICULTURE", "EXPLOITANT AGRICOLE"),
    "AGRICULTURE_RIZICULTEUR": ("Developpement Rural", "AGRICULTURE", "RIZICULTEUR"),
    "AGRICULTURE_FRUIT": ("Developpement Rural", "AGRICULTURE", "PRODUCTEUR D'ARBRES FRUITIERS"),
    "ELEVAGE_TECHNICIEN": ("Developpement Rural", "ELEVAGE", "TECHNICIEN D'ELEVAGE"),
    "ELEVAGE_AVICULTEUR": ("Developpement Rural", "ELEVAGE", "AVICULTEUR"),
    "ELEVAGE_APICULTEUR": ("Developpement Rural", "ELEVAGE", "APICULTEUR"),
    "ELEVAGE_PORC": ("Developpement Rural", "ELEVAGE", "ELEVEUR DE PORC"),
    "TEXTILE_COUTURE": ("Textile - Habillement - Accessoires", "COUPE ET COUTURE", "COUTURIER (E)"),
    "TEXTILE_TAILLEUR": ("Textile - Habillement - Accessoires", "COUPE ET COUTURE", "TAILLEUR COUTURIER"),
    "TEXTILE_BRODERIE": ("Textile - Habillement - Accessoires", "BRODERIE", "BRODEUR / BRODEUSE"),
    "TEXTILE_VANNERIE": ("Textile - Habillement - Accessoires", "VANNERIE", "VANNIER"),
    "TEXTILE_TISSERAND": ("Textile - Habillement - Accessoires", "VANNERIE", "TISSERAND"),
    "COIFFURE_AIDE": ("Art et Technique", "COIFFURE", "AIDE COFFEUSE"),
    "RESTO_PATISSIER": ("Tourisme - Hôtellerie - Restauration", "RESTAURATION", "PATISSIER"),
    "RESTO_CUISINIER": ("Tourisme - Hôtellerie - Restauration", "RESTAURATION", "Cuisinier"),
    "RESTO_RESTAURATEUR": ("Tourisme - Hôtellerie - Restauration", "RESTAURATION", "RESTAURATEUR VILLAGEOIS"),
    "RESTO_COMMIS": ("Tourisme - Hôtellerie - Restauration", "RESTAURATION", "COMMIS DE CUISINE"),
    "ENERGIE_PHOTOVOLTAIQUE": ("AUTRES", "ENERGIE RENOUVELABLE", "INSTALLATEUR EN PHOTOVOLTAIQUE"),
    "SOUDURE": ("", "", "Soudeur-monteur"),
    "MECANIQUE_AGRICOLE": ("", "", "Mécanicien de machines agricoles"),
    "ELEVAGE_AGENT": ("Developpement Rural", "ELEVAGE", "AGENTS D'ELEVAGE"),
    "AGRICULTURE_PLOMBIER": ("Developpement Rural", "AGRICULTURE", "Plombier"),
    "AGRICULTURE_CHARIOT": ("Developpement Rural", "AGRICULTURE", "Conducteur de chariots élévateurs"),
    "AGRICULTURE_JARDINIER": ("Developpement Rural", "AGRICULTURE", "JARDINIER PAYSAGISTE"),
    "AGRICULTURE_MECANICIEN_INDUSTRIEL": ("Developpement Rural", "AGRICULTURE", "Mécanicien industriel"),
    "AGRICULTURE_PEPINIERE": ("", "", "Pépiniériste"),
    "AGRICULTURE_BOVINS": ("", "", "Producteur de bovins"),
    "AGRICULTURE_OVINS": ("", "", "Producteur d’ovins (béliers, brebis, agneaux)"),
    "AGRICULTURE_LEGUMES": ("", "", "Producteur de légumes"),
    "METIER_CUISINIER": ("", "", "Cuisinier"),
    "IND_TEC_METALLIQUE": ("Industriel", "STRUCTURE METALLIQUE", "Technicien en ouvrage métallique"),
    "IND_ENERGIE_SOLAIRE": ("AUTRES", "ENERGIE RENOUVELABLE", "INSTALLATEUR EN PHOTOVOLTAIQUE"),
    "IND_TECH_METIER_IMPRESSION": ("Industriel", "MAINTENANCE INDUSTRIELLE", "Agent de Maintenance en Système d’Impression"),
    "TOURISME_ACCOMPAGNATEUR": ("Tourisme - Hôtellerie - Restauration", "TOURISME", "ACCOMPAGNATEUR TOURISTIQUE"),
    "TOURISME_GUIDE": ("Tourisme - Hôtellerie - Restauration", "TOURISME", "GUIDE INTERPRETE"),
    "TOURISME_AGENT_ACCUEIL": ("Tourisme - Hôtellerie - Restauration", "TOURISME", "AGENTS D'ACCEUIL TOURISTIQUE"),
    "HOTEL_FEMME_CHAMBRE": ("Tourisme - Hôtellerie - Restauration", "HOTELLERIE", "FEMME /VALET DE CHAMBRE"),
    "HOTEL_CONCIERGE": ("Tourisme - Hôtellerie - Restauration", "HOTELLERIE", "CONCIERGE D'HOTEL"),
    "HOTEL_AGENT_ACCUEIL": ("Tourisme - Hôtellerie - Restauration", "HOTELLERIE", "AGENT D'ACCUEIL"),
    "HOTEL_HOTESSE_SALLE": ("Tourisme - Hôtellerie - Restauration", "HOTELLERIE", "HOTESSE DE SALLE"),
    "HOTEL_BARMAN": ("Tourisme - Hôtellerie - Restauration", "HOTELLERIE", "BARMAN"),
    "RESTO_TRAITEUR": ("", "", "Traiteur"),
    "RESTO_CHARCUTIER": ("Tourisme - Hôtellerie - Restauration", "RESTAURATION", "Charcutier"),
    "BTP_FORGERON": ("", "", "Forgeron"),
    "AGRICULTURE_LAITIER": ("", "", "Ouvrier d’exploitation laitière"),
    "AGRICULTURE_MAINTENANCE_EQUIPEMENT": ("Developpement Rural", "MAINTENANCE DES EQUIPEMENTS ET MATERIELS AGRICOLE", "TECHNICIEN EN MAINTENANCE DES EQUIPEMENTS ET MATERIELS AGRICOLE"),
    "MECANICIEN_AUTOMOBILE": ("", "", "Mécanicien d’automobiles"),
}

# Snapshot of facility names clearly displayed on the official METFP map at
# migration authoring time. This is deliberately not the full claimed 24-region
# census. Each mapping uses only offerings explicitly listed under that facility
# in the source. New/ambiguous names must be validated by an administrator.
ETABLISSEMENTS = [
    ("LTP AMBATONDRAZAKA", "ALAOTRA MANGORO", "lycee_technique", None, ["INDSTRUCTURE", "GESTION_ENTREPRISE", "BTPDESSIN", "BTPMENUISIER", "BTPELECTRICIEN", "SOUDURE", "MECANIQUE_AGRICOLE"]),
    ("CFP ANOSIBE AN'ALA", "ALAOTRA MANGORO", "centre_formation_professionnelle", "Anosibe An'Ala", ["TEXTILE_COUTURE", "BTPCOMMIS", "BTPMENUISIER", "BTPPOSEUR", "SOUDURE"]),
    ("LTP MORAMANGA", "ALAOTRA MANGORO", "lycee_technique", "Moramanga", ["GESTION_COMPTABLE", "BTPCHEF", "BTPMENUISIER"]),
    ("CFP SABOTSY ANJIRO", "ALAOTRA MANGORO", "centre_formation_professionnelle", "Sabotsy Anjiro", ["TEXTILE_COUTURE", "BTPCARRELEUR", "BTPCOMMIS", "BTPMENUISIER", "BTPPOSEUR", "RESTO_PATISSIER", "RESTO_CUISINIER"]),
    ("LTP VODIRIANA", "ALAOTRA MANGORO", "lycee_technique", None, ["BTPCHEF"]),
    ("CFP AMBOHIDRATRIMO", "ANALAMANGA", "centre_formation_professionnelle", "Ambohidratrimo", ["TEXTILE_COUTURE", "TEXTILE_TAILLEUR"]),
    ("LTP AMBOHIDRATRIMO", "ANALAMANGA", "lycee_technique", "Ambohidratrimo", ["INDSTRUCTURE", "GESTION_COMPTABLE", "GESTION_ENTREPRISE", "INDELECTRONIQUE", "INDTECH_INDUSTRIEL", "BTPCHEF"]),
    ("LTP ALAROBIA VATOSOLA", "ANALAMANGA", "lycee_technique", "Alarobia Vatosola", ["INDMECANIQUE", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("LTP ANOSIVOLA", "ANALAMANGA", "lycee_technique", None, ["INDSTRUCTURE", "BTPCHEF", "BTPDESSIN"]),
    ("LTP MAHAMASINA", "ANALAMANGA", "lycee_technique", "Mahamasina", ["BTPCHEF", "BTPDESSIN", "BTPCARRELEUR", "BTPMENUISIER", "AGRICULTURE_PLOMBIER"]),
    ("CNFPPSH", "ANALAMANGA", "centre_formation_professionnelle_specialise", None, ["ELEVAGE_AGENT", "ELEVAGE_TECHNICIEN", "ELEVAGE_PORC", "ELEVAGE_AVICULTEUR", "ELEVAGE_APICULTEUR", "COIFFURE_AIDE", "ENERGIE_PHOTOVOLTAIQUE", "INDSTRUCTURE", "INDTOLIER", "INDELECTRONIQUE", "TEXTILE_COUTURE", "TEXTILE_TAILLEUR", "TEXTILE_VANNERIE", "TEXTILE_TISSERAND"]),
    ("LTP AMBOVOMBE", "ANDROY", "lycee_technique", "Ambovombe", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "INDMECANIQUE", "GESTION_COMPTABLE", "TEXTILE_COUTURE", "TEXTILE_VANNERIE", "BTPCHEF", "BTPTOPGRAPHE", "BTPMENUISIER", "BTPELECTRICIEN", "BTPPOSEUR", "RESTO_RESTAURATEUR", "SOUDURE"]),
    ("LTP TSIHOMBE", "ANDROY", "lycee_technique", "Tsihombe", ["GESTION_COMPTABLE", "BTPCHEF"]),
    ("CFP EJEDA", "ATSIMO ANDREFANA", "centre_formation_professionnelle", "Ejeda", ["INDTOLIER", "BTPMENUISIER", "SOUDURE"]),
    ("LTP ANKAZOABO", "ATSIMO ANDREFANA", "lycee_technique", "Ankazoabo", ["GESTION_COMPTABLE", "BTPCHEF"]),
    ("CRFPPV MIARY TOLIARA", "ATSIMO ANDREFANA", "centre_formation_professionnelle_specialise", "Miary Toliara", ["TEXTILE_COUTURE", "TEXTILE_TAILLEUR"]),
    ("CFPF TOLIARA", "ATSIMO ANDREFANA", "centre_formation_professionnelle_specialise", "Toliara", ["GESTION_COMPTABLE", "TEXTILE_COUTURE", "TEXTILE_BRODERIE", "RESTO_PATISSIER"]),
    ("CFPF FARAFANGANA", "ATSIMO ATSINANANA", "centre_formation_professionnelle_specialise", "Farafangana", ["TEXTILE_COUTURE", "RESTO_CUISINIER"]),
    ("CFP AMPAGNARENA", "ATSIMO ATSINANANA", "centre_formation_professionnelle", "Ampagnarena", ["AGRICULTURE_AGENT", "AGRICULTURE_MARAICHERE", "AGRICULTURE_EXPLOITANT", "AGRICULTURE_JARDINIER", "AGRICULTURE_RIZICULTEUR", "AGRICULTURE_FRUIT", "AGRICULTURE_MECANICIEN_INDUSTRIEL", "AGRICULTURE_PLOMBIER", "AGRICULTURE_CHARIOT", "ELEVAGE_AGENT", "ELEVAGE_TECHNICIEN", "ELEVAGE_PORC", "ELEVAGE_AVICULTEUR", "ELEVAGE_APICULTEUR"]),
    ("CFP MAHAFASA", "ATSIMO ATSINANANA", "centre_formation_professionnelle", "Mahafasa", ["AGRICULTURE_MARAICHERE", "ELEVAGE_PORC", "AGRICULTURE_EXPLOITANT", "ELEVAGE_APICULTEUR", "BTPCOMMIS", "BTPMENUISIER", "BTPELECTRICIEN", "AGRICULTURE_PEPINIERE", "ELEVAGE_AVICULTEUR", "AGRICULTURE_OVINS", "AGRICULTURE_BOVINS"]),
    ("CFPF VANGAINDRANO", "ATSIMO ATSINANANA", "centre_formation_professionnelle_specialise", "Vangaindrano", ["TEXTILE_COUTURE", "TEXTILE_BRODERIE", "RESTO_CUISINIER"]),
    ("LTP VANGAINDRANO", "ATSIMO ATSINANANA", "lycee_technique", "Vangaindrano", ["ENERGIE_PHOTOVOLTAIQUE", "INDSTRUCTURE", "GESTION_COMPTABLE", "BTPCHEF", "BTPPOSEUR", "SOUDURE"]),
    ("CFP ANTANAMBAO MANAMPOTSY", "ATSINANANA", "centre_formation_professionnelle", "Antanambao Manampotsy", ["BTPCHEF", "BTPMENUISIER"]),
    ("LTP BRICKAVILLE", "ATSINANANA", "lycee_technique", "Brickaville", ["AGRICULTURE_MARAICHERE", "ENERGIE_PHOTOVOLTAIQUE", "INDSTRUCTURE", "BTPCHEF", "RESTO_RESTAURATEUR", "ELEVAGE_AVICULTEUR"]),
    ("CFP TOAMASINA", "ATSINANANA", "centre_formation_professionnelle", "Toamasina", ["TEXTILE_COUTURE", "RESTO_CUISINIER"]),
    ("LTP TOAMASINA", "ATSINANANA", "lycee_technique", "Toamasina", ["INDSTRUCTURE", "INDMECANIQUE", "AGRICULTURE_AGENT", "GESTION_COMPTABLE", "BTPDESSIN"]),
    ("LTP MAEVATANANA", "BETSIBOKA", "lycee_technique", "Maevatanana", ["GESTION_COMPTABLE", "BTPCHEF"]),
    ("LTP AMBATO BOENY", "BOENY", "lycee_technique", "Ambato Boeny", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("LTP AMBONDROMAMY", "BOENY", "lycee_technique", "Ambondromamy", ["GESTION_COMPTABLE", "INDMECANIQUE"]),
    ("CFP FIRAVAHANA", "BONGOLAVA", "centre_formation_professionnelle", "Firavahana", ["BTPCOMMIS", "BTPMENUISIER"]),
    ("LTP ANKADINONDRY SAKAY", "BONGOLAVA", "lycee_technique", "Ankadinondry Sakay", ["BTPCHEF", "GESTION_COMPTABLE"]),
    ("LTP TSIROANOMANDIDY", "BONGOLAVA", "lycee_technique", "Tsiroanomandidy", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "INDMECANIQUE", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("CFP ANTSIRANANA", "DIANA", "centre_formation_professionnelle", "Antsiranana", ["TEXTILE_COUTURE", "BTPDECORATEUR", "RESTO_PATISSIER", "RESTO_CUISINIER"]),
    ("CFPF ANTSIRANANA", "DIANA", "centre_formation_professionnelle_specialise", "Antsiranana", ["AGRICULTURE_FRUIT", "COIFFURE_AIDE", "TEXTILE_COUTURE", "RESTO_PATISSIER", "RESTO_RESTAURATEUR", "RESTO_CUISINIER"]),
    ("LTP ANTSIRANANA PK3", "DIANA", "lycee_technique", "Antsiranana", ["GESTION_COMPTABLE"]),
    ("LTP ANTSIRANANA PK4", "DIANA", "lycee_technique", "Antsiranana", ["INDSTRUCTURE", "INDMECANIQUE", "GESTION_COMPTABLE", "INDFRAISEUR", "INDELECTROTECH", "INDELECTRONIQUE", "INDMETAUX_FEUILLE", "INDMAINTENANCE", "BTPDESSIN", "BTPMENUISIER"]),
    ("CFP AMBOMBILAVA NOSY BE", "DIANA", "centre_formation_professionnelle", "Nosy Be", ["INDFROID", "INDSTRUCTURE", "INDTOLIER", "TEXTILE_COUTURE", "TEXTILE_TAILLEUR", "TEXTILE_BRODERIE"]),
    ("LTP TSAIKY TSARA DZAMANDZAR", "DIANA", "lycee_technique", "Dzamandzar", ["INDMECANIQUE", "GESTION_COMPTABLE", "BTPELECTRICIEN", "METIER_CUISINIER"]),
    ("LTP ANDAPA", "SAVA", "lycee_technique", "Andapa", ["AGRICULTURE_AGENT", "GESTION_COMPTABLE"]),
    ("CFP AMPANEFENA VOHEMAR", "SAVA", "centre_formation_professionnelle", "Ampanefena", ["BTPCOMMIS"]),
    ("LTP VOHEMAR", "SAVA", "lycee_technique", "Vohemar", ["ELEVAGE_AGENT", "ELEVAGE_TECHNICIEN", "ELEVAGE_PORC", "ELEVAGE_AVICULTEUR", "ELEVAGE_APICULTEUR", "BTPCHEF", "BTPDESSIN", "BTPCARRELEUR", "BTPARCHITECTE", "BTPDECORATEUR", "BTPTOPGRAPHE", "BTPCOMMIS", "BTPMENUISIER", "BTPELECTRICIEN", "BTPPOSEUR", "BTPALUMINIUM", "BTPPLOMBIER", "BTPPLATRIER", "BTPCONDUCTEUR_GRUE", "BTPCONDUCTEUR_ENGIN"]),
    ("LTP ANTSOHIHY", "SOFIA", "lycee_technique", "Antsohihy", ["INDMECANIQUE", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("CFP BEANDRAREZONA", "SOFIA", "centre_formation_professionnelle", "Beandrarezona", ["AGRICULTURE_AGENT", "ELEVAGE_AGENT", "BTPCOMMIS"]),
    ("CFP BEFANDRIANA-SUD", "SOFIA", "centre_formation_professionnelle", "Befandriana Sud", ["BTPCHEF", "BTPMENUISIER"]),
    ("LTP BEFANDRIANA AVARATRA", "SOFIA", "lycee_technique", "Befandriana Avaratra", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "ELEVAGE_PORC", "GESTION_COMPTABLE"]),
    ("CFP AMBOHIBARY SAMBAINA", "VAKINANKARATRA", "centre_formation_professionnelle", "Ambohibary Sambaina", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("CFP ANTSIRABE", "VAKINANKARATRA", "centre_formation_professionnelle", "Antsirabe", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "INDTOLIER"]),
    ("LTP ANTSIRABE", "VAKINANKARATRA", "lycee_technique", "Antsirabe", ["INDMECANIQUE", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("LTP ANDRANOMANELATRA", "VAKINANKARATRA", "lycee_technique", "Andranomanelatra", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "GESTION_COMPTABLE", "BTPCHEF", "SOUDURE", "ELEVAGE_AVICULTEUR", "AGRICULTURE_LEGUMES"]),
    ("CFP ANTSOATANY", "VAKINANKARATRA", "centre_formation_professionnelle", "Antsoatany", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "TEXTILE_COUTURE", "TEXTILE_BRODERIE"]),
    ("CFP MANANDONA", "VAKINANKARATRA", "centre_formation_professionnelle", "Manandona", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "INDTOLIER", "TEXTILE_COUTURE", "TEXTILE_BRODERIE", "BTPCOMMIS", "BTPMENUISIER", "SOUDURE"]),
    ("LTP VINANINKARENA", "VAKINANKARATRA", "lycee_technique", "Vinaninkarena", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "COIFFURE_AIDE", "INDMECANIQUE", "BTPCHEF", "BTPMENUISIER", "SOUDURE", "AGRICULTURE_LEGUMES"]),
    ("CFPF FENERIVE EST", "ANALANJIROFO", "centre_formation_professionnelle_specialise", "Fenerive Est", ["TEXTILE_COUTURE", "TEXTILE_BRODERIE"]),
    ("LTP FENERIVE EST", "ANALANJIROFO", "lycee_technique", "Fenerive Est", ["INDSTRUCTURE", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("CFPF MANAKARA", "FITOVINANY", "centre_formation_professionnelle_specialise", "Manakara", ["TEXTILE_COUTURE", "RESTO_CUISINIER"]),
    ("LTP MANAKARA", "FITOVINANY", "lycee_technique", "Manakara", ["INDSTRUCTURE", "GESTION_COMPTABLE", "BTPCHEF"]),
    ("CFP VOHIPENO", "FITOVINANY", "centre_formation_professionnelle", "Vohipeno", ["AGRICULTURE_AGENT", "TEXTILE_COUTURE"]),
    ("LTP AMBALAVAO", "HAUTE MATSIATRA", "lycee_technique", "Ambalavao", ["GESTION_COMPTABLE", "BTPCHEF"]),
    ("CFP FIANARANTSOA", "HAUTE MATSIATRA", "centre_formation_professionnelle", "Fianarantsoa", ["TEXTILE_COUTURE", "RESTO_CUISINIER"]),
    ("CFPF TSIANOLONDROA", "HAUTE MATSIATRA", "centre_formation_professionnelle_specialise", "Tsianolondroa", ["TEXTILE_COUTURE", "TEXTILE_BRODERIE"]),

]

# Complément du snapshot de cartographie officielle pour toutes les régions
# absentes de l'extraction initiale. Même règle de prudence : les offres
# importées restent à vérifier pour chaque année scolaire.
ETABLISSEMENTS.extend([
    ("CFP MAROATSETRA", "AMBATOSOA", "centre_formation_professionnelle", "Maroantsetra", ["BTPCHEF", "BTPDESSIN", "BTPCARRELEUR", "BTPARCHITECTE", "BTPDECORATEUR", "BTPTOPGRAPHE", "BTPCOMMIS", "BTPMENUISIER", "BTPELECTRICIEN", "BTPPOSEUR", "BTPALUMINIUM", "BTPPLOMBIER", "BTPPLATRIER", "BTPCONDUCTEUR_GRUE", "BTPCONDUCTEUR_ENGIN"]),
    ("LTP MAROANTSETRA", "AMBATOSOA", "lycee_technique", "Maroantsetra", ["AGRICULTURE_MARAICHERE", "INDSTRUCTURE", "GESTION_COMPTABLE", "BTPCHEF", "BTPMENUISIER", "BTPELECTRICIEN", "SOUDURE", "ELEVAGE_AVICULTEUR"]),
    ("CFP AMBATOFINANDRAHANA", "AMORON'I MANIA", "centre_formation_professionnelle", "Ambatofinandrahana", ["TEXTILE_COUTURE", "BTPCHEF", "BTPMENUISIER", "RESTO_PATISSIER"]),
    ("LTP AMBATOFINANDRAHANA", "AMORON'I MANIA", "lycee_technique", "Ambatofinandrahana", ["BTPPOSEUR", "BTPALUMINIUM", "BTPPLOMBIER", "BTPPLATRIER", "BTPCONDUCTEUR_GRUE", "BTPCONDUCTEUR_ENGIN"]),
    ("CFP TSIVORY", "ANOSY", "centre_formation_professionnelle", "Tsivory", ["AGRICULTURE_AGENT", "AGRICULTURE_MARAICHERE", "AGRICULTURE_EXPLOITANT", "AGRICULTURE_JARDINIER", "AGRICULTURE_RIZICULTEUR", "AGRICULTURE_FRUIT", "AGRICULTURE_MECANICIEN_INDUSTRIEL", "AGRICULTURE_PLOMBIER", "AGRICULTURE_CHARIOT", "ELEVAGE_AGENT", "ELEVAGE_TECHNICIEN", "ELEVAGE_PORC", "ELEVAGE_AVICULTEUR", "ELEVAGE_APICULTEUR"]),
    ("CFPF BETROKA", "ANOSY", "centre_formation_professionnelle_specialise", "Betroka", ["TEXTILE_COUTURE"]),
    ("CFPF FORT-DAUPHIN", "ANOSY", "centre_formation_professionnelle_specialise", "Tolagnaro", ["TOURISME_ACCOMPAGNATEUR", "TOURISME_GUIDE", "TOURISME_AGENT_ACCUEIL", "HOTEL_FEMME_CHAMBRE", "HOTEL_CONCIERGE", "HOTEL_AGENT_ACCUEIL", "HOTEL_HOTESSE_SALLE", "HOTEL_BARMAN", "RESTO_PATISSIER", "RESTO_COMMIS", "RESTO_RESTAURATEUR"]),
    ("LTP TOLAGNARO", "ANOSY", "lycee_technique", "Tolagnaro", ["INDMECANIQUE", "GESTION_ENTREPRISE", "TEXTILE_COUTURE", "BTPCHEF", "RESTO_PATISSIER", "MECANICIEN_AUTOMOBILE"]),
    ("CFP IAKORA", "IHOROMBE", "centre_formation_professionnelle", "Iakora", ["BTPCHEF", "RESTO_PATISSIER", "AGRICULTURE_OVINS", "AGRICULTURE_BOVINS"]),
    ("LTP ANDOHANILAKAKA", "IHOROMBE", "lycee_technique", "Andohanilakaka", ["GESTION_COMPTABLE", "BTPCHEF", "BTPDESSIN", "RESTO_PATISSIER"]),
    ("LTP IHOSY", "IHOROMBE", "lycee_technique", "Ihosy", ["GESTION_COMPTABLE", "BTPCHEF", "BTPDESSIN", "BTPPOSEUR", "RESTO_PATISSIER", "BTPMENUISIER"]),
    ("LTP ARIVONIMAMO", "ITASY", "lycee_technique", "Arivonimamo", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "GESTION_COMPTABLE"]),
    ("LTP MIARINARIVO", "ITASY", "lycee_technique", "Miarinarivo", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "AGRICULTURE_MARAICHERE", "GESTION_COMPTABLE", "INDTECH_INDUSTRIEL", "BTPCHEF"]),
    ("LTP SOAVINANDRIANA", "ITASY", "lycee_technique", "Soavinandriana", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "AGRICULTURE_MARAICHERE", "ELEVAGE_AVICULTEUR", "ELEVAGE_APICULTEUR", "GESTION_ENTREPRISE", "BTPCHEF", "BTPELECTRICIEN"]),
    ("LTP MAINTIRANO", "MELAKY", "lycee_technique", "Maintirano", ["GESTION_COMPTABLE", "BTPCHEF"]),
    ("LTP BELO SUR TSIRIBIHINA", "MENABE", "lycee_technique", "Belo sur Tsiribihina", ["AGRICULTURE_AGENT", "INDSTRUCTURE", "BTPCHEF", "BTPMENUISIER", "SOUDURE"]),
    ("LTP MAHABO", "MENABE", "lycee_technique", "Mahabo", ["AGRICULTURE_AGENT", "ELEVAGE_TECHNICIEN", "GESTION_COMPTABLE", "SOUDURE"]),
    ("CFP MANJA", "MENABE", "centre_formation_professionnelle", "Manja", ["AGRICULTURE_AGENT", "ELEVAGE_AGENT", "TEXTILE_COUTURE", "BTPMENUISIER", "RESTO_PATISSIER"]),
    ("LTP MIANDRIVAZO", "MENABE", "lycee_technique", "Miandrivazo", ["COIFFURE_AIDE", "GESTION_COMPTABLE", "BTPMENUISIER", "RESTO_PATISSIER", "SOUDURE"]),
    ("CFPF MANANJARY", "VATOVAVY", "centre_formation_professionnelle_specialise", "Mananjary", ["TEXTILE_COUTURE", "TEXTILE_BRODERIE", "RESTO_PATISSIER", "RESTO_RESTAURATEUR", "RESTO_CUISINIER"]),
    ("LTP MANANJARY", "VATOVAVY", "lycee_technique", "Mananjary", ["INDSTRUCTURE", "INDMECANIQUE", "BTPCHEF", "BTPMENUISIER"]),
    ("CRFPPV MAHAJANGA", "BOENY", "centre_formation_professionnelle_specialise", "Mahajanga", ["AGRICULTURE_MAINTENANCE_EQUIPEMENT", "TEXTILE_COUTURE", "TEXTILE_TAILLEUR"]),
])

def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return value[:120] or "SANS-CODE"


def upgrade() -> None:
    op.create_table(
        "parcourstechniqueprofessionnel",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("secteur", sa.String(length=120), nullable=True),
        sa.Column("filiere", sa.String(length=180), nullable=True),
        sa.Column("metier", sa.String(length=180), nullable=True),
        sa.Column("source_officielle", sa.String(length=500), nullable=False),
        sa.Column("statut_validation", sa.String(length=20), server_default="a_verifier", nullable=False),
        sa.Column("est_actif", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.Column("date_maj", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(coalesce(filiere, ''))) > 0 OR length(trim(coalesce(metier, ''))) > 0",
            name="ck_parcours_etfp_filiere_ou_metier",
        ),
        sa.UniqueConstraint("code", name="uq_parcourstechniqueprofessionnel_code"),
    )
    for column in ("code", "secteur", "filiere", "metier", "statut_validation", "est_actif"):
        op.create_index(f"ix_parcourstechniqueprofessionnel_{column}", "parcourstechniqueprofessionnel", [column], unique=(column=="code"))

    op.create_table(
        "offreetablissementsscolaire",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("etablissement_id", sa.Integer(), sa.ForeignKey("etablissementscolaire.id"), nullable=False),
        sa.Column("code_offre", sa.String(length=160), nullable=False),
        sa.Column("type_offre", sa.String(length=20), nullable=False),
        sa.Column("niveau_scolaire_id", sa.Integer(), sa.ForeignKey("niveauscolaire.id"), nullable=True),
        sa.Column("option_scolaire_id", sa.Integer(), sa.ForeignKey("optionscolaire.id"), nullable=True),
        sa.Column("matiere_scolaire_id", sa.Integer(), sa.ForeignKey("matierescolaire.id"), nullable=True),
        sa.Column("parcours_etfp_id", sa.Integer(), sa.ForeignKey("parcourstechniqueprofessionnel.id"), nullable=True),
        sa.Column("annee_scolaire", sa.String(length=20), nullable=True),
        sa.Column("source_officielle", sa.String(length=500), nullable=False),
        sa.Column("statut_validation", sa.String(length=20), server_default="a_verifier", nullable=False),
        sa.Column("est_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("date_creation", sa.DateTime(), nullable=False),
        sa.Column("date_maj", sa.DateTime(), nullable=False),
        sa.Column("valide_par_id", sa.Integer(), sa.ForeignKey("utilisateur.id"), nullable=True),
        sa.Column("date_validation", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "(type_offre = 'classe' AND niveau_scolaire_id IS NOT NULL AND option_scolaire_id IS NULL AND matiere_scolaire_id IS NULL AND parcours_etfp_id IS NULL) OR "
            "(type_offre = 'serie' AND niveau_scolaire_id IS NOT NULL AND option_scolaire_id IS NOT NULL AND matiere_scolaire_id IS NULL AND parcours_etfp_id IS NULL) OR "
            "(type_offre = 'matiere' AND niveau_scolaire_id IS NOT NULL AND matiere_scolaire_id IS NOT NULL AND parcours_etfp_id IS NULL) OR "
            "(type_offre = 'formation' AND niveau_scolaire_id IS NULL AND option_scolaire_id IS NULL AND matiere_scolaire_id IS NULL AND parcours_etfp_id IS NOT NULL)",
            name="ck_offre_etablissement_cible_type",
        ),
    )
    for column in ("etablissement_id", "type_offre", "niveau_scolaire_id", "option_scolaire_id", "matiere_scolaire_id", "parcours_etfp_id", "annee_scolaire", "statut_validation", "est_active", "valide_par_id"):
        op.create_index(f"ix_offreetablissementsscolaire_{column}", "offreetablissementsscolaire", [column])
    op.create_index(
        "uq_offre_etablissement_code_active",
        "offreetablissementsscolaire",
        ["etablissement_id", "code_offre", "annee_scolaire"],
        unique=True,
        postgresql_where=sa.text("est_active = TRUE"),
        sqlite_where=sa.text("est_active = 1"),
    )
    op.create_index(
        "ix_offre_etablissement_statut_type",
        "offreetablissementsscolaire",
        ["etablissement_id", "statut_validation", "type_offre", "est_active"],
    )

    conn = op.get_bind()
    now = datetime.utcnow()
    path_ids = {}
    for code, (secteur, filiere, metier) in PARCOURS.items():
        code_parcours = _slug("-".join(part for part in (secteur, filiere, metier) if part))
        existing = conn.execute(
            sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
            {"code": code_parcours},
        ).first()
        if existing:
            path_id = existing[0]
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO parcourstechniqueprofessionnel "
                    "(code, secteur, filiere, metier, source_officielle, statut_validation, est_actif, date_creation, date_maj) "
                    "VALUES (:code, :secteur, :filiere, :metier, :source, 'verifie', TRUE, :created, :updated)"
                ),
                {
                    "code": code_parcours,
                    "secteur": secteur or None,
                    "filiere": filiere or None,
                    "metier": metier,
                    "source": SOURCE_CARTOGRAPHIE,
                    "created": now,
                    "updated": now,
                },
            )
            path_id = conn.execute(
                sa.text("SELECT id FROM parcourstechniqueprofessionnel WHERE code=:code"),
                {"code": code_parcours},
            ).scalar_one()
        path_ids[code] = path_id

    for nom, region, type_etablissement, commune, code_parcours in ETABLISSEMENTS:
        stable_code = "METFP-" + _slug(region) + "-" + _slug(nom)
        row = conn.execute(
            sa.text(
                "SELECT id FROM etablissementscolaire "
                "WHERE lower(trim(nom))=lower(trim(:nom)) "
                "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
            ),
            {"nom": nom, "region": region},
        ).first()
        if row:
            etablissement_id = row[0]
            conn.execute(
                sa.text(
                    "UPDATE etablissementscolaire SET "
                    "code=coalesce(code, :code), type_etablissement=:type, "
                    "source_officielle=:source, est_verifie=TRUE, est_actif=TRUE, "
                    "date_maj=:updated WHERE id=:id"
                ),
                {
                    "code": stable_code,
                    "type": type_etablissement,
                    "source": SOURCE_CARTOGRAPHIE,
                    "updated": now,
                    "id": etablissement_id,
                },
            )
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO etablissementscolaire "
                    "(nom, code, type_etablissement, secteur, region, district, commune, source_officielle, est_verifie, est_actif, date_creation, date_maj) "
                    "VALUES (:nom, :code, :type, 'inconnu', :region, NULL, :commune, :source, TRUE, TRUE, :created, :updated)"
                ),
                {
                    "nom": nom,
                    "code": stable_code,
                    "type": type_etablissement,
                    "region": region,
                    "commune": commune,
                    "source": SOURCE_CARTOGRAPHIE,
                    "created": now,
                    "updated": now,
                },
            )
            etablissement_id = conn.execute(
                sa.text(
                    "SELECT id FROM etablissementscolaire WHERE lower(trim(nom))=lower(trim(:nom)) "
                    "AND lower(trim(coalesce(region, '')))=lower(trim(:region))"
                ),
                {"nom": nom, "region": region},
            ).scalar_one()

        for code in sorted(set(code_parcours)):
            path_id = path_ids[code]
            code_offre = "FORMATION:" + _slug(code)
            existe = conn.execute(
                sa.text(
                    "SELECT id FROM offreetablissementsscolaire "
                    "WHERE etablissement_id=:etablissement AND code_offre=:code AND est_active=TRUE"
                ),
                {"etablissement": etablissement_id, "code": code_offre},
            ).first()
            if existe:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO offreetablissementsscolaire "
                    "(etablissement_id, code_offre, type_offre, parcours_etfp_id, annee_scolaire, "
                    "source_officielle, statut_validation, est_active, date_creation, date_maj) "
                    "VALUES (:etablissement, :code, 'formation', :parcours, NULL, :source, "
                    "'a_verifier', TRUE, :created, :updated)"
                ),
                {
                    "etablissement": etablissement_id,
                    "code": code_offre,
                    "parcours": path_id,
                    "source": SOURCE_CARTOGRAPHIE,
                    "created": now,
                    "updated": now,
                },
            )


def downgrade() -> None:
    op.drop_index("ix_offre_etablissement_statut_type", table_name="offreetablissementsscolaire")
    op.drop_index("uq_offre_etablissement_code_active", table_name="offreetablissementsscolaire")
    for column in ("etablissement_id", "type_offre", "niveau_scolaire_id", "option_scolaire_id", "matiere_scolaire_id", "parcours_etfp_id", "annee_scolaire", "statut_validation", "est_active", "valide_par_id"):
        op.drop_index(f"ix_offreetablissementsscolaire_{column}", table_name="offreetablissementsscolaire")
    op.drop_table("offreetablissementsscolaire")
    for column in ("code", "secteur", "filiere", "metier", "statut_validation", "est_actif"):
        op.drop_index(f"ix_parcourstechniqueprofessionnel_{column}", table_name="parcourstechniqueprofessionnel")
    op.drop_table("parcourstechniqueprofessionnel")
