# Econergy Cloud for Home Assistant

Intégration communautaire **non officielle** pour radiateurs Econergy / Carrera Wi-Fi.

## Fonctionnalités

- Configuration par adresse e-mail et mot de passe Econergy, depuis l’interface de Home Assistant.
- Découverte des radiateurs du foyer.
- Température ambiante et contrôle via une entité `climate` par radiateur.
- Modes **Arrêt**, **Hors gel (7 °C)**, **Manuel** et **Programmation**.
- Consigne active calculée à partir des plages de programmation (Éco/Confort), horaires locaux.
- Actualisation groupée toutes les **5 minutes dès qu’au moins un radiateur du foyer n’est pas à l’arrêt**, et toutes les **15 minutes lorsque tous les radiateurs sont à l’arrêt**. La fréquence s’applique à toutes les données du foyer, car l’API les renvoie dans une même réponse.
- Écritures protégées : lecture préalable des 13 paramètres et 21 entrées de programme, refus d’écrire en cas de données incomplètes, et contrôle après écriture.

## Installation HACS (dépôt personnalisé)

Dans HACS, ajouter ce dépôt GitHub comme **dépôt personnalisé** de catégorie *Intégration*, puis installer **Econergy Cloud**, redémarrer Home Assistant et ajouter l’intégration via **Paramètres → Appareils et services**.

## Installation manuelle

Copier `custom_components/econergy_cloud` dans le dossier `/config/custom_components/` et redémarrer Home Assistant.

## Utilisation

Chaque radiateur expose une entité `climate` et un capteur de température ambiante. La consigne modifiée depuis Home Assistant bascule en mode Manuel. Les modes Hors gel et Programmation conservent les réglages Eco/Confort existants.

## Notes et précautions

- Ce projet n'est **ni développé ni approuvé par Econergy/Carrera**.
- Requiert le service cloud du fabricant ; l’API peut évoluer ou être indisponible.
- Les identifiants sont stockés dans la configuration de Home Assistant ; **ne jamais les ajouter à un dépôt GitHub**.
- La configuration complète de chaque radiateur doit être présente avant toute commande : si elle est incomplète, l'intégration bloque les écritures.
- Après une modification de consigne, vérifier la bonne prise en compte sur les premiers tests.
- Le CRC est conservé tel quel ; son algorithme n'est pas connu.
- Ne permet pas encore de modifier les horaires depuis Home Assistant.

## Support

Ouvrir un ticket dans l’onglet Issues du dépôt en précisant la version et les journaux **anonymisés** (jamais de jeton, e-mail ou mot de passe).

## Licence

Voir le fichier `LICENSE`.
