# Référencer MITARIDALA dans Google

L'hébergement reste sur Render. Google Search Console sert uniquement à vérifier le site, envoyer son sitemap et suivre son indexation.

## Adresse officielle à déclarer

Utiliser la propriété de type **Préfixe d'URL** :

`https://mitaridala.onrender.com/`

Ne pas déclarer `mahay-toamasina.onrender.com` comme propriété principale : le site MITARIDALA indique déjà son adresse canonique et l'autre sous-domaine ne doit pas créer un doublon dans Google.

## Vérification de propriété

1. Ouvrir [Google Search Console](https://search.google.com/search-console/).
2. Ajouter une propriété de type **Préfixe d'URL** et saisir `https://mitaridala.onrender.com/`.
3. Choisir la méthode **Balise HTML**.
4. Google fournit une balise ressemblant à `<meta name="google-site-verification" content="VALEUR_DU_JETON">`.
5. Copier uniquement la valeur de l'attribut `content`, sans les guillemets et sans la balise complète.
6. Dans Render, ouvrir le service **mitaridala** puis **Environment**. Ajouter la variable `GOOGLE_SITE_VERIFICATION` avec cette valeur et enregistrer. Render redéploiera/redémarrera le service selon sa configuration.
7. Revenir dans Search Console et cliquer sur **Valider**.

Le jeton est injecté dans le HTML par l'application depuis une variable Render. Il n'a pas besoin d'être commité dans le dépôt GitHub. Ne pas le publier dans un fichier source.

## Envoyer le sitemap

Après le déploiement et la validation de propriété :

1. Ouvrir le rapport **Sitemaps** dans Search Console.
2. Saisir `sitemap.xml` (l'URL complète est `https://mitaridala.onrender.com/sitemap.xml`).
3. Envoyer le sitemap et consulter son statut de lecture et les éventuelles erreurs.

Le sitemap contient les pages publiques stables : accueil, présentation, universités, bibliothèque documentaire, cercles d'étude, FAQ, mode d'emploi, contact et cadre légal. Les écrans de connexion, d'inscription et les pages réservées aux utilisateurs ne sont pas proposés à l'indexation.

## Demander l'indexation des pages importantes

Dans **Inspection de l'URL**, tester puis demander l'indexation de :

- `https://mitaridala.onrender.com/`
- `https://mitaridala.onrender.com/a-propos`
- `https://mitaridala.onrender.com/universites`
- `https://mitaridala.onrender.com/faq`
- `https://mitaridala.onrender.com/mode-emploi`

Google décide lui-même du moment d'exploration, d'indexation et du classement. Un sitemap et une demande d'indexation ne garantissent ni l'affichage immédiat ni une position particulière. Le rapport **Pages** de Search Console permet de suivre les résultats.

## Paramètres Render prévus

- `SEO_CANONICAL_BASE_URL` : par défaut `https://mitaridala.onrender.com`. Ne le modifier que si l'adresse officielle change.
- `GOOGLE_SITE_VERIFICATION` : valeur fournie par Search Console à ajouter au service Render `mitaridala`.

Aucun nouveau service, compte payant ou déploiement Google Cloud n'est requis pour cette configuration.
