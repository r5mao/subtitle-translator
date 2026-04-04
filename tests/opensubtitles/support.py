from tests.test_translate_and_download import make_srt


class FakeOpenSubtitlesClient:
    """Stub for OpenSubtitlesClient in route tests."""

    last_search = None

    def __init__(self):
        pass

    def configured(self):
        return True

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        assert query.strip()
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
            "year": year,
            "imdb_id": imdb_id,
        }
        return {
            "data": [
                {
                    "type": "subtitle",
                    "attributes": {
                        "language": "en",
                        "release": "Test.Release",
                        "download_count": 42,
                        "fps": 23.976,
                        "files": [{"file_id": 999001, "file_name": "sample_en.srt"}],
                        "feature_details": {"movie_name": "Test Movie", "year": 2020},
                        "related_links": {
                            "img_url": "https://example.com/poster/test-movie.jpg",
                        },
                    },
                }
            ],
            "total_pages": 3,
            "total_count": 75,
        }

    def download_file(self, file_id):
        return make_srt(), "sample_en.srt"


class FakeOpenSubtitlesManyPages(FakeOpenSubtitlesClient):
    """Upstream reports more pages than we expose to the client."""

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        out = super().search(
            query,
            languages=languages,
            page=page,
            per_page=per_page,
            year=year,
            imdb_id=imdb_id,
            **kwargs,
        )
        out = dict(out)
        out["total_pages"] = 50
        return out


class FakeSuggestionsDupFeature(FakeOpenSubtitlesClient):
    """Two subtitle rows share one feature id; third row is another feature."""

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        assert query.strip()
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
            "year": year,
            "imdb_id": imdb_id,
        }
        return {
            "data": [
                {
                    "type": "subtitle",
                    "relationships": {"feature": {"data": {"type": "feature", "id": "42"}}},
                    "attributes": {
                        "language": "en",
                        "release": "R1",
                        "files": [{"file_id": 1, "file_name": "a.srt"}],
                        "feature_details": {"movie_name": "Same Movie", "year": 2019},
                        "related_links": {"img_url": "https://example.com/p1.jpg"},
                    },
                },
                {
                    "type": "subtitle",
                    "relationships": {"feature": {"data": {"type": "feature", "id": "42"}}},
                    "attributes": {
                        "language": "es",
                        "release": "R2",
                        "files": [{"file_id": 2, "file_name": "b.srt"}],
                        "feature_details": {"movie_name": "Same Movie", "year": 2019},
                    },
                },
                {
                    "type": "subtitle",
                    "relationships": {"feature": {"data": {"type": "feature", "id": "99"}}},
                    "attributes": {
                        "language": "en",
                        "release": "R3",
                        "files": [{"file_id": 3, "file_name": "c.srt"}],
                        "feature_details": {"movie_name": "Other Movie", "year": 2021},
                    },
                },
            ],
        }


class FakeMultiFilePerSubtitle(FakeOpenSubtitlesClient):
    """Each API subtitle has multiple files; flatten yields more rows than per_page."""

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        assert query.strip()
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
            "year": year,
            "imdb_id": imdb_id,
        }
        data_items = []
        for i in range(5):
            data_items.append(
                {
                    "type": "subtitle",
                    "attributes": {
                        "language": "en",
                        "release": f"Release.{i}",
                        "download_count": 1,
                        "fps": 23.976,
                        "files": [
                            {"file_id": 880000 + i * 10 + j, "file_name": f"sub_{i}_{j}.srt"}
                            for j in range(3)
                        ],
                        "feature_details": {
                            "movie_name": "Multi CD",
                            "year": 2020,
                        },
                        "related_links": {
                            "img_url": "https://example.com/poster.jpg",
                        },
                    },
                }
            )
        return {
            "data": data_items,
            "total_pages": 1,
            "total_count": 5,
        }
