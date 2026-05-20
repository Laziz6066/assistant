import pytest

from voice_assistant.dictation.punctuation import normalize_punctuation


def test_empty_string_returns_empty():
    assert normalize_punctuation("") == ""


def test_text_without_punctuation_words_unchanged():
    assert normalize_punctuation("привет мама") == "привет мама"


def test_tochka_becomes_period():
    assert normalize_punctuation("привет мама точка") == "привет мама."


def test_zapyataya_becomes_comma():
    assert normalize_punctuation("молоко запятая хлеб") == "молоко, хлеб"


def test_vopros_becomes_question():
    assert normalize_punctuation("как дела вопрос") == "как дела?"


def test_vosklicatelnyj_becomes_excl():
    assert normalize_punctuation("ого восклицательный") == "ого!"


def test_dvoetochie_becomes_colon():
    assert normalize_punctuation("вывод двоеточие итог") == "вывод: итог"


def test_tire_becomes_em_dash():
    assert normalize_punctuation("а тире б") == "а — б"


def test_defis_becomes_hyphen():
    assert normalize_punctuation("сине дефис зелёный") == "сине - зелёный"


def test_novaya_stroka_becomes_newline():
    assert normalize_punctuation("первая строка новая строка вторая") == \
        "первая строка\nвторая"


def test_multi_word_tochka_s_zapyatoy():
    assert normalize_punctuation("тест точка с запятой следующее") == \
        "тест; следующее"


def test_multi_word_vosklicatelnyj_znak():
    assert normalize_punctuation("ура восклицательный знак") == "ура!"


def test_case_insensitive_match():
    assert normalize_punctuation("Привет Мама ТОЧКА") == "Привет Мама."


def test_word_boundary_prevents_partial_match_vostok():
    """'восток' must not be split into 'вос' + 'ток' via 'точка' substring."""
    assert normalize_punctuation("восток") == "восток"


def test_word_boundary_prevents_partial_match_tochki():
    """'точки' must not match 'точка'."""
    assert normalize_punctuation("не имеет точки") == "не имеет точки"


def test_multiple_punctuation_in_sentence():
    assert normalize_punctuation(
        "молоко запятая хлеб запятая сахар точка") == \
        "молоко, хлеб, сахар."


def test_whitespace_collapse():
    assert normalize_punctuation("привет    мама") == "привет мама"


def test_strip_leading_trailing_spaces():
    assert normalize_punctuation("   привет   ") == "привет"


def test_mixed_russian_english_passthrough():
    assert normalize_punctuation("hello world точка") == "hello world."
