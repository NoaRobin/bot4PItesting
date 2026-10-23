# TIS Belges : envoi quotidien automatique

Chaque jour ouvré à 17h, l'outil :

1. copie `TISBE_PROD` et y met la date du jour dans `Paramètres!E4` ;
2. actualise la requête ODBC (`RMMPRD`) dans Excel ;
3. vérifie le résultat : dates, lignes, ISIN, doublons, montants ;
4. archive le fichier dans `…\3. TIS Belges\2026\TISBE_PROD_yyyymmdd.xlsx` ;
5. ajoute les lignes « R-co Valor » à l'historique ;
6. crée `TISBE_Rothschild & Co AM_File.xlsx` (onglet Paramètres supprimé) ;
7. envoie le mail à Six depuis `AMEUDataTeam@rmm-co.com`.

**Règle de sécurité : si une vérification échoue, rien n'est envoyé à Six.** Un mail
d'alerte part alors à l'adresse configurée. Si la donnée n'est pas prête, l'outil réessaie
toutes les 15 minutes jusqu'à 18h.

---

## 1. Prérequis sur le poste

| Élément | Comment vérifier |
|---|---|
| Windows avec **Excel** et **Outlook** (version bureau) | Déjà utilisés pour la procédure actuelle |
| DSN ODBC **RMMPRD** configuré | Voir étape 3 ci-dessous |
| Accès réseau ou VPN à la base | La requête RMMPRD doit fonctionner dans Excel |
| Boîte `AMEUDataTeam@rmm-co.com` ajoutée dans Outlook, avec le droit d'envoi | Voir étape 4 |
| Le poste reste **allumé et la session ouverte** à 17h | Voir section 5 |

## 2. Installation en un double-clic

Seul prérequis : **Python 3.9 ou plus récent**, installé depuis https://www.python.org/downloads/
en cochant **« Add python.exe to PATH »**.

Ensuite, double-cliquer sur **`Installer_TIS_Belges.bat`**. Ce fichier est autonome : il peut
être posé n'importe où (bureau, Téléchargements, ou même lancé depuis un zip). Il :

1. télécharge la dernière version de l'application depuis GitHub ;
2. l'installe dans `%LOCALAPPDATA%\TISBelges\app` (dossier local, hors OneDrive) ;
3. crée l'environnement Python et installe les composants (openpyxl, pywin32) ;
4. contrôle le poste (Excel, Outlook, base RMMPRD, dossiers) ;
5. programme l'envoi automatique si le contrôle ne signale aucun point bloquant ;
6. crée le raccourci **TIS Belges** sur le bureau et ouvre l'application.

**Mise à jour** : relancer le même fichier. Les réglages de `config.json` sont conservés et
les nouvelles options éventuelles y sont ajoutées.

Au premier lancement, Windows peut afficher « Windows a protégé votre ordinateur » (fichier
téléchargé) : cliquer sur **Informations complémentaires**, puis **Exécuter quand même**.

## 3. Réglages à vérifier une fois

**a. Si le contrôle du poste signale des points bloquants**, ils s'affichent dans la fenêtre
d'installation et dans l'application (bouton « Vérifier le poste »). L'envoi automatique ne
s'active qu'une fois ces points corrigés : l'activer ensuite depuis l'application.

**b. Vérifier le DSN RMMPRD**
1. Ouvrir « Sources de données ODBC » (taper `odbcad32` dans la recherche Windows).
2. Onglet « DSN utilisateur » ou « DSN système » : sélectionner **RMMPRD** → Configurer.
3. Tester la connexion. Cocher **« Se souvenir du mot de passe »** (ou équivalent) pour que
   l'outil se connecte sans invite.

**c. Lire le contrôle du poste.** Si le contrôle affiche des lignes **ECHEC**, le message indique ce qui manque. Une ligne
**ATTENTION** pour la boîte expéditrice signifie que l'envoi se fera « de la part de » la
boîte : il faut alors vérifier le droit d'envoi dans Outlook.

**d. Vérifier les chemins** dans `config.json` (`base_dir` en particulier) s'ils diffèrent
de la structure actuelle.

## 4. Première exécution : essai sans envoi à Six

Ouvrir un terminal dans le dossier `%LOCALAPPDATA%\TISBelges\app` (barre d'adresse de l'explorateur → `cmd`)
et lancer :

```
.venv\Scripts\python.exe tis_belges.py run --test --now
```

