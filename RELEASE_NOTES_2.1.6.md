# Econergy Cloud 2.1.6 — Bêta

## Nouveautés

### Actualisation centralisée
- Remplace les boutons séparés « Actualiser l'état » et « Actualiser la consommation » par une seule action « Actualiser les infos ».
- La nouvelle action demande une remontée d'état au radiateur, puis actualise les consommations journalières et réimporte les statistiques dans le Recorder.
- Une erreur sur une opération ne bloque pas la tentative de l'autre ; les résultats et erreurs sont exposés dans les attributs du bouton.

### Consommation journalière
- Remplace le graphique 15 jours basé sur ApexCharts par deux cartes natives Home Assistant `statistics-graph` : énergie journalière et durée de chauffe journalière.
- Les exemples 15 et 30 jours exploitent les statistiques long terme Econergy du Recorder, et non le capteur de dernière journée ni une série horaire.
- L'intégration continue d'utiliser le relevé API des 15 dernières journées complètes. Aucun endpoint de consommation par tranche de 10 minutes n'est ajouté sans route API documentée et vérifiée.

### Programmation
- La page « Programmes du radiateur » ne contient plus que l'éditeur hebdomadaire.
- Suppression du bloc et du bouton « Activer la programmation » ; le passage en mode Programmation reste disponible depuis le pilotage habituel du radiateur.
- Passage au vouvoiement dans les textes de la page et de l'éditeur.
- Harmonisation du texte d'information : « 3 créneaux maximum · pas de 10 minutes · pas de chevauchement. Le radiateur doit être en mode Programmation pour suivre les horaires. »

### Notice PDF
- Conserve la route `GET /devices/{deviceId}/manual?lang=fr` et le traitement du lien HTTPS temporaire retourné par l'API.
- Ne transforme plus `MANUAL_NOT_FOUND` en affirmation locale selon laquelle aucune notice n'existe. Les erreurs de l'API et les réponses sans URL PDF attendue sont désormais remontées explicitement.

## Compatibilité
- Aucun changement d'autorisation OAuth ni de commande de pilotage.
- L'identifiant unique du bouton historique « Actualiser l'état » est conservé pour préserver son `entity_id` existant ; son nouveau nom est « Actualiser les infos ».
- Les cartes de consommation restent optionnelles et utilisent les identifiants de statistiques Recorder externes déjà créés.
- Les tests finaux d'interface et de récupération de notices doivent être effectués après installation sur Home Assistant.
