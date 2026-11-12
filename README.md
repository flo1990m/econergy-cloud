# Econergy Cloud — Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://www.hacs.xyz/)
[![Version bêta](https://img.shields.io/badge/version-2.1.2--b%C3%AAta-orange.svg)](https://github.com/flo1990m/econergy-cloud/releases)

Intégration communautaire Home Assistant pour les radiateurs Econergy / Carrera, basée sur l'API officielle Econergy Lab.

> **Version bêta :** l'intégration est encore en développement et peut contenir des défauts. Projet communautaire indépendant, non affilié à Econergy et non officiellement pris en charge par le fabricant. Elle dépend de l'API cloud Econergy ; ses fonctions peuvent évoluer avec l'API.

## Fonctionnalités

- Découverte des domiciles autorisés par le compte Econergy et des radiateurs associés.
- Entité `climate` : arrêt, hors-gel, manuel et programmation ; température ambiante et consigne.
- Programmation hebdomadaire avec un éditeur en français : sept jours, jusqu'à trois plages Confort par jour, consignes Éco/Confort, copie des réglages entre jours et activation explicite du mode Programmation.
- Réglages : butée maximale, protection enfant et verrouillage du clavier.
- Capteurs : température ambiante, puissance nominale, firmware, date d'installation, dernière communication, dernière remontée d'état, régime appliqué, état de chauffe, détection de fenêtre ouverte et consommation estimée.
- Actions : actualisation à la demande, actualisation de la consommation, renommage du radiateur et récupération de la notice lorsqu'elle existe.
- Suivi des commandes avec attente de leur confirmation par l'API ; le dernier statut est conservé après un redémarrage de Home Assistant et aucune commande incertaine n'est renvoyée automatiquement.
- Régime appliqué déterminé à partir de l'état du radiateur et, en mode Programmation, de la consigne et du créneau hebdomadaire en cours.
- Authentification OAuth 2.0 avec PKCE ; aucun mot de passe Econergy ni jeton à copier dans YAML.

## Installation avec HACS / Marketplace

Le dépôt doit d'abord être ajouté comme dépôt personnalisé :

1. Ouvre **Paramètres → Marketplace** dans Home Assistant.
2. Choisis **Ajouter à partir d'un lien**.
3. Saisis `flo1990m/econergy-cloud` (ou `https://github.com/flo1990m/econergy-cloud`).
4. Sélectionne le type **Intégration**, puis valide.
5. Télécharge **Econergy Cloud** et redémarre Home Assistant.
6. Va dans **Paramètres → Appareils et services → Ajouter une intégration**, puis recherche **Econergy Cloud**.
7. Termine l'autorisation Econergy dans la fenêtre OAuth. Le compte doit disposer des autorisations `readonly` et `write` ; `multihome` est demandé pour les comptes ayant plusieurs domiciles.

Après une mise à jour HACS, redémarre Home Assistant si nécessaire. Ne supprime pas l'entrée d'intégration lors d'une mise à jour : elle contient l'autorisation OAuth.

## Installation manuelle

1. Télécharge le dépôt et décompresse-le.
2. Copie `custom_components/econergy` vers `/config/custom_components/econergy`.
3. Redémarre Home Assistant.
4. Ajoute **Econergy Cloud** depuis **Appareils et services** et termine l'autorisation OAuth.

## Programmation hebdomadaire

Sur la fiche de chaque radiateur, utilise l'action **Programmer le radiateur**. L'éditeur présente les jours de la semaine et permet de définir jusqu'à trois plages Confort par jour. En dehors de ces plages, le radiateur reste en Éco.

L'enregistrement du planning et l'activation du mode `PROG` sont deux opérations distinctes : après avoir sauvegardé les horaires, active le mode Programmation pour que le radiateur les applique.

## Données et limites connues

- L'API expose actuellement le mode `FROST` avec une consigne renvoyée de **7,5 °C**, alors que l'application Econergy affiche **7 °C**. La valeur de l'API est conservée telle quelle afin de ne pas masquer cet écart ; ce point doit être clarifié avec Econergy.
- La détection de fenêtre ouverte est exposée en lecture seule dans les routes actuellement documentées. Aucune commande documentée d'activation/désactivation n'est disponible à ce jour.
- Le téléchargement de la notice dépend de la présence d'un document côté Econergy. En cas de réponse `MANUAL_NOT_FOUND`, une notification informative est affichée plutôt qu'une erreur d'action.
- La consommation disponible correspond aux 15 dernières journées complètes et représente une estimation calculée à partir de la durée de chauffe et de la puissance nominale ; ce n'est pas un relevé Linky ni une mesure électrique directe. L'absence de donnée n'est pas assimilée à zéro.
- La température et les états sont les dernières valeurs publiées par les radiateurs. Une lecture API n'implique pas nécessairement une nouvelle remontée physique.
- Les scénarios, configurations avancées, gestion des membres et les commandes de présence/absence ne sont pas exposés par les routes publiques actuellement utilisées/documentées par cette version ; ils ne sont pas simulés par l'intégration.

## API utilisée

Base : `https://econergy-app.fr/api/smarthome/v1`

Routes utilisées par cette version :

- `GET /me`, `GET /homes`, `GET /homes/{homeId}/devices`
- `GET /devices/{deviceId}/status`, `PATCH /devices/{deviceId}`
- `GET /devices/{deviceId}/settings`, `PATCH /devices/{deviceId}/settings`
- `GET /devices/{deviceId}/program`, `PATCH /devices/{deviceId}/program`
- `GET /devices/{deviceId}/consumption`, `GET /devices/{deviceId}/manual`
- `POST /devices/{deviceId}/status-request`
- `POST /devices/{deviceId}/commands`, `GET /commands/{commandId}`

Documentation officielle : https://econergy-app.fr/lab/doc

## Sécurité et confidentialité

- OAuth 2.0 Authorization Code avec PKCE ; aucun `client_secret` n'est intégré.
- Les jetons sont stockés dans l'entrée Home Assistant et ne doivent jamais être publiés dans une issue ou un journal.
- Les diagnostics Home Assistant retirent les données d'authentification.
- Ne partage jamais de capture contenant des jetons, codes OAuth ou identifiants de compte.

## Signaler un problème

Ouvre une issue en indiquant la version Home Assistant, la version de l'intégration, le modèle du radiateur et les étapes pour reproduire le problème. **N'ajoute jamais de mot de passe, jeton OAuth, code d'autorisation ou identifiant privé.**

## Licence

MIT — voir [LICENSE](LICENSE).
