import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app

def test_parse_age_subject():
    it = app.parse("teach science to 12-year-olds")
    assert it["age"] == 12 and it["subject"] == "science-math" and "primary-secondary" in it["levels"]

def test_parse_language_learning():
    it = app.parse("learn French")
    assert it["lang"] == "fra" and it["subject"] == "language"

def test_parse_size_units():
    assert app.parse("medicine under 2 GB")["max_gb"] == 2.0
    assert app.parse("something under 500 MB")["max_gb"] == 0.5

def test_baseline_survives_hostile_input():
    assert isinstance(app.baseline('"; DROP TABLE x; -- ()*'), list)
    assert app.baseline("") == []

def test_intent_respects_size_limit():
    res, _ = app.intent("medical resources under 2 GB", 20)
    assert res and all(r["size_gb"] is None or r["size_gb"] <= 2 for r in res)

def test_every_result_is_explained():
    res, _ = app.intent("learn French", 10)
    assert res and all(r["why"] for r in res)

def test_library_fits_budget_and_has_unique_titles():
    lib = app.library("teach science to 12-year-olds", 5)
    assert lib["used_gb"] <= 5 + 1e-6
    titles = [i["title"] for i in lib["items"]]; assert len(titles) == len(set(titles))

def test_library_zero_budget():
    assert app.library("science", 0)["items"] == []
