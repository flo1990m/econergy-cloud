# Exemples de tuiles Lovelace Econergy

Ce dossier contient une tuile d'exemple pour le radiateur Bureau et les modèles communs utilisés par les tuiles des autres radiateurs.

## Contenu

- `button_card_templates.yaml` : modèles communs pour les boutons de modes et les commandes de température.
- `radiateur_bureau.yaml` : exemple complet pour `climate.econergy_bureau`.
- `INSTALLATION.md` : procédure d'ajout au tableau de bord.

## Dépendance

Ces exemples utilisent la carte personnalisée **Button Card** (`custom:button-card`). Ils ne sont pas des cartes natives Home Assistant et ne sont pas ajoutés automatiquement au tableau de bord lors de l'installation de l'intégration.

Pour les trois autres radiateurs, duplique `radiateur_bureau.yaml` et remplace les identifiants `climate.econergy_bureau` et `binary_sensor.econergy_bureau_chauffage_en_cours` par ceux du radiateur concerné. Les modèles communs restent identiques.

Les identifiants de température, de chauffe, de consigne et les limites de consigne proviennent directement des entités Econergy. Aucun capteur de température supplémentaire n'est nécessaire pour cette tuile.
