# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from pia_bench import scoring as S
from pia_bench.catalogue import load_catalogue
from conftest import make_workbook

EQ = S.Equivalences.load(Path(__file__).resolve().parents[1] / "equivalences.csv")


def test_catalogue_groups_and_merges_orphans(workbook):
    cat = load_catalogue(workbook)
    assert len(cat.questions) == 20
    assert cat.merged_orphans == 1
    assert cat.by_qid()["Q0002"].attendu.endswith("(suite du texte long)")
    convs = cat.conversations
    assert [c.cid for c in convs] == ["C001", "C002", "C003", "C004"]
    assert all([q.tour for q in c.turns] == [1, 2, 3, 4, 5] for c in convs)
    assert cat.by_qid()["Q0005"].notable is False
    assert cat.by_qid()["Q0001"].theme == "Équipe complète"


def test_catalogue_digest_changes_with_content(tmp_path):
    a = load_catalogue(make_workbook(tmp_path / "a.xlsx"))
    b = load_catalogue(make_workbook(tmp_path / "b.xlsx"))
    c = load_catalogue(make_workbook(tmp_path / "c.xlsx", n_conv=3))
    assert a.digest == b.digest != c.digest


def v(expected, answer, notable=True, champ="", produit="", competitors=()):
    return S.score(expected, notable, answer, champ, produit, EQ, competitors).verdict


@pytest.mark.parametrize("expected,answer", [
    ("Unit Trust (FCP)", "Résultat La forme juridique est : FCP (Fonds Commun de Placement)."),
    ("UCITS (OPCVM)", "Résultat Information trouvée OPCVM"),
    ("World", "La région d’investissement indiquée est : Monde"),
    ("Euro zone", "la zone d’investissement indiquée est : Zone euro"),
    ("MARTIN Paul", "le gérant principal est : Paul MARTIN"),
    ("LAFONT (DE) Alice", "Le gérant principal est : Alice LAFONT"),
    ("BELANGERE Jules", "le premier gérant secondaire est : Jules Bélangère"),
    ("0.143", "les coûts sont de : 0,143 %"),
    ("2", "le plafond est de 2,00 %"),
    ("27/04/2012", "Date d’agrément : 27/04/2012"),
    ("27/02/2018", "Date de création du produit : 26/02/2018"),          # UTC → Paris
    ("31/12/2027", "la date d’échéance renseignée est le 31 décembre 2027."),
    ("01/06/2024", "la date de début est le 1er juin 2024"),
    ("Until 31 December 2030", "est : Jusqu’au 31 décembre 2030."),
    ("969500ABCDEF12345678", "Le code LEI est : 969500ABCDEF12345678."),
    ("No (Non)", "Résultat Information trouvée le champ Benchmark est renseigné à : Non"),
    ("5 years (5 ans)", "La durée de détention recommandée est : 5 ans"),
])
def test_correct(expected, answer):
    assert v(expected, answer) == S.CORRECT


def test_fund_name_digits_are_not_answers():
    assert v("2", "Le SRI de R-co Target 2029 HY est : 3", produit="R-co Target 2029 HY") == S.INCORRECT
    assert v("2", "Le SRI de R-co Target 2029 HY est : 2", produit="R-co Target 2029 HY") == S.CORRECT


@pytest.mark.parametrize("expected,answer", [
    ("SICAV", "Résultat Aucune information disponible pour cette demande."),
    ("4", "Résultat Information trouvée Aucune note de risque officielle n’est renseignée pour ce fonds."),
    ("Europe", "Aucune zone d’investissement n’est renseignée pour le fonds."),
    # « oui/non » cité seulement dans les détails d'une réponse « aucune information »
    ("Yes (Oui)", "Résultat Aucune information disponible pour cette demande. Détails complémentaires "
                  "Il n’est donc pas possible de déterminer une valeur « Oui » ou « Non »."),
])
def test_no_info(expected, answer):
    assert v(expected, answer) == S.NO_INFO


def test_details_no_info_does_not_hide_a_correct_answer():
    answer = ("Résultat Information trouvée Le dépositaire est : Caceis Bank. "
              "Détails complémentaires Aucune information complémentaire pertinente.")
    assert v("Caceis Bank", answer) == S.CORRECT


def test_incorrect_typed_and_competitor_values():
    assert v("2025", "l’année des coûts renseignée est 2024.") == S.INCORRECT
    assert v("0.011", "la valeur enregistrée est : 0,00") == S.INCORRECT
    comps = {"Caceis Bank", "CACEIS Bank Luxembourg Branch", "Rothschild & Co Martin Maurel"}
    assert v("Rothschild & Co Martin Maurel", "Le centralisateur est : CACEIS Bank Luxembourg Branch",
             competitors=comps) == S.INCORRECT
    assert v("Caceis Bank", "Le dépositaire est : CACEIS Bank Luxembourg Branch", competitors=comps) == S.INCORRECT


def test_unknown_translation_goes_to_review_not_incorrect():
    assert v("Equities management – NZAMi", "la valeur du champ Article 29 est : Gestion directe – NZAMi") == S.REVIEW


def test_empty_cells():
    assert v("", "Résultat Aucune information disponible pour cette demande.", notable=False) == S.ABSTENTION
    assert v("", "Aucun deuxième gérant secondaire n’est renseigné pour le fonds.", notable=False) == S.ABSTENTION
    assert v("", "Le troisième gérant est : Jean MARTIN", notable=False) == S.INVENTED


def test_technical_and_flags():
    assert v("SICAV", "Oops! Something happened. Can you try again?Share feedback") == S.TECH
    assert S.technical_kind("Too many requests, please wait") == "RATE_LIMIT"
    r = S.score("SICAV", True, "Résultat Information trouvée Aucune information disponible. SICAV", eq=EQ)
    assert "contradictoire" in r.flags


def test_raw_english_values_of_the_new_workbook():
    assert v("5 years", "La durée de détention recommandée est de 5 ans.") == S.CORRECT
    assert v("No AMF Classification", "la classification AMF renseignée est : Pas de Classification AMF") == S.CORRECT
    assert v("Last open business day of December", "clôture annuelle : Dernier jour ouvré de décembre") == S.CORRECT


def test_off_topic_answers():
    for answer in ("Quel est le scope de recherche que vous souhaitez utiliser pour la recherche de données ?",
                   "Je n’ai pas reçu de demande exploitable. Pouvez-vous indiquer le fonds ?",
                   "Pouvez-vous fournir la requête SQL SELECT que vous souhaitez exécuter ?",
                   "Product Info Assistant said:\nProduct Info Assistant\n"):
        assert v("SICAV", answer) == S.OFF_TOPIC
    assert S.score("", False, "La réaffectation à un représentant n’est pas configurée pour ce copilote.", eq=EQ).verdict == S.OFF_TOPIC


def test_yes_no_reversed_is_incorrect():
    assert v("No", "Résultat Information trouvée l’indicateur est renseigné à « Oui ».") == S.INCORRECT
    assert v("Yes", "Résultat la valeur enregistrée pour l’indicateur est : Non.") == S.INCORRECT


def test_bubble_label_and_system_error():
    assert S.strip_label("Product Info Assistant said:\nProduct Info Assistant\nRésultat SICAV") == "Résultat SICAV"
    assert v("SICAV", "Product Info Assistant said:\nProduct Info Assistant\nRésultat La forme juridique est : SICAV") == S.CORRECT
    assert v("0.043", "Désolé, une erreur inattendue s’est produite. Code d’erreur : SystemError.") == S.TECH
