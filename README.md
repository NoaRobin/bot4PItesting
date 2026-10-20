![Uploading {DB2E134C-34F6-440A-BD21-65739CAB24AB}.png…]()



# bot4PItesting : banc de test du Product Info Assistant

`pia_bench` pose les 1 500 questions du benchmark au Product Info Assistant (Copilot Studio) et
**ouvre lui-même un chat neuf pour chaque conversation de 5 tours**. Plus besoin d'appuyer sur
Entrée tous les 100 messages, ni de modifier `START_INDEX` à la main après un incident.

Les scripts v21 à v28 sont rangés dans `legacy/`.

## Ce qui change par rapport à v28

| Constat (rapport du 29/09, onglet AUDIT_BENCHMARK) | v21–v28 | pia_bench |
|---|---|---|
| 100 questions (20 conversations) dans un même chat : « aucune information » passe de 5 % à 15-18 % après la 50e question | pause manuelle tous les 100 | **un chat neuf par conversation**, ouvert automatiquement (URL de l'agent, sinon bouton « Nouvelle conversation ») |
| Un incident arrête tout, reprise par une nouvelle version du script (Q0601, Q0656, Q0711) | arrêt + `START_INDEX` codé en dur | la **conversation entière est rejouée dans un chat neuf** (3 tentatives, attente croissante) ; la campagne continue |
| 5 « Oops! Something happened » | capturés comme réponses | détectés : la conversation est rejouée |
| Premier chat du 28/09 : 70 « aucune information » sur 84 | vu après coup | **session dégradée détectée en direct** : relance du navigateur, conversations rejouées |
| Lot 6 capturé sur l'ancien classeur | nom de fichier codé en dur | empreinte SHA-256 du classeur liée à la campagne, chemin en configuration |
| 171 lignes orphelines (textes longs éclatés) | ignorées | recollées à la ligne précédente |
| Envoi non confirmé dans la page | — | saisie vérifiée avant Entrée, envoi confirmé (message affiché, saisie vidée ou génération en cours) |
| Latence non reprise | dans la base seulement | dans l'Excel et le rapport (médiane, p95) |
| Notation faite à part, à la main | — | **pré-verdicts automatiques** (même grille : Correct, Pas d'info à tort, Incorrect…), juge LLM facultatif, relecture humaine réimportée |
| Marge d'erreur | calculée à part | bootstrap par conversation, intégré au rapport |

## Installation (Windows, une fois)

```bat
py -m pip install -r requirements.txt
```

Edge est utilisé tel quel (`channel = "msedge"`) : pas besoin de `playwright install`.

## Utilisation

Placer le classeur `Benchmark_Product_Info_1500_questions_COUVERTURE_ELARGIE.xlsx` à côté du dossier
(ou indiquer son chemin dans `pia_bench.toml`, à créer à partir de `pia_bench.example.toml`).

```bat
:: 1. Contrôler le classeur (questions, conversations, lignes orphelines recollées)
py -m pia_bench check

:: 2. Une seule fois : Edge s'ouvre, vous ouvrez l'agent dans un chat vierge, Entrée.
::    L'URL de l'agent est mémorisée et le script vérifie qu'il sait ouvrir un chat neuf seul.
py -m pia_bench setup

:: 3. Pilote sur 3 conversations
py -m pia_bench run --campaign pilote --limit 3

:: 4. Campagne complète (laisser tourner ; Ctrl+C à tout moment sans rien perdre)
py -m pia_bench run --campaign octobre

:: Reprise après une coupure : les conversations terminées sont sautées
py -m pia_bench run --campaign octobre
py -m pia_bench run --resume                 :: = la dernière campagne

:: Rejouer seulement certaines conversations, ou mesurer la stabilité (3 passages)
py -m pia_bench run --campaign lot1 --conversations C001-C020
py -m pia_bench run --campaign stabilite --conversations C001-C010 --repeat 3
```

Chaque campagne a son dossier `runs/<nom>/` :

- `campaign.sqlite3` : journal durable (tentatives, tours, verdicts) ;
- `resultats.xlsx` : SYNTHESE, RESULTATS (colonnes jaunes à remplir), PAR_TOUR, PAR_CHAMP, PAR_THEME,
  PAR_GROUPE, TENTATIVES, STABILITE ;
- `rapport.html` : synthèse visuelle (exactitude et IC 95 %, par tour, par champ, latence) ;
- `captures/` : capture d'écran de chaque tentative échouée ;
- `run.log` : journal lisible.

### Notation

```bat
py -m pia_bench report                         :: recalcule verdicts + rapports
py -m pia_bench import-review                  :: relit les verdicts humains saisis dans resultats.xlsx
py -m pia_bench judge                          :: (facultatif) juge LLM sur les « À confirmer »
py -m pia_bench calibrate chemin\Benchmark_Product_Info_Resultats.xlsx
```

Priorité des verdicts : humain > juge LLM > règles. Les règles appliquent la grille du rapport du
29/09 et neutralisent les défauts connus du benchmark : libellés EN/FR (`equivalences.csv`, à
compléter), dates UTC (±1 jour accepté et signalé), nombres au format français, noms « NOM Prénom »,
chiffres du nom du fonds, valeur voisine d'un même champ (« Caceis Bank » ≠ « CACEIS Bank Luxembourg
Branch »). Quand elles ne savent pas trancher, elles répondent **« À confirmer »** plutôt que
« Incorrect ».

**Calibrage sur les 690 réponses relues à la main le 29/09 : 683/690 verdicts identiques (99,0 %),
aucun faux « Correct ».** Les 7 écarts restants sont 4 « À confirmer » (textes traduits, libellés
inconnus) et 3 cas où le verdict humain semble à revérifier (Q0699, Q0735, Q0754 : valeur attendue 0,
l'agent donne 100 %, 30 et 0,043, notés « Correct »).

Le juge LLM (`judge`) envoie la question, la valeur attendue et la réponse à l'API Claude
(`ANTHROPIC_API_KEY`). Il n'est jamais lancé automatiquement : **à faire valider par la conformité**
avant de l'utiliser sur des données internes.

## Transports

- `edge` (défaut) : pilote l'interface de chat comme un utilisateur. Tous les sélecteurs sont dans la
  configuration : si Microsoft change l'écran, on corrige `pia_bench.toml` sans toucher au code.
- `directline` : parle à l'agent par l'API Direct Line de Copilot Studio, sans navigateur. Plus
  robuste et plus rapide, mais il faut que l'administrateur de l'agent fournisse le secret du canal
  ou l'URL du « token endpoint », et que l'agent n'exige pas l'authentification Entra de l'utilisateur.
- `fake` : agent simulé, pour essayer toute la chaîne sans solliciter l'agent :
  `py -m pia_bench run --transport fake --campaign essai`.

## Tests

```bat
py -m pytest -q
```

Les tests utilisent un classeur fictif et une **fausse interface Copilot** (`tests/fake_copilot/`)
qui reproduit le DOM réel : « Mise en place en cours… », réponse en streaming, bouton « Arrêter »,
« Oops! Something happened » injecté. Ils vérifient qu'une conversation n'utilise jamais deux chats,
que chaque conversation a son chat, et qu'une erreur plateforme fait rejouer la conversation.

## Pourquoi cette architecture

- **Une conversation = une session isolée** : c'est le protocole du benchmark et ce que font les outils
  d'évaluation (Copilot Studio Agent Evaluation, Copilot Studio Kit, DeepEval, promptfoo) ; l'article
  *LLMs Get Lost in Multi-Turn Conversation* (Laban et al., ICLR 2026) montre une forte baisse de
  fiabilité quand le contexte s'allonge, cohérente avec l'effet observé à partir de la 50e question.
- **Collecte et notation séparées** : on peut renoter (nouvelles équivalences, juge, relecture) sans
  reposer une seule question à l'agent.
- **Notation à la conversation** (score 5/5, IC bootstrap par conversation) et **par tour** (dérive
  dans la conversation), pas seulement question par question.
- **Répétitions** (`--repeat`) : la même question donne parfois un verdict différent d'une session à
  l'autre (onglet STABILITE du 29/09) ; pass^k mesure la fiabilité « juste à chaque fois ».
- **Jamais de tour rejoué hors contexte** : un tour en échec fait rejouer toute la conversation dans un
  chat neuf, pour que le tour 4 soit toujours posé après les tours 1 à 3 du même chat.
