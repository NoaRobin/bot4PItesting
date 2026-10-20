# Extraction des questions d'un questionnaire web

Outil qui parcourt un questionnaire en ligne et enregistre **toutes** ses questions : libellés, consignes, listes déroulantes avec leurs options, et **questions conditionnelles** (celles qui n'apparaissent qu'après un certain choix).

Il clique uniquement sur les rubriques bleues de la colonne de gauche et sur les réponses des questions. Il ne soumet jamais le formulaire et ne saisit aucun texte.

---

## 1. Installation (Windows)

Il faut Python 3.10 ou plus récent.

```bat
py -m pip install -r questionnaire\requirements.txt
```

Le script utilise **Microsoft Edge**, déjà installé sur Windows : rien d'autre à télécharger.

Si Edge n'est pas utilisable, installez le navigateur fourni avec Playwright et ajoutez `--navigateur chromium` :

```bat
py -m playwright install chromium
```

## 2. Lancement

```bat
cd questionnaire
py extracteur.py --url "https://adresse-du-questionnaire"
```

Déroulement :

1. Une fenêtre de navigateur s'ouvre. Connectez-vous et allez sur le questionnaire. **Appuyez sur Entrée** dans le terminal.
2. Le script affiche la liste des rubriques bleues (`GEA - …`, `GEK - …`, `RB1 - …`).
3. Pour chaque rubrique, il affiche une invite :
   - **Entrée** : traiter cette rubrique (le script clique lui-même sur la rubrique bleue) ;
   - **s** : passer cette rubrique ;
   - **a** : traiter toutes les rubriques restantes sans demander ;
   - **q** : quitter (les résultats déjà lus sont gardés).

Le profil du navigateur est conservé dans `questionnaire\profil_navigateur` : la connexion reste valable d'une exécution à l'autre.

### Options utiles

| Option | Rôle | Défaut |
|---|---|---|
| `--url` | page d'ouverture | aucune (navigation manuelle) |
| `--cdp http://localhost:9222` | se connecter à un navigateur déjà ouvert (lancé avec `--remote-debugging-port=9222`) | — |
| `--navigateur msedge\|chrome\|chromium` | navigateur à utiliser | `msedge` |
| `--sans-sondage` | ne pas tester les listes : extraction simple et rapide | tests activés |
| `--profondeur N` | nombre maximum de réponses enchaînées testées | 3 |
| `--max-tests N` | nombre maximum d'essais par rubrique | 400 |
| `--pause MS` | attente après chaque réponse testée | 300 |
| `--calme MS` | silence du DOM exigé avant lecture | 250 |

Si le site est lent et que des questions apparaissent avec retard, augmentez `--pause` (par exemple `--pause 1000`).

## 3. Résultats

Chaque exécution crée un dossier `questionnaire\sortie\AAAA-MM-JJ_HH-MM-SS\` :

| Fichier | Contenu |
|---|---|
| `questionnaire.txt` | lecture et copie vers Word : une question par bloc, avec options et conditions |
| `questionnaire.csv` | même contenu en tableau (séparateur `;`, ouvrable dans Excel) |
| `questionnaire.json` | tout le détail, y compris le contexte et les anomalies |
| `brut/*.txt` | texte brut lu dans chaque rubrique, pour contrôler une question |
| `journal.txt` | déroulé complet : clics, réponses testées, avertissements |

Les résultats sont enregistrés après chaque rubrique.

**Avant de vous servir du texte, relisez la section « Anomalies à vérifier » en fin de `questionnaire.txt`.** Elle signale :

- un code de question présent dans le texte de la rubrique mais non extrait (la question est dans `brut\`) ;
- des tests interrompus par la limite `--max-tests` ;
- des réponses qui n'ont pas pu être remises à leur valeur d'origine.

Les champs sont décrits ainsi dans `questionnaire.txt` :

- **Affichée si** : conditions minimales d'affichage, par exemple `Stato = « Italia »` ;
- **Toujours affichée** : visible dès l'ouverture de la rubrique ;
- **Masquée si** : conditions où une question visible au départ disparaît ;
- **Contexte** : titres et textes de la rubrique qui précèdent la question ;
- **Consignes** : les lignes en italique sous le libellé.

## 4. Sécurité

- **Clics** : uniquement sur les rubriques bleues de la colonne de gauche (liens dont le texte commence par un code, par exemple `GEA - `), et sur les boutons radio et cases des questions. Les boutons « Invia », « Salva », les liens du contenu et le bandeau rouge « Salvare le modifiche… » ne sont jamais cliqués.
- **Saisie** : aucun texte n'est saisi. Les listes déroulantes sont changées par leur valeur, sans clic.
- **Soumission** : `submit` et `form.submit()` sont bloqués dans la page. Les requêtes `POST`, `PUT`, `PATCH` et `DELETE` sont annulées et journalisées (`requetes_bloquees` dans le JSON).
- **Remise à zéro** : après chaque essai, toutes les réponses sont ramenées à leur valeur d'origine, et avant chaque changement de rubrique.
- **Boîtes de dialogue** : refusées et journalisées.
- **Données** : tout reste en local. Le dépôt est public : les dossiers `sortie\` et `profil_navigateur\` sont exclus de Git.

## 5. Limites connues

- Les **listes à choix multiples** et les **champs de texte** ne sont pas testés : ils ne révèlent pas de question dans les cas usuels. Leur présence et leurs options (pour les listes) sont tout de même extraites.
- Si un changement de réponse **recharge la page** côté serveur (par exemple `onchange="submit()"`), le script ne peut pas tester cette réponse : elle est bloquée et signalée dans le journal. Les questions qu'elle révèle seraient alors manquantes. Le test de la page de démonstration couvre ce cas.
- Les **rubriques** doivent être des liens (`<a>`) situés dans la colonne de gauche, et leur texte doit commencer par un code (`GEA - …`, `RB1 - …`). Si le script annonce « 0 rubrique », c'est généralement l'un de ces points : envoyez-moi le texte de `journal.txt` pour adapter la détection.
- Les **questions sans code** sont identifiées par leur libellé.
- Le contenu lu est celui de l'écran : la **page de synthèse « Anteprima stampa »** n'est pas utilisée.
- L'outil n'a pas pu être testé sur le questionnaire réel : il a été validé sur une copie locale qui reproduit la mise en page des captures. **Lancez une première rubrique et comparez avec l'écran** avant de traiter tout le questionnaire.

## 6. Tests

```bat
py -m pip install pytest
py -m pytest questionnaire\tests
```

Les tests lancent le script sur la page de démonstration `tests\site_test\index.html` et vérifient les conditions, les options, l'absence de soumission et l'absence de clic interdit.
