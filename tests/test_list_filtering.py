from code_puppy.list_filtering import normalize_filter_text, query_matches_text


def test_normalize_filter_text_collapses_case_and_punctuation():
    assert normalize_filter_text("GPT-5.4 Mini") == "gpt 5 4 mini"


def test_query_matches_text_handles_multiple_terms_across_candidates():
    assert query_matches_text("gpt mini", "GPT-5.4", "Mini")


def test_query_matches_text_returns_false_for_missing_term():
    assert not query_matches_text("gpt opus", "GPT-5.4 Mini")
