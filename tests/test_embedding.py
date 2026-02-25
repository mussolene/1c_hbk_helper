"""Tests for embedding module."""

from unittest.mock import MagicMock, patch

import pytest

from onec_help import embedding as embedding_mod


def test_get_embedding_dimension_default() -> None:
    """Default backend is local: dimension is VECTOR_SIZE."""
    assert embedding_mod.get_embedding_dimension() == embedding_mod.VECTOR_SIZE


def test_get_embedding_dimension_openai_api() -> None:
    """When openai_api and EMBEDDING_DIMENSION set, returns that value."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "openai_api", "EMBEDDING_DIMENSION": "768"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        assert embedding_mod.get_embedding_dimension() == 768
    importlib.reload(embedding_mod)


def test_get_embedding() -> None:
    vec = embedding_mod.get_embedding("test text")
    assert isinstance(vec, list)
    assert len(vec) == embedding_mod.VECTOR_SIZE
    assert all(isinstance(x, float) for x in vec)


def test_get_embedding_backend_none() -> None:
    """When EMBEDDING_BACKEND=none, uses placeholder vector (no model, no API)."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "none"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        vec = embedding_mod.get_embedding("hello")
        assert len(vec) == embedding_mod.VECTOR_SIZE
        assert all(isinstance(x, float) for x in vec)
        vec2 = embedding_mod.get_embedding("hello")
        assert vec == vec2
    importlib.reload(embedding_mod)


