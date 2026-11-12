# Exemples de tuiles Lovelace Econergy

Les exemples sont facultatifs et indépendants : ajoute uniquement les cartes qui t'intéressent. Ils sont fournis pour le radiateur Bureau et peuvent être adaptés aux autres radiateurs.

Ce dossier contient une tuile d'exemple pour le radiateur Bureau et les modèles communs utilisés par les tuiles des autres radiateurs.

## Contenu

- `button_card_templates.yaml` : modèles communs pour les boutons de modes et les commandes de température.
- `radiateur_bureau.yaml` : tuile de pilotage compacte pour `climate.econergy_bureau`.
- `radiateur_bureau_etat.yaml` : résumé des états en temps réel.
- `radiateur_bureau_consommation.yaml` : graphiques Recorder 30 jours (statistiques externes Econergy).
- `radiateur_bureau_consommation_15_jours.yaml` : graphique de la fenêtre API 15 jours (ApexCharts).
- `radiateur_bureau_reglages.yaml` : commandes et options du radiateur.
- `radiateur_bureau_diagnostic.yaml` : informations techniques et dernière communication.
- `radiateur_bureau_actions.yaml` : boutons d'action disponibles.
- `INSTALLATION.md` : procédure d'ajout au tableau de bord.

## Dépendance

Ces exemples utilisent la carte personnalisée **Button Card** (`custom:button-card`). Ils ne sont pas des cartes natives Home Assistant et ne sont pas ajoutés automatiquement au tableau de bord lors de l'installation de l'intégration.

Pour les trois autres radiateurs, duplique `radiateur_bureau.yaml` et remplace les identifiants `climate.econergy_bureau` et `binary_sensor.econergy_bureau_chauffage_en_cours` par ceux du radiateur concerné. Les modèles communs restent identiques.

Les identifiants de température, de chauffe, de consigne et les limites de consigne proviennent directement des entités Econergy. Aucun capteur de température supplémentaire n'est nécessaire pour la tuile de base.

Les autres cartes utilisent les entités du radiateur Bureau. Home Assistant conserve parfois les anciens `entity_id` après un changement de nom : vérifie les identifiants dans la fiche de l'appareil avant de coller les exemples.

Pour les graphiques 30 jours, les identifiants Recorder sont des statistiques externes `econergy:<device_id>_estimated_consumption` et `econergy:<device_id>_heating_duration`, pas des `sensor.*`. L'onglet Historique de la fenêtre « Plus d'informations » ne représente pas ces statistiques externes ; utilise la carte `statistics-graph` fournie.
