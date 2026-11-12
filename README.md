# Econergy Cloud — Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://www.hacs.xyz/)
[![Version bêta](https://img.shields.io/badge/version-2.1.5--b%C3%AAta-orange.svg)](https://github.com/flo1990m/econergy-cloud/releases)

Intégration communautaire Home Assistant pour les radiateurs Econergy / Carrera, basée sur l'API officielle Econergy Lab.

> **Version bêta :** l'intégration est encore en développement et peut contenir des défauts. Projet communautaire indépendant, non affilié à Econergy et non officiellement pris en charge par le fabricant. Elle dépend de l'API cloud Econergy ; ses fonctions peuvent évoluer avec l'API.

## Fonctionnalités

- Découverte des domiciles autorisés par le compte Econergy et des radiateurs associés.
- Entité `climate` : arrêt, hors-gel, manuel et programmation ; température ambiante et consigne.
- Programmation hebdomadaire avec un éditeur en français : sept jours, jusqu'à trois plages Confort par jour, consignes Éco/Confort, copie des réglages entre jours et activation explicite du mode Programmation.
- Réglages : butée de température max, protection enfant et verrouillage du clavier.
- Capteurs : température ambiante, puissance nominale, firmware, date d'installation, dernière communication, dernière remontée d'état, régime appliqué, état de chauffe, détection de fenêtre ouverte et consommation estimée.
- Actions : actualisation à la demande, actualisation de la consommation, renommage du radiateur et récupération de la notice lorsqu'elle existe.
- Archivage durable des relevés journaliers de consommation estimée et de durée de chauffe, avec import dans les statistiques long terme de Home Assistant.
- Suivi des commandes avec attente de leur confirmation par l'API ; le dernier statut est conservé après un redémarrage de Home Assistant et aucune commande incertaine n'est renvoyée automatiquement.
- Régime appliqué déterminé à partir de l'état du radiateur et, en mode Programmation, de la consigne et du créneau hebdomadaire en cours.
- Authentification OAuth 2.0 avec PKCE ; aucun mot de passe Econergy ni jeton à copier dans YAML.
- Exemples Lovelace facultatifs : tuile de pilotage de base, état détaillé, réglages, diagnostic, actions, graphique des 15 derniers jours et statistiques sur 30 jours.

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

Sur la fiche de chaque radiateur, utilise l'action **Programmes du radiateur**. L'éditeur présente les jours de la semaine et permet de définir jusqu'à trois plages Confort par jour. En dehors de ces plages, le radiateur reste en Éco.

L'enregistrement du planning et l'activation du mode `PROG` sont deux opérations distinctes : après avoir sauvegardé les horaires, active le mode Programmation pour que le radiateur les applique.

## Exemples Lovelace facultatifs

Le dossier `custom_components/econergy/examples/lovelace` contient plusieurs cartes indépendantes : tu peux en ajouter seulement certaines à ton tableau de bord.

- `radiateur_bureau.yaml` : tuile de pilotage compacte avec l'indicateur de chauffe réel (modèle de base, nécessite `custom:button-card`).
- `radiateur_bureau_etat.yaml` : état, température, régime, chauffe, fenêtre et ventilateur.
- `radiateur_bureau_consommation.yaml` : graphiques Recorder sur 30 jours à partir des statistiques long terme Econergy.
- `radiateur_bureau_consommation_15_jours.yaml` : graphique API des 15 derniers jours, avec les dates au format JJ/MM (nécessite `custom:apexcharts-card`).
- `radiateur_bureau_reglages.yaml` : consignes Éco/Confort, butée max, protection enfant et verrouillage du clavier.
- `radiateur_bureau_diagnostic.yaml` : firmware, puissance, dernière communication et statut de commande.
- `radiateur_bureau_actions.yaml` : actualisation, programmation et notice.

Les exemples sont fournis pour `climate.econergy_bureau`. Les identifiants des radiateurs et certains `entity_id` peuvent différer selon le nom et l'historique de ton installation : vérifie-les dans **Paramètres → Appareils et services → Econergy → Bureau** avant de coller une carte.

**Historique de consommation :** les relevés du cloud sont importés comme statistiques long terme externes, avec des identifiants de la forme `econergy:<identifiant_du_radiateur>_estimated_consumption` et `econergy:<identifiant_du_radiateur>_heating_duration`. La carte `statistics-graph` doit utiliser ces identifiants de statistiques, pas les entités `sensor.*` qui n'exposent que la dernière journée. L'onglet Historique natif d'une entité Home Assistant montre les changements d'état de cette entité ; il ne présente pas les statistiques externes. Le graphique 30 jours affiche les jours disponibles (15 au premier import), puis s'enrichit au fil de l'archivage.

## Données et limites connues

- L'API expose actuellement le mode `FROST` avec une consigne renvoyée de **7,5 °C**, alors que l'application Econergy affiche **7 °C**. La valeur de l'API est conservée telle quelle afin de ne pas masquer cet écart ; ce point doit être clarifié avec Econergy.
- La détection de fenêtre ouverte est exposée en lecture seule dans les routes actuellement documentées. Aucune commande documentée d'activation/désactivation n'est disponible à ce jour.
- Le téléchargement de la notice dépend de la présence d'un document côté Econergy. En cas de réponse `MANUAL_NOT_FOUND`, une notification informative est affichée plutôt qu'une erreur d'action.
- L'API Econergy ne retourne que les 15 dernières journées complètes, mais l'intégration les archive durablement dans Home Assistant et alimente ses statistiques long terme. Les valeurs restent des estimations calculées à partir de la durée de chauffe et de la puissance nominale ; ce ne sont pas des relevés Linky ni des mesures électriques directes. Lorsqu'une journée est renvoyée sans mesure (`null`), la tuile affiche `0` par convention, tandis que l'archive conserve l'absence de donnée.
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
