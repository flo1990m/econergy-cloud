# Installation et mise à jour

## Avec HACS / Marketplace

1. Paramètres → Marketplace → Ajouter à partir d'un lien.
2. Saisir `flo1990m/econergy-cloud`, sélectionner **Intégration** et valider.
3. Installer **Econergy Cloud** puis redémarrer Home Assistant.
4. Ajouter l'intégration depuis Paramètres → Appareils et services et terminer l'autorisation OAuth.

Pour une mise à jour, utiliser le bouton de mise à jour HACS puis redémarrer Home Assistant si demandé. Ne supprime pas l'entrée Econergy : elle conserve l'autorisation OAuth.

## Installation manuelle

Copier `custom_components/econergy` vers `/config/custom_components/econergy`, puis redémarrer Home Assistant.

## Coexistence

Cette intégration utilise le domaine `econergy`. Elle ne remplace pas automatiquement l'intégration historique `econergy_cloud_v2` ; conserve cette dernière pendant les essais. Évite de commander le même radiateur simultanément depuis les deux intégrations.
