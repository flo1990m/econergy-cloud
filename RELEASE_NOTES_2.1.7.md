# Econergy Cloud 2.1.7 — Bêta

## Actualisation automatique des températures
- Rétablit les demandes de statut radio automatiques : les radiateurs ne sont plus dépendants d'une remontée spontanée du cloud.
- Les radiateurs sont interrogés séquentiellement et répartis sur un cycle cible de cinq minutes. Avec quatre radiateurs, une demande est lancée environ toutes les 75 secondes, ce qui donne environ une actualisation par radiateur toutes les cinq minutes.
- Respecte un délai minimal de 60 secondes entre deux demandes pour un même radiateur et conserve le bouton « Actualiser les infos » pour une demande manuelle.
- Conserve le dernier état le plus récent si la liste générale du cloud renvoie ensuite un instantané plus ancien.

## Nettoyage des anciens appareils
- Ajoute la prise en charge de la suppression des appareils Econergy dans le registre Home Assistant.
- La suppression est autorisée uniquement lorsque l'identifiant de l'appareil n'est plus présent dans l'inventaire actuel du domicile Econergy.
- Les appareils encore présents dans le compte restent protégés contre la suppression.

## Fiabilité
- Le cycle d'actualisation automatique est arrêté proprement lors du déchargement ou du rechargement de l'intégration.
- Aucun changement d'autorisation OAuth, d'identifiants d'entités, de scripts ou de services existants.
