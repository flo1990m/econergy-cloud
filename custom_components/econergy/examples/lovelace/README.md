# Exemples de tuiles Lovelace Econergy

Les exemples sont facultatifs et indépendants : ajoute uniquement les cartes qui t'intéressent. Ils sont fournis pour le radiateur Bureau et peuvent être adaptés aux autres radiateurs.

Il contient la tuile de pilotage de base et ses modèles communs, ainsi que plusieurs exemples facultatifs.

## Contenu

- `button_card_templates.yaml` : modèles communs pour les boutons de modes et les commandes de température.
- `radiateur_bureau.yaml` : tuile de pilotage compacte pour `climate.econergy_bureau`.
- `radiateur_bureau_etat.yaml` : résumé des états en temps réel.
- `radiateur_bureau_consommation.yaml` : graphiques Recorder 30 jours (statistiques externes Econergy).
- `radiateur_bureau_consommation_15_jours.yaml` : graphiques journaliers Recorder sur 15 jours (énergie et durée de chauffe).
- `radiateur_bureau_reglages.yaml` : commandes et options du radiateur.
- `radiateur_bureau_diagnostic.yaml` : informations techniques et dernière communication.
- `radiateur_bureau_actions.yaml` : boutons d'action disponibles.
- `INSTALLATION.md` : procédure d'ajout au tableau de bord.

## Dépendance

Seule la tuile de pilotage de base (`radiateur_bureau.yaml`) utilise **Button Card** (`custom:button-card`) et les modèles du fichier compagnon. Les cartes d'état, de réglages, de diagnostic et d'actions sont natives Home Assistant. Les graphiques de consommation utilisent les statistiques Recorder journalières et ne nécessitent pas ApexCharts. Aucune de ces cartes n'est ajoutée automatiquement au tableau de bord lors de l'installation de l'intégration.

Pour les trois autres radiateurs, duplique `radiateur_bureau.yaml` et remplace les identifiants `climate.econergy_bureau` et `binary_sensor.econergy_bureau_chauffage_en_cours` par ceux du radiateur concerné. Les modèles communs restent identiques.

Les identifiants de température, de chauffe, de consigne et les limites de consigne proviennent directement des entités Econergy. Aucun capteur de température supplémentaire n'est nécessaire pour la tuile de base.

Les autres cartes utilisent les entités du radiateur Bureau. Home Assistant conserve parfois les anciens `entity_id` après un changement de nom : vérifie les identifiants dans la fiche de l'appareil avant de coller les exemples.

Pour les graphiques 15 et 30 jours, les identifiants Recorder sont des statistiques externes `econergy:<device_id>_estimated_consumption` et `econergy:<device_id>_heating_duration`, pas des `sensor.*`. L'onglet Historique de la fenêtre « Plus d'informations » ne représente pas ces statistiques externes ; utilise la carte `statistics-graph` fournie.


## Important — graphiques de consommation

Les capteurs `sensor.*_consommation_estimee_dernier_jour` et `sensor.*_duree_de_chauffe_dernier_jour` exposent le dernier relevé quotidien reçu, pas l'historique des journées. Les graphiques automatiquement suggérés par Home Assistant à partir de ces capteurs ne constituent donc pas un historique journalier : ils peuvent rester à 0 lorsque le dernier relevé est nul.

Pour l'historique par journée, ajoutez manuellement une carte `statistics-graph` et renseignez un identifiant de statistique externe Econergy sous la forme `econergy:<device_id>_estimated_consumption` ou `econergy:<device_id>_heating_duration`. Utilisez `period: day` et `stat_types: [state]`. Le fichier `radiateur_bureau_consommation.yaml` fournit un exemple complet prêt à adapter. La carte doit être ajoutée via l'éditeur YAML (**Par carte**), et non créée à partir de la suggestion automatique **Par entité** du capteur de dernière journée.
