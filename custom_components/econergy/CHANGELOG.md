# Changelog

## 2.1.4 — bêta — 12 novembre 2026

### Tuiles Lovelace
- Ajoute à l'archive de l'intégration des exemples de tuiles Lovelace Econergy, avec les modèles `button_card_templates` réutilisables et une tuile complète pour le Bureau.
- Distingue visuellement les états arrêté, actif sans chauffe et chauffe effective à partir du capteur de fonctionnement publié par l'intégration.
- Conserve un affichage cohérent du mode Hors gel, même lorsque le climate expose `hvac_mode: off`.
- Lit la température ambiante directement depuis l'entité `climate` et adapte les boutons de consigne aux limites réelles `min_temp` et `max_temp`.
- Documente l'installation et la duplication de la tuile pour les autres radiateurs.

### Compatibilité
- Aucun changement des commandes API, de l'autorisation OAuth ou des identifiants uniques des entités.
- Les exemples Lovelace nécessitent la carte personnalisée `custom:button-card` et sont ajoutés manuellement au tableau de bord.

## 2.1.3 — bêta — 12 novembre 2026

### Tuile Lovelace
- Modernise l'exemple de tuile de pilotage des radiateurs en conservant son apparence et ses commandes, avec une structure factorisée et réutilisable via `button_card_templates`.
- Exploite les états Econergy pour distinguer visuellement le radiateur arrêté, allumé sans chauffe et en chauffe effective.
- Utilise directement la température ambiante publiée par l'entité `climate` et adapte les boutons de consigne aux limites `min_temp` et `max_temp` exposées par le radiateur.
- Préserve la dernière consigne manuelle lors des transitions entre les modes arrêt, hors-gel et chauffage.


### Consommation et historique
- Les capteurs de consommation estimée et de durée de chauffe exploitent désormais les relevés disponibles sans se limiter à la dernière journée de la fenêtre API.
- Affiche 0 dans les tuiles lorsqu'une journée existe mais que l'API renvoie `null`, sans transformer cette absence de mesure en zéro dans les données archivées.
- Fusionne chaque nouvelle fenêtre de 15 jours avec l'historique local permanent : les journées antérieures sont conservées et une valeur `null` ne peut pas effacer une mesure déjà connue.
- Enregistre l'archive dans le stockage persistant Home Assistant et importe les valeurs quotidiennes disponibles dans les statistiques long terme du Recorder, pour l'énergie estimée et la durée de chauffe.

### Compatibilité
- Aucune modification de l'autorisation OAuth ni de la configuration des radiateurs.
- Les identifiants uniques des entités existantes sont conservés.

## 2.1.2 — bêta — 12 novembre 2026

### Correctifs
- Corrige le cycle de vie de l'écouteur ponctuel `homeassistant_started` : il n'est plus désinscrit une seconde fois lors du déchargement de l'intégration.
- Conserve une désinscription explicite si l'intégration est déchargée avant le démarrage complet de Home Assistant.

### Compatibilité
- Version bêta ; aucune modification de l'autorisation OAuth ni de la configuration des appareils.

## 2.1.1 — bêta — 11 novembre 2026

### Correctifs
- Corrige la classe d'état des capteurs de consommation énergétique : les consommations journalières utilisent désormais `total`, tandis que la durée de chauffe conserve `measurement`.
- Améliore le capteur « Régime appliqué » : interprète le mode réel du radiateur et, en mode programmation, la consigne et le créneau hebdomadaire courant lorsque l'API ne fournit pas `setpointKind`.
- Conserve le statut de la dernière commande dans le stockage Home Assistant afin de le retrouver après un redémarrage. Affiche « Aucune commande enregistrée » lorsqu'aucune commande n'a encore été suivie.
- Affiche une notification informative lorsque l'API renvoie `MANUAL_NOT_FOUND`, sans faire échouer l'action du bouton.

### Compatibilité
- Aucun changement de configuration OAuth requis.
- L'entrée Econergy existante et ses appareils sont conservés lors de la mise à jour.

# Econergy Cloud — historique des versions

## 2.1.0 — bêta — couverture de l'API publique Econergy Lab

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
