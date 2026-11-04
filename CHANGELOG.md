# Changelog

## 1.1.1

- Attente de 15 secondes après l'accusé de réception du diagnostic, pour laisser les radiateurs transmettre leur état avant la lecture cloud.
- Cadence réglée à 4 min 45 s après cette attente, soit environ 5 minutes entre deux demandes de diagnostic.
- Publication de l'heure de la dernière demande de diagnostic et du nombre de radiateurs ayant accusé réception dans les attributs du capteur.
- Le capteur conserve les nouvelles mesures même lorsque la température reste identique, afin de rendre visible la cadence des remontées.

## 1.1.0

- Demande de diagnostic réseau de tous les radiateurs avant chaque lecture groupée du domicile.
- Cadence fixe de cinq minutes, y compris lorsque tous les radiateurs sont en mode OFF.
- Validation de la session mobile avec `GET /auth?homeId=...` après connexion.
- Renouvellement de session puis nouvelle tentative unique du diagnostic si le serveur refuse la session.
- Un échec du diagnostic seul est journalisé sans empêcher les lectures habituelles du domicile.
- Les modes et consignes ne sont jamais modifiés par le diagnostic.
