import json
import urllib.request

from srt_translator.services.opensubtitles_client import flatten_subtitle_results


def test_flatten_poster_tmdb_falls_back_to_tv_when_movie_has_no_posters(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "k")
    calls: list[str] = []

    def fake_urlopen(req, *a, **k):
        u = getattr(req, "full_url", None) or req.get_full_url()
        calls.append(u)

        class R:
            def __init__(self, body: bytes):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        if "/movie/" in u:
            return R(json.dumps({"posters": []}).encode("utf-8"))
        if "/tv/" in u:
            return R(json.dumps({"posters": [{"file_path": "/from-tv.jpg"}]}).encode("utf-8"))
        raise AssertionError(f"unexpected urlopen url: {u}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "Some Show", "tmdb_id": 1399},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://image.tmdb.org/t/p/w185/from-tv.jpg"
    assert len(calls) == 2
    assert "/movie/1399/" in calls[0]
    assert "/tv/1399/" in calls[1]


def test_flatten_poster_tmdb_fallback(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "test-tmdb-key")

    class FakeResp:
        def read(self):
            return json.dumps({"posters": [{"file_path": "/abc.jpg"}]}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "X", "tmdb_id": 550},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://image.tmdb.org/t/p/w185/abc.jpg"


def test_tmdb_poster_api_and_cdn_url_construction(monkeypatch):
    """TMDb images request and resulting image.tmdb.org poster URL must follow a fixed shape."""
    monkeypatch.setenv("TMDB_API_KEY", "k")
    seen: list[str] = []

    class FakeResp:
        def read(self):
            return json.dumps(
                {
                    "posters": [{"file_path": "/movie/poster1.jpg"}],
                    "backdrops": [{"file_path": "/movie/backdrop1.jpg"}],
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def capture_urlopen(req, *a, **k):
        seen.append(getattr(req, "full_url", None) or req.get_full_url())
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "X", "tmdb_id": 999},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert len(seen) == 1
    assert seen[0].startswith("https://api.themoviedb.org/3/movie/999/images?")
    assert "api_key=k" in seen[0]
    assert rows[0]["posterUrl"] == "https://image.tmdb.org/t/p/w185/movie/poster1.jpg"
    assert rows[0]["backdropUrl"] == "https://image.tmdb.org/t/p/w780/movie/backdrop1.jpg"


def test_flatten_poster_from_included_movie_resource():
    """Shows may sideload poster on type=movie via relationships.movie."""
    payload = {
        "data": [
            {
                "type": "subtitle",
                "relationships": {"movie": {"data": {"type": "movie", "id": "77"}}},
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "ep.srt"}],
                    "feature_details": {"movie_name": "Some Show", "season_number": 1, "episode_number": 2},
                },
            }
        ],
        "included": [
            {
                "type": "movie",
                "id": "77",
                "attributes": {
                    "poster_url": "https://s9.osdb.link/features/show/77.jpg",
                    "feature_details": {},
                },
            }
        ],
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://s9.osdb.link/features/show/77.jpg"


def test_flatten_poster_from_included_parent_resource():
    """Episode rows may link poster via relationships.parent."""
    payload = {
        "data": [
            {
                "type": "subtitle",
                "relationships": {"parent": {"data": {"type": "feature", "id": "p1"}}},
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "Ep Title"},
                },
            }
        ],
        "included": [
            {
                "type": "feature",
                "id": "p1",
                "attributes": {"image": "https://img.example/parent-poster.png"},
            }
        ],
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://img.example/parent-poster.png"
