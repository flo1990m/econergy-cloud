# Changelog

## 2.1.1 — 11 novembre 2026

### Correctifs
- Corrige la classe d'état des capteurs de consommation énergétique : les consommations journalières utilisent désormais `total`, tandis que la durée de chauffe conserve `measurement`.
- Améliore le capteur « Régime appliqué » : interprète le mode réel du radiateur et, en mode programmation, la consigne et le créneau hebdomadaire courant lorsque l'API ne fournit pas `setpointKind`.
- Conserve le statut de la dernière commande dans le stockage Home Assistant afin de le retrouver après un redémarrage.
- Affiche une notification informative lorsque l'API renvoie `MANUAL_NOT_FOUND`, sans faire échouer l'action du bouton.

### Compatibilité
- Aucun changement de configuration OAuth requis.
- L'entrée Econergy existante et ses appareils sont conservés lors de la mise à jour.
