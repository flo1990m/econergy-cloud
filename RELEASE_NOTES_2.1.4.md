## Nouveautés

### Tuiles Lovelace Econergy
- Ajout d'exemples de tuiles de pilotage des radiateurs dans l'archive, avec modèles réutilisables `button_card_templates`.
- Affichage de trois états : radiateur arrêté, radiateur actif sans chauffe et chauffe effective.
- Le mode Hors gel reste visuellement reconnu même si `hvac_mode` vaut `off`.
- Température ambiante et limites de consigne directement lues depuis l'entité `climate`.
- Instructions fournies pour dupliquer la tuile sur les autres radiateurs.

### Historique de consommation
- Conservation de l'archivage durable des consommations estimées et durées de chauffe introduit en 2.1.3.
- Import des données disponibles dans les statistiques long terme Home Assistant.

### Compatibilité
- Aucun changement d'autorisation OAuth, de commandes API ni d'identifiants uniques.
- Les exemples Lovelace requièrent `custom:button-card` et doivent être ajoutés manuellement au tableau de bord.

**Statut :** version bêta.
