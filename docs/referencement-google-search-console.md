# Référencer MITARIDALA dans Google

L'hébergement reste sur Render. Google Search Console sert uniquement à vérifier le site, envoyer son sitemap et suivre son indexation.

## Adresse officielle à déclarer

Utiliser la propriété de type **Préfixe d'URL** :

`https://mitaridala.onrender.com/`

Ne pas déclarer `mahay-toamasina.onrender.com` comme propriété principale : le site MITARIDALA indique déjà son adresse canonique et l'autre sous-domaine ne doit pas créer un doublon dans Google.

## Vérification de propriété avec le fichier HTML

1. Dans Google Search Console, sélectionner la méthode **Fichier HTML**.
2. Télécharger le fichier Google fourni pour cette propriété.
3. Conserver exactement son nom et son contenu. Ne pas le renommer, ne pas le modifier et ne pas le placer dans un sous-dossier.
4. Ajouter le fichier à la racine du dépôt GitHub. L'application doit le servir à la racine du site, à l'URL exacte affichée par Google. Pour le fichier actuellement fourni, l'URL est :
   `https://mitaridala.onrender.com/google8d625d7edf0d28f9.html`
5. Fusionner la modification après validation CI et attendre que le déploiement Render soit terminé.
6. Ouvrir l'URL du fichier dans un navigateur : elle doit afficher le texte de vérification Google, sans page 404 ni redirection.
7. Revenir dans Search Console et cliquer sur **Vérifier**.

**Important :** laisser le fichier à la racine du dépôt et ne pas le supprimer après validation. Google peut refaire la vérification ultérieurement.

Une méthode alternative reste disponible dans le code : la balise HTML `google-site-verification` peut être ajoutée via la variable Render `GOOGLE_SITE_VERIFICATION`. Pour le fichier fourni ici, il n'est pas nécessaire de configurer cette variable.


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
