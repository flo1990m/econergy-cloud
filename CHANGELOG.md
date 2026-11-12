# Changelog

## 2.1.6 — bêta — 12 novembre 2026

- Fusionne les demandes d'actualisation de l'état et de la consommation dans l'action « Actualiser les infos », en conservant l'identifiant unique de l'ancien bouton d'état.
- Remplace le graphique 15 jours basé sur ApexCharts par des graphiques natifs journaliers Recorder pour l'énergie estimée et la durée de chauffe.
- Simplifie la page « Programmes du radiateur » : retrait de l'activation depuis cette page et passage au vouvoiement dans l'éditeur.
- Harmonise le texte d'information sur les créneaux et le mode Programmation.
- Conserve la route officielle de récupération de notice et remonte les erreurs API sans affirmer à tort que le PDF est absent.

## 2.1.5 — bêta — 12 novembre 2026

- Ajoute l'état natif du chauffage réellement actif dans la fenêtre de thermostat Home Assistant.
- Ajoute des exemples Lovelace indépendants : état, consommation, réglages, diagnostic et actions ; le graphique API 15 jours affiche les dates en JJ/MM.
- Retire le graphique de consommation de la page de programmation, désormais exclusivement consacrée aux programmes du radiateur.
- Corrige les libellés des actions et réglages, traduit les statuts de commande en français et harmonise l'icône d'actualisation de la consommation.
- Fournit une carte `statistics-graph` configurée avec les identifiants de statistiques long terme Econergy pour afficher les relevés archivés sur 30 jours.


## 2.1.4 — bêta — 12 novembre 2026

- Ajoute des exemples Lovelace de tuiles Econergy et des modèles réutilisables pour piloter les radiateurs avec l'état de chauffe réel.
- Aucun changement de l'API, des commandes, de l'autorisation OAuth ou des identifiants uniques.

## 2.1.1 — 11 novembre 2026

### Correctifs
- Corrige la classe d'état des capteurs de consommation énergétique : les consommations journalières utilisent désormais `total`, tandis que la durée de chauffe conserve `measurement`.
- Améliore le capteur « Régime appliqué » : interprète le mode réel du radiateur et, en mode programmation, la consigne et le créneau hebdomadaire courant lorsque l'API ne fournit pas `setpointKind`.
- Conserve le statut de la dernière commande dans le stockage Home Assistant afin de le retrouver après un redémarrage.
- Affiche une notification informative lorsque l'API renvoie `MANUAL_NOT_FOUND`, sans faire échouer l'action du bouton.

### Compatibilité
- Aucun changement de configuration OAuth requis.
- L'entrée Econergy existante et ses appareils sont conservés lors de la mise à jour.