def test_get_embedding_openai_api_mock() -> None:
    """When EMBEDDING_BACKEND=openai_api and API returns valid embedding."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test:8080/v1",
            "EMBEDDING_MODEL": "test-model",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        fake_embedding = [0.1, 0.2, 0.3, 0.4]
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            # 1) _check_embedding_api_available: GET /models; 2) _resolve_openai_api_model: GET /models; 3) POST /embeddings
            mock_resp.read.side_effect = [
                b'{"data":[{"id":"test-model"}]}',
                b'{"data":[{"id":"test-model"}]}',
                b'{"data":[{"embedding":[0.1,0.2,0.3,0.4]}]}',
            ]
            mock_open.return_value.__enter__.return_value = mock_resp
            mock_open.return_value.__exit__.return_value = False
            vec = embedding_mod.get_embedding("hello")
        assert vec == fake_embedding
    importlib.reload(embedding_mod)


def test_get_embedding_batch_empty() -> None:
    assert embedding_mod.get_embedding_batch([]) == []


def test_get_embedding_batch_placeholder() -> None:
    """Batch with backend none returns list of placeholder vectors."""
    import importlib

    with patch.dict("os.environ", {"EMBEDDING_BACKEND": "none"}, clear=False):
        importlib.reload(embedding_mod)
        dim = embedding_mod.get_embedding_dimension()
        result = embedding_mod.get_embedding_batch(["a", "b"])
        assert len(result) == 2
        assert len(result[0]) == dim
        assert len(result[1]) == dim
    importlib.reload(embedding_mod)


def test_embedding_timeout_default() -> None:
    """_embedding_timeout returns int from env or default."""
    import importlib

    with patch.dict("os.environ", {"EMBEDDING_TIMEOUT": "90"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_timeout() == 90
    with patch.dict("os.environ", {"EMBEDDING_TIMEOUT": "invalid"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_timeout() == embedding_mod.DEFAULT_EMBEDDING_TIMEOUT
    importlib.reload(embedding_mod)


def test_embedding_batch_size_clamp() -> None:
    """_embedding_batch_size clamps to 1..256 and handles invalid env."""
    import importlib

    with patch.dict("os.environ", {"EMBEDDING_BATCH_SIZE": "128"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_batch_size() == 128
    with patch.dict("os.environ", {"EMBEDDING_BATCH_SIZE": "0"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_batch_size() == 1
    with patch.dict("os.environ", {"EMBEDDING_BATCH_SIZE": "999"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_batch_size() == 256
    with patch.dict("os.environ", {"EMBEDDING_BATCH_SIZE": "x"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_batch_size() == embedding_mod.DEFAULT_EMBEDDING_BATCH_SIZE
    importlib.reload(embedding_mod)


def test_embedding_workers_clamp() -> None:
    """_embedding_workers clamps to 1..16 and handles invalid env."""
    import importlib

    with patch.dict("os.environ", {"EMBEDDING_WORKERS": "8"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_workers() == 8
    with patch.dict("os.environ", {"EMBEDDING_WORKERS": "0"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_workers() == 1
    with patch.dict("os.environ", {"EMBEDDING_WORKERS": "99"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_workers() == 16
    with patch.dict("os.environ", {"EMBEDDING_WORKERS": "nope"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_workers() == embedding_mod.DEFAULT_EMBEDDING_WORKERS


def test_embedding_force_batch() -> None:
    """EMBEDDING_FORCE_BATCH=1 forces max batch size and max workers for any backend."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_FORCE_BATCH": "1", "EMBEDDING_BATCH_SIZE": "32", "EMBEDDING_WORKERS": "2"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_force_batch() is True
        assert embedding_mod._embedding_batch_size() == embedding_mod.MAX_EMBEDDING_BATCH_SIZE
        assert embedding_mod._embedding_workers() == embedding_mod.MAX_EMBEDDING_WORKERS
    with patch.dict("os.environ", {"EMBEDDING_FORCE_BATCH": "yes"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_force_batch() is True
    with patch.dict("os.environ", {"EMBEDDING_FORCE_BATCH": "0"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._embedding_force_batch() is False
    importlib.reload(embedding_mod)
    importlib.reload(embedding_mod)


def test_log_fallback() -> None:
    """_log_fallback logs first time and every 100th."""
    import importlib

    importlib.reload(embedding_mod)
    embedding_mod._fallback_log_count = 0
    with patch("sys.stderr") as mock_stderr:
        embedding_mod._log_fallback("reason one")
        assert mock_stderr.write.called
        embedding_mod._log_fallback("reason 100")  # count=2, not 100th
        embedding_mod._fallback_log_count = 99
        embedding_mod._log_fallback("reason 100th")
        assert mock_stderr.write.called


def test_check_embedding_api_available_unavailable() -> None:
    """When API is unreachable, _check_embedding_api_available returns False and logs."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "openai_api", "EMBEDDING_API_URL": "http://nonexistent:9999/v1"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = OSError("connection refused")
            result = embedding_mod._check_embedding_api_available()
        assert result is False
    importlib.reload(embedding_mod)


def test_embedding_fallback_dim_when_detecting() -> None:
    """_embedding_fallback_dim returns VECTOR_SIZE when _dimension_detecting is True."""
    with patch.object(embedding_mod, "_dimension_detecting", True):
        assert embedding_mod._embedding_fallback_dim() == embedding_mod.VECTOR_SIZE


def test_get_embedding_dimension_openai_api_detects_from_api() -> None:
    """get_embedding_dimension with openai_api and no EMBEDDING_DIMENSION detects from API."""
    import importlib
    import json

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        embedding_mod._cached_api_dimension = None
        embedding_mod._resolved_api_model_id = None
        with patch.object(embedding_mod, "_check_embedding_api_available", return_value=True):
            with patch.object(embedding_mod, "_resolve_openai_api_model", return_value="m"):
                with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = json.dumps(
                        {"data": [{"embedding": [0.0] * 768}]}
                    ).encode()
                    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                    mock_resp.__exit__ = MagicMock(return_value=False)
                    mock_open.return_value = mock_resp
                    dim = embedding_mod.get_embedding_dimension()
        assert dim == 768
    importlib.reload(embedding_mod)


def test_get_embedding_dimension_openai_api_invalid_dimension() -> None:
    """When EMBEDDING_DIMENSION is not int, falls through to VECTOR_SIZE or API."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "openai_api", "EMBEDDING_DIMENSION": "not_a_number", "EMBEDDING_API_URL": "http://x/v1"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding._check_embedding_api_available", return_value=False):
            dim = embedding_mod.get_embedding_dimension()
        assert dim == embedding_mod.VECTOR_SIZE
    importlib.reload(embedding_mod)


def test_resolve_openai_api_model_preferred() -> None:
    """_resolve_openai_api_model returns preferred model when match by substring."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "other",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data":[{"id":"nomic-embed-text-v1"}]}'
            mock_open.return_value.__enter__.return_value = mock_resp
            mock_open.return_value.__exit__.return_value = False
            model = embedding_mod._resolve_openai_api_model()
        assert "nomic" in model or model == "nomic-embed-text-v1"
    importlib.reload(embedding_mod)


def test_resolve_openai_api_model_first_in_list() -> None:
    """_resolve_openai_api_model returns first model when no preferred match."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "custom-model",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data":[{"id":"first-model"},{"id":"second"}]}'
            mock_open.return_value.__enter__.return_value = mock_resp
            mock_open.return_value.__exit__.return_value = False
            model = embedding_mod._resolve_openai_api_model()
        assert model == "first-model"
    importlib.reload(embedding_mod)


def test_resolve_openai_api_model_exact_match() -> None:
    """_resolve_openai_api_model returns exact EMBEDDING_MODEL when in list."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "exact-model",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data":[{"id":"exact-model"}]}'
            mock_open.return_value.__enter__.return_value = mock_resp
            mock_open.return_value.__exit__.return_value = False
            model = embedding_mod._resolve_openai_api_model()
        assert model == "exact-model"
    importlib.reload(embedding_mod)


def test_get_embedding_placeholder_custom_dim() -> None:
    """_get_embedding_placeholder with custom dimension."""
    vec = embedding_mod._get_embedding_placeholder("x", dimension=8)
    assert len(vec) == 8
    assert all(isinstance(x, float) for x in vec)


def test_get_embedding_backend_null_off() -> None:
    """get_embedding with backend null and off uses placeholder."""
    import importlib

    for backend in ("null", "off"):
        with patch.dict("os.environ", {"EMBEDDING_BACKEND": backend}, clear=False):
            importlib.reload(embedding_mod)
            vec = embedding_mod.get_embedding("t")
            assert len(vec) == embedding_mod.VECTOR_SIZE
    importlib.reload(embedding_mod)


def test_get_embedding_api_single_no_url() -> None:
    """_get_embedding_api_single with empty API URL returns placeholder (no HTTP call)."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "openai_api", "EMBEDDING_API_URL": ""},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        embedding_mod._cached_api_dimension = None
        embedding_mod._embedding_api_available = None
        vec = embedding_mod._get_embedding_api_single("text")
        assert len(vec) >= 1
        assert all(isinstance(x, float) for x in vec)
        vec2 = embedding_mod._get_embedding_api_single("text")
        assert vec == vec2
    importlib.reload(embedding_mod)


def test_get_embedding_api_single_retry_then_fallback() -> None:
    """_get_embedding_api_single retries then falls back to placeholder."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = OSError("timeout")
            with patch("onec_help.embedding.time.sleep"):
                vec = embedding_mod._get_embedding_api_single("x")
        assert len(vec) == 4
    importlib.reload(embedding_mod)


def test_get_embedding_api_single_retry_then_success() -> None:
    """_get_embedding_api_single retries on failure then succeeds (covers retry loop)."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        embedding_mod._embedding_api_available = True
        with patch.object(embedding_mod, "_resolve_openai_api_model", return_value="m"):
            with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
                fail_ctx = MagicMock()
                fail_ctx.__enter__.side_effect = OSError("first")
                ok_ctx = MagicMock()
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"data":[{"embedding":[0.1,0.2,0.3,0.4]}]}'
                ok_ctx.__enter__.return_value = mock_resp
                ok_ctx.__exit__.return_value = False
                mock_open.side_effect = [fail_ctx, ok_ctx]
                with patch("onec_help.embedding.time.sleep"):
                    vec = embedding_mod._get_embedding_api_single("x")
        assert vec == [0.1, 0.2, 0.3, 0.4]
    importlib.reload(embedding_mod)


def test_get_embedding_api_single_invalid_response() -> None:
    """_get_embedding_api_single when response has no embedding returns placeholder."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"data":[{}]}'
            mock_open.return_value.__enter__.return_value = mock_resp
            mock_open.return_value.__exit__.return_value = False
            vec = embedding_mod._get_embedding_api_single("x")
        assert len(vec) == 4
    importlib.reload(embedding_mod)


def test_get_embedding_api_batch_success() -> None:
    """_get_embedding_api_batch returns list of vectors from API."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = (
                b'{"data":[{"embedding":[0.1,0.2,0.3,0.4]},{"embedding":[0.5,0.6,0.7,0.8]}]}'
            )
            mock_open.return_value.__enter__.return_value = mock_resp
            mock_open.return_value.__exit__.return_value = False
            with patch.object(embedding_mod, "_check_embedding_api_available", return_value=True):
                with patch.object(embedding_mod, "_resolve_openai_api_model", return_value="m"):
                    result = embedding_mod._get_embedding_api_batch(["a", "b"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3, 0.4]
        assert result[1] == [0.5, 0.6, 0.7, 0.8]
    importlib.reload(embedding_mod)


def test_get_embedding_api_batch_fallback_to_single() -> None:
    """_get_embedding_api_batch on error falls back to single requests."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        embedding_mod._embedding_api_available = True
        with patch.object(embedding_mod, "_resolve_openai_api_model", return_value="m"):
            with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
                mock_open.side_effect = OSError("timeout")
                with patch("onec_help.embedding.time.sleep"):
                    with patch.object(embedding_mod, "_get_embedding_api_single") as mock_single:
                        mock_single.return_value = [0.0, 0.0, 0.0, 0.0]
                        result = embedding_mod._get_embedding_api_batch(["x", "y"])
        assert len(result) == 2
        assert mock_single.call_count == 2
    importlib.reload(embedding_mod)


def test_get_embedding_api_batch_one_item_missing_embedding() -> None:
    """_get_embedding_api_batch uses placeholder for item when embedding key missing."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = (
                b'{"data":[{"embedding":[1,2,3,4]},{},{"embedding":[5,6,7,8]}]}'
            )
            mock_open.return_value.__enter__.return_value = mock_resp
            mock_open.return_value.__exit__.return_value = False
            with patch.object(embedding_mod, "_check_embedding_api_available", return_value=True):
                with patch.object(embedding_mod, "_resolve_openai_api_model", return_value="m"):
                    result = embedding_mod._get_embedding_api_batch(["a", "b", "c"])
        assert len(result) == 3
        assert result[0] == [1, 2, 3, 4]
        assert len(result[1]) == 4
        assert all(isinstance(x, float) for x in result[1])
        assert result[2] == [5, 6, 7, 8]
    importlib.reload(embedding_mod)


def test_get_embedding_api_batch_retry_then_success() -> None:
    """_get_embedding_api_batch retries on failure then returns vectors (covers retry loop)."""
    import importlib

    with patch.dict(
        "os.environ",
        {
            "EMBEDDING_BACKEND": "openai_api",
            "EMBEDDING_API_URL": "http://test/v1",
            "EMBEDDING_MODEL": "m",
            "EMBEDDING_DIMENSION": "4",
        },
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch.object(embedding_mod, "_check_embedding_api_available", return_value=True):
            with patch.object(embedding_mod, "_resolve_openai_api_model", return_value="m"):
                with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
                    fail_ctx = MagicMock()
                    fail_ctx.__enter__.side_effect = OSError("first")
                    ok_ctx = MagicMock()
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = (
                        b'{"data":[{"embedding":[1,2,3,4]},{"embedding":[5,6,7,8]}]}'
                    )
                    ok_ctx.__enter__.return_value = mock_resp
                    ok_ctx.__exit__.return_value = False
                    mock_open.side_effect = [fail_ctx, ok_ctx]
                    with patch("onec_help.embedding.time.sleep"):
                        result = embedding_mod._get_embedding_api_batch(["a", "b"])
                assert len(result) == 2
                assert result[0] == [1, 2, 3, 4]
                assert result[1] == [5, 6, 7, 8]
    importlib.reload(embedding_mod)


def test_get_embedding_api_batch_parallel_workers_gt_one() -> None:
    """_get_embedding_api_batch_parallel with workers>1 and multiple batches."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "openai_api", "EMBEDDING_API_URL": "http://test/v1", "EMBEDDING_DIMENSION": "4"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch.object(embedding_mod, "_get_embedding_api_batch") as mock_batch:
            mock_batch.side_effect = [
                [[0.1] * 4, [0.2] * 4],
                [[0.3] * 4, [0.4] * 4],
            ]
            result = embedding_mod._get_embedding_api_batch_parallel(
                ["a", "b", "c", "d"], batch_size=2, workers=2
            )
        assert len(result) == 4
        assert mock_batch.call_count == 2
    importlib.reload(embedding_mod)


def test_get_embedding_batch_openai_api_uses_parallel() -> None:
    """get_embedding_batch with openai_api calls batch parallel."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "openai_api", "EMBEDDING_API_URL": "http://test/v1", "EMBEDDING_DIMENSION": "4"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        with patch.object(embedding_mod, "_get_embedding_api_batch_parallel") as mock_par:
            mock_par.return_value = [[0.0] * 4, [0.0] * 4]
            embedding_mod.get_embedding_batch(["x", "y"], batch_size=2, workers=2)
        mock_par.assert_called_once()
        assert mock_par.call_args[0][2] == 2
    importlib.reload(embedding_mod)


def test_get_embedding_local_batch_import_error() -> None:
    """_get_embedding_local_batch when sentence_transformers missing returns placeholders."""
    import importlib

    with patch.dict("os.environ", {"EMBEDDING_BACKEND": "local"}, clear=False):
        importlib.reload(embedding_mod)
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with patch("importlib.import_module") as mock_import:
                mock_import.side_effect = ImportError
                result = embedding_mod._get_embedding_local_batch(["a", "b"])
        assert len(result) == 2
        assert len(result[0]) == embedding_mod.VECTOR_SIZE
    importlib.reload(embedding_mod)


def test_get_embedding_batch_local_chunked() -> None:
    """get_embedding_batch with local backend chunks by batch_size."""
    import importlib

    with patch.dict("os.environ", {"EMBEDDING_BACKEND": "local"}, clear=False):
        importlib.reload(embedding_mod)
        with patch.object(embedding_mod, "_get_embedding_local_batch") as mock_local:
            mock_local.side_effect = [[[0.0] * 384], [[0.0] * 384, [0.0] * 384]]
            result = embedding_mod.get_embedding_batch(["a", "b", "c"], batch_size=2)
        assert len(result) == 3
        assert mock_local.call_count == 2
    importlib.reload(embedding_mod)


def test_check_embedding_api_available_cached_true() -> None:
    """_check_embedding_api_available returns cached True without calling urlopen."""
    import importlib

    with patch.dict(
        "os.environ",
        {"EMBEDDING_BACKEND": "openai_api", "EMBEDDING_API_URL": "http://test/v1"},
        clear=False,
    ):
        importlib.reload(embedding_mod)
        embedding_mod._embedding_api_available = True
        with patch("onec_help.embedding.urllib.request.urlopen") as mock_open:
            assert embedding_mod._check_embedding_api_available() is True
            mock_open.assert_not_called()
    importlib.reload(embedding_mod)


def test_check_embedding_api_available_backend_not_openai() -> None:
    """_check_embedding_api_available returns True when backend is not openai_api."""
    import importlib

    with patch.dict("os.environ", {"EMBEDDING_BACKEND": "local"}, clear=False):
        importlib.reload(embedding_mod)
        assert embedding_mod._check_embedding_api_available() is True
    importlib.reload(embedding_mod)
