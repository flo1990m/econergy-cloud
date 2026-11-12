TUILES LOVELACE ECONERGY — INSTALLATION
=======================================

Dépendance
----------
Installer la carte personnalisée Button Card (custom:button-card) avec HACS.

1. Modèles communs
------------------
Dans le tableau de bord : menu ⋮ > Modifier le tableau de bord > Éditeur de configuration brute.
Copier le contenu de button_card_templates.yaml à la racine, au même niveau que "views:".
Si "button_card_templates:" existe déjà, fusionner les deux modèles dans cette section : ne pas créer une deuxième clé.

2. Tuile du Bureau
------------------
Ajouter le contenu de radiateur_bureau.yaml comme carte manuelle dans la vue souhaitée.

Entités utilisées
-----------------
- climate.econergy_bureau
- binary_sensor.econergy_bureau_chauffage_en_cours

Fonctionnement
--------------
- Le rond du radiateur est gris lorsque le radiateur est arrêté.
- Il passe en orange lorsqu'il est actif mais ne chauffe pas.
- L'icône de chauffe est affichée lorsque le binaire Econergy "Chauffage en cours" est actif.
- Le mode Hors gel reste identifié comme un mode actif, même si le climate expose hvac_mode=off.
- La température ambiante est lue depuis l'attribut current_temperature du climate.
- Les boutons +/- utilisent min_temp, max_temp et econergy_manual_setpoint_c fournis par l'intégration.
- Les modes Hors gel, Manuel et Programmation utilisent climate.set_preset_mode.

Pour les autres radiateurs
--------------------------
Dupliquer radiateur_bureau.yaml, puis remplacer les deux identifiants d'entité par ceux du radiateur visé. Les modèles button-card sont communs aux quatre tuiles.

Important
---------
Ces exemples utilisent custom:button-card : ils ne sont pas des cartes natives intégrées automatiquement par Home Assistant.
Ils sont livrés dans l'archive Econergy à titre d'exemples de tableau de bord.
