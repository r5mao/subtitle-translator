import json
import urllib.error
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

        if "/movie/1399" in u and "api.themoviedb.org" in u:
            raise urllib.error.HTTPError(u, 404, "Not Found", hdrs={}, fp=None)
        if "/tv/1399" in u and "api.themoviedb.org" in u:
            return R(
                json.dumps(
                    {
                        "name": "Some Show",
                        "first_air_date": "2011-04-17",
                        "poster_path": "/from-tv.jpg",
                        "backdrop_path": "/bd.jpg",
                    }
                ).encode("utf-8")
            )
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
    assert rows[0]["title"] == "Some Show"
    assert rows[0]["year"] == 2011
    assert len(calls) == 2
    assert "/movie/1399" in calls[0]
    assert "/tv/1399" in calls[1]


def test_flatten_poster_tmdb_fallback(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "test-tmdb-key")

    class FakeResp:
        def read(self):
            return json.dumps(
                {
                    "title": "Fight Club",
                    "release_date": "1999-10-15",
                    "poster_path": "/abc.jpg",
                    "backdrop_path": "/bd.jpg",
                }
            ).encode("utf-8")

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
    assert rows[0]["title"] == "Fight Club"
    assert rows[0]["year"] == 1999


def test_tmdb_poster_api_and_cdn_url_construction(monkeypatch):
    """TMDb movie details request and resulting image.tmdb.org URLs must follow a fixed shape."""
    monkeypatch.setenv("TMDB_API_KEY", "k")
    seen: list[str] = []

    class FakeResp:
        def read(self):
            return json.dumps(
                {
                    "title": "Movie",
                    "release_date": "2020-01-01",
                    "poster_path": "/movie/poster1.jpg",
                    "backdrop_path": "/movie/backdrop1.jpg",
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
    assert seen[0].startswith("https://api.themoviedb.org/3/movie/999?")
    assert "api_key=k" in seen[0]
    assert "/images" not in seen[0]
    assert rows[0]["posterUrl"] == "https://image.tmdb.org/t/p/w185/movie/poster1.jpg"
    assert rows[0]["backdropUrl"] == "https://image.tmdb.org/t/p/w780/movie/backdrop1.jpg"


def test_flatten_tmdb_overrides_opensubtitles_title_and_year(monkeypatch):
    """When TMDB_API_KEY is set, TMDb title and release year replace OS catalog strings."""
    monkeypatch.setenv("TMDB_API_KEY", "k")

    def fake_urlopen(req, *a, **k):
        u = getattr(req, "full_url", None) or req.get_full_url()

        class R:
            def read(self):
                return json.dumps(
                    {
                        "title": "Avatar: The Way of Water",
                        "release_date": "2022-12-16",
                        "poster_path": "/av.jpg",
                        "backdrop_path": "/avbd.jpg",
                    }
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        if "/movie/76600" in u and "api.themoviedb.org" in u:
            return R()
        raise AssertionError(u)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "Avatar.2.2020.x264.srt"}],
                    "feature_details": {
                        "title": "Avatar 2",
                        "year": 2020,
                        "tmdb_id": 76600,
                    },
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["title"] == "Avatar: The Way of Water"
    assert rows[0]["year"] == 2022


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
