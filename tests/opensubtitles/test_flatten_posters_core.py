from srt_translator.services.opensubtitles_client import flatten_subtitle_results


def test_flatten_subtitle_results_language_name():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "fr",
                    "files": [{"file_id": 1, "file_name": "x.srt"}],
                    "feature_details": {"movie_name": "M"},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload, language_names={"fr": "French"})
    assert len(rows) == 1
    assert rows[0]["language"] == "fr"
    assert rows[0]["languageName"] == "French"


def test_flatten_poster_related_links_list():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "related_links": [
                        {
                            "label": "Movie",
                            "url": "https://www.opensubtitles.com/en/movies/x",
                            "img_url": "https://s9.osdb.link/features/1/2/3/99.jpg",
                        },
                    ],
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://s9.osdb.link/features/1/2/3/99.jpg"


def test_flatten_poster_from_included_feature():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "relationships": {
                    "feature": {"data": {"type": "feature", "id": "42"}},
                },
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "X"},
                },
            }
        ],
        "included": [
            {
                "type": "feature",
                "id": "42",
                "attributes": {"image": "https://img.example/poster.png"},
            }
        ],
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://img.example/poster.png"


def test_flatten_poster_protocol_relative_img_url():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "related_links": {"imgUrl": "//cdn.example/p/a.jpg"},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://cdn.example/p/a.jpg"


def test_flatten_poster_relative_path_on_opensubtitles_com():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "related_links": {"img_url": "/pictures/posters/abc.jpg"},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://www.opensubtitles.com/pictures/posters/abc.jpg"


def test_flatten_poster_deep_nested_string():
    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {
                        "movie_name": "X",
                        "nested": {"note": "see https://s9.osdb.link/features/1/2/3/z.jpg"},
                    },
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://s9.osdb.link/features/1/2/3/z.jpg"
