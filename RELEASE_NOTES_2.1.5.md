## Nouveautés

### Thermostat natif
- Le panneau thermostat Home Assistant indique si le radiateur chauffe réellement ou s'il est simplement allumé au repos, via `hvac_action`.

### Tuiles Lovelace facultatives
- Ajout de cartes indépendantes pour l'état, les consommations, les réglages, le diagnostic et les actions.
- Ajout d'un graphique Recorder sur 30 jours utilisant les identifiants de statistiques long terme propres à chaque radiateur. Le bouton « Actualiser la consommation » relance l'import de l'archive locale dans Recorder.
- Ajout d'un graphique API sur les 15 derniers jours avec les dates au format JJ/MM.
- La tuile de pilotage de base reste compacte et conserve l'indicateur visuel de chauffe.

### Page de programmation et libellés
- La page est renommée « Programmes du radiateur » et ne contient plus les consommations : elle reste exclusivement consacrée aux horaires et à l'activation du mode Programmation.
- Le bouton « Actualiser la consommation » utilise désormais la même icône d'actualisation que « Actualiser l'état ».
- Les statuts de commande sont traduits en français ; le code API reste disponible dans les attributs.
- Le réglage est renommé « Butée de température max » et le capteur « Détection fenêtre ouverte » (les états Ouvert/Fermé restent inchangés).

**Statut :** version bêta.
