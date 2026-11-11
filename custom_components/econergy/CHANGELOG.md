# Econergy Cloud — historique des versions

## 2.1.0 — couverture de l'API publique Econergy Lab

- Ajout des routes documentées `GET/PATCH /devices/{deviceId}/settings` : butée maximale, verrouillage clavier et protection enfant.
- Ajout de `GET /devices/{deviceId}/consumption` : 15 jours de durée de chauffe et d'énergie estimée, cache quotidien.
- Ajout de `GET /devices/{deviceId}/manual` : récupération à la demande d'un lien PDF temporaire.
- Ajout des états runtime `heating`, `windowOpen`, `fanBoost`, `setpointKind`.
- Mise en cohérence avec l’API 1.9 : manuel à partir de 13,5 °C, hors-gel affiché à 7,5 °C et consigne maximale respectée dans l’entité climate et l’éditeur.
- Ajout de `GET /devices/{deviceId}/status` et conservation des dates de fraîcheur d'état.
- Boutons d'action sur la fiche du radiateur : programmer, actualiser l'état, télécharger la notice.
- Retrait du lien générique « Visiter » ; le bouton « Programmer le radiateur » ouvre directement l'éditeur hebdomadaire.
- Renommage conforme à la limite API de 50 caractères ; champ vide pour revenir au nom calculé.
- Les écritures de réglages utilisent exclusivement les routes et paramètres publiés par Econergy et sont vérifiées par relecture.
- La lecture automatique ne réveille plus les radiateurs : la demande radio est réservée au bouton d'actualisation et à la vérification des commandes.

## 2.0.0b2 — bêta locale précédente

- Première version OAuth locale avec éditeur de programme hebdomadaire.
- Pilotage des radiateurs, demande d'actualisation d'état et renommage.