Mode test : **aucun envoi à Six, aucune écriture dans les dossiers réels**. Le mail part
seulement à l'adresse `operator_email`, avec le préfixe `[TEST]`. Le fichier de test est
dans `%LOCALAPPDATA%\TISBelges\test\`.

Pendant **3 à 5 jours ouvrés**, lancer ce test chaque jour et comparer le fichier produit
avec celui fait à la main. Quand les deux concordent, passer en production : la tâche
planifiée est déjà en place, rien d'autre à faire.

## 5. Fonctionnement en production

- La tâche « **TIS Belges - envoi quotidien** » se lance du lundi au vendredi à 17h.
- Pour qu'elle démarre, le poste doit être **allumé et la session ouverte** (le verrouillage
  de l'écran n'empêche pas l'exécution). Si le poste était éteint à 17h, la tâche démarre
  dès qu'il est rallumé ; une exécution tardive attend 17h si elle arrive avant.
- Éviter les redémarrages Windows Update entre 16h30 et 18h, et désactiver la mise en veille
  à cette heure.
- Les jours fériés se configurent dans `config.json` → `skip_dates`, au format `yyyymmdd`.

### Fichiers produits

| Fichier | Emplacement |
|---|---|
| Archive | `…\3. TIS Belges\2026\TISBE_PROD_yyyymmdd.xlsx` (dossier de l'année créé automatiquement) |
| Fichier envoyé | `…\3. TIS Belges\TISBE_Rothschild & Co AM_File.xlsx` (écrasé chaque jour) |
| Historique Valor | `…\3. TIS Belges\Historique TIS Belges\TIS BE_R-co Valor.xlsx` |
| Journaux | `%LOCALAPPDATA%\TISBelges\logs\tis_belges_yyyymmdd.log` |

## 6. Si un mail d'alerte arrive

| Message | Que faire |
|---|---|
| « Échec du … » avec « Délai d'actualisation dépassé » | Une boîte de dialogue est probablement restée ouverte, ou la base ne répond pas. Vérifier le DSN (étape 3b) et la connexion réseau/VPN, puis relancer (section 7). |
| « Fichier valide » absent, « Date de valeur liquidative différente » | Les données ne sont pas encore publiées pour la date. L'outil a réessayé jusqu'à 18h. Relancer plus tard avec `run --now`. |
| « strictement identique(s) en double » | Anomalie dans les données source. **Ne pas envoyer** sans vérification avec le support RMMPRD. |
| « Nombre de lignes … hors de la plage » | Vérifier la volumétrie. Si elle est normale, ajuster `min_rows` / `max_rows`. |
| « Devise(s) non prévue(s) » ou « Type de fiscalité non prévu » | Compléter `currencies` ou `types` dans `config.json` après vérification. |
| « Vérification requise » | Un envoi a pu partir sans confirmation. **Regarder dans Éléments envoyés de la boîte AMEUDataTeam avant toute relance.** |
| « Un envoi a été démarré sans confirmation » | Même conduite que ci-dessus. |
| « Aucune ligne « R-co Valor » » | Anomalie de données : vérifier le fichier avant de relancer. |

## Application TIS Belges

Le raccourci **TIS Belges** du bureau (créé par `Installer.bat`, ou `Lancer.bat`) ouvre l'application
dans sa propre fenêtre. Elle fonctionne entièrement en local : rien ne sort du poste.

- **Envoyer à Six** : lance l'envoi réel, après confirmation. Le bouton se désactive une fois
  l'envoi du jour effectué.
- **Essai sans envoi** : même déroulé, dans le dossier de test ; le mail part seulement vers
  l'adresse opérateur.
- **Vérifier le poste** : contrôle Excel, Outlook, la base et les dossiers, résultat en liste.
- **Parcours du fichier** : les cinq étapes numérotées (Actualisation, Archive, Valor, Fichier
  final, Six). Un bloc avance case par case jusqu'à l'étape où se trouve le fichier : jaune et
  clignotant pendant le traitement, rouge sur l'étape en échec, bleu quand tout est fait. Un tampon
  « ENVOYÉ 17:01 » ou « ÉCHEC » se pose sur l'étape concernée. L'heure de chaque étape s'affiche dessous.
- **Règle de la journée** : l'heure actuelle (bleu), l'heure de calcul et la fenêtre de reprise
  17h-18h (hachures jaunes).
- **Programmation** : changer l'heure de calcul et activer ou couper l'envoi automatique ;
  la tâche planifiée Windows est mise à jour immédiatement.
- **Console** : la sortie de l'opération en direct, copiable pour le support.

L'application respecte le réglage Windows « réduire les animations » et propose un thème clair
ou sombre (bouton en haut à droite).

## 7. Commandes utiles

Toutes à lancer depuis le dossier `%LOCALAPPDATA%\TISBelges\app` :

```
.venv\Scripts\python.exe tis_belges.py check                  contrôle de l'installation
.venv\Scripts\python.exe tis_belges.py run --now              relance immédiate, sans attendre 17h
.venv\Scripts\python.exe tis_belges.py run --date 20261016    relance pour une date donnée
.venv\Scripts\python.exe tis_belges.py run --test --now       essai sans envoi à Six
.venv\Scripts\python.exe tis_belges.py uninstall-task         arrêter la tâche planifiée
.venv\Scripts\python.exe tis_belges.py install-task           remettre la tâche planifiée
```

Une relance ne renvoie jamais un fichier déjà envoyé pour la même date. Elle reprend
simplement à l'étape qui n'était pas terminée.

## 8. Sécurité

- Aucun mot de passe n'est stocké dans les fichiers de l'outil. Les identifiants de la base
  restent dans le DSN ODBC de Windows.
- Les fichiers de travail et les journaux sont dans `%LOCALAPPDATA%\TISBelges`, pas dans le
  dossier partagé.
- L'envoi ne se fait qu'après validation complète, et une seule fois par date.

## 9. Structure du dossier

| Fichier | Rôle |
|---|---|
| `Installer_TIS_Belges.bat` | Téléchargement, installation et mise à jour en un double-clic |
| `Installer.bat` | Installation depuis un dossier déjà présent |
| `deploy.py` | Logique d'installation commune aux deux installeurs |
| `Lancer.bat` | Ouvre l'application TIS Belges |
| `dashboard/` | Application locale : serveur (`server.py`) et interface (`static/`) |
| `tis_belges.py` | Point d'entrée : commandes, orchestration, reprise |
| `rules.py` | Règles de validation et sélection Valor (sans dépendance Windows) |
| `office.py` | Pilotage d'Excel et d'Outlook (COM) |
| `system.py` | Verrou, DSN, tâche planifiée |
| `checks.py` | Contrôle de l'installation |
| `config.json` | Chemins, destinataires, seuils de validation |
| `tests/` | Tests : `python -m unittest discover -s tests` |
