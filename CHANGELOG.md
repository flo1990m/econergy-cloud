# Changelog

## 1.1.0

- Demande de diagnostic réseau de tous les radiateurs avant chaque lecture groupée du domicile.
- Cadence fixe de cinq minutes, y compris lorsque tous les radiateurs sont en mode OFF.
- Validation de la session mobile avec `GET /auth?homeId=...` après connexion.
- Renouvellement de session puis nouvelle tentative unique du diagnostic si le serveur refuse la session.
- Un échec du diagnostic seul est journalisé sans empêcher les lectures habituelles du domicile.
- Les modes et consignes ne sont jamais modifiés par le diagnostic.
