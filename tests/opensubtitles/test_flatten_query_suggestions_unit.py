from srt_translator.services.opensubtitles_client import (
    clean_work_search_query,
    distinct_work_suggestions_from_subtitles,
    filter_subtitle_rows_by_query,
    filter_work_suggestions_by_query,
    flatten_subtitle_results,
)

from tests.opensubtitles.support import FakeSuggestionsDupFeature


def test_clean_work_search_query_strips_opensubtitles_year_patterns():
    assert clean_work_search_query("1999 - The Matrix", 1999) == "The Matrix"
    assert clean_work_search_query("The Matrix (1999)", 1999) == "The Matrix"
    assert clean_work_search_query("The Matrix", 1999) == "The Matrix"
    assert clean_work_search_query("  2010  -  Some Film ", 2010) == "Some Film"


def test_flatten_prefers_title_over_movie_name_when_both_present():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {
                        "title": "My Mister",
                        "movie_name": "2024 - Unrelated Movie",
                        "year": 2018,
                    },
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert len(rows) == 1
    assert rows[0]["title"] == "My Mister"


def test_flatten_tv_uses_parent_title_over_movie_name():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {
                        "feature_type": "Episode",
                        "parent_title": "My Mister",
                        "title": "Episode One",
                        "season_number": 1,
                        "episode_number": 1,
                        "movie_name": "2024 - Random Film",
                    },
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["title"] == "My Mister · Episode One"


def test_filter_subtitle_rows_by_query_drops_unrelated_titles():
    rows = [
        {"title": "My Mister", "release": "", "fileName": "a.srt"},
        {"title": "2024 Blockbuster", "release": "", "fileName": "b.srt"},
    ]
    out = filter_subtitle_rows_by_query(rows, "My Mister")
    assert len(out) == 1
    assert out[0]["title"] == "My Mister"


def test_filter_subtitle_rows_by_query_keeps_all_if_query_not_in_any_row():
    rows = [{"title": "나의 아저씨", "release": "", "fileName": "a.srt"}]
    out = filter_subtitle_rows_by_query(rows, "My Mister")
    assert len(out) == 1


def test_filter_work_suggestions_by_query():
    sugs = [
        {"title": "My Mister", "searchQuery": "My Mister"},
        {"title": "Other Show", "searchQuery": "Other Show"},
    ]
    out = filter_work_suggestions_by_query(sugs, "My Mister")
    assert len(out) == 1


def test_filter_subtitle_rows_matches_dotted_filename():
    rows = [
        {"title": "x", "release": "", "fileName": "My.Mister.S01E01.1080p.srt"},
        {"title": "Other", "release": "", "fileName": "Something.Else.srt"},
    ]
    out = filter_subtitle_rows_by_query(rows, "My Mister")
    assert len(out) == 1
    assert "Mister" in out[0]["fileName"]


def test_flatten_skips_placeholder_api_title_uses_filename():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "My.Mister.2018.S01E01.HDTV.srt"}],
                    "feature_details": {
                        "title": "Empty Movie (SubScene)",
                        "movie_name": "Empty Movie (SubScene)",
                        "year": 2024,
                    },
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert len(rows) == 1
    assert rows[0]["title"] == "My Mister"
    assert rows[0]["year"] == 2018


def test_flatten_year_from_aligned_movie_name_when_api_year_wrong():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {
                        "title": "My Mister",
                        "movie_name": "2018 - My Mister",
                        "year": 2024,
                    },
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert len(rows) == 1
    assert rows[0]["year"] == 2018


def test_distinct_suggestion_year_from_aligned_movie_name_when_api_wrong():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "x.srt"}],
                    "feature_details": {
                        "title": "My Mister",
                        "movie_name": "2018 - My Mister",
                        "year": 2024,
                    },
                },
            }
        ]
    }
    sugs = distinct_work_suggestions_from_subtitles(payload, limit=5)
    assert len(sugs) == 1
    assert sugs[0]["year"] == 2018


def test_distinct_work_suggestions_dedupes_same_feature():
    c = FakeSuggestionsDupFeature()
    raw = c.search("x", languages="", page=1, per_page=50)
    sugs = distinct_work_suggestions_from_subtitles(raw, limit=10)
    assert len(sugs) == 2
    assert sugs[0]["title"] == "Same Movie"
    assert sugs[0]["searchQuery"] == "Same Movie"
    assert sugs[0]["year"] == 2019
    assert sugs[0]["posterUrl"] == "https://example.com/p1.jpg"
    assert sugs[0]["featureId"] == "42"
    assert sugs[1]["title"] == "Other Movie"
    assert sugs[1]["searchQuery"] == "Other Movie"
    assert sugs[1]["year"] == 2021
    assert sugs[1]["featureId"] == "99"
