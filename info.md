Intégration communautaire Home Assistant pour les radiateurs Econergy / Carrera via l'API officielle Econergy Lab. Elle fournit le pilotage du chauffage, l'actualisation automatique des températures, la programmation hebdomadaire, les réglages, les capteurs de diagnostic, l'archivage des consommations journalières et la suppression sécurisée des anciens appareils, avec des exemples Lovelace facultatifs.

## Historique et graphiques de consommation

Les capteurs « Consommation estimée (dernier jour) » et « Durée de chauffe (dernier jour) » exposent uniquement la dernière journée complète renvoyée par l'API Econergy. Leur valeur est remplacée lors de la prochaine actualisation : ils ne constituent pas un historique journalier.

Les graphiques statistiques automatiquement suggérés par Home Assistant à partir de ces capteurs utilisent donc les statistiques de ces entités, et non l'historique journalier complet importé par l'intégration. Ils peuvent rester à 0 lorsque le dernier relevé quotidien est nul et ne doivent pas être utilisés pour représenter la consommation de chaque journée.

Pour afficher l'historique quotidien, ajoutez une carte **Graphique des statistiques** en mode YAML et utilisez l'identifiant de statistique externe Econergy (préfixe `econergy:`). Exemple pour le Bureau :

```yaml
type: statistics-graph
title: Consommation estimée — 30 derniers jours
entities:
  - econergy:68c5597e5cb480c6cc800d66_estimated_consumption
period: day
days_to_show: 30
chart_type: bar
stat_types:
  - state
hide_legend: true
```

Pour la durée de chauffe, utilisez `econergy:68c5597e5cb480c6cc800d66_heating_duration`. Remplacez l'identifiant du radiateur par celui de votre appareil. Ces statistiques externes sont distinctes des entités `sensor.*` et se consultent dans **Paramètres → Outils de développement → Statistiques**.
