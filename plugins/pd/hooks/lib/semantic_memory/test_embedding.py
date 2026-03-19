"""Tests for semantic_memory.embedding module."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from semantic_memory.embedding import (
    EmbeddingProvider,
    GeminiProvider,
    NormalizingWrapper,
    OpenAIProvider,
    OllamaProvider,
    VoyageProvider,
    create_provider,
)
from semantic_memory import EmbeddingError


# ---------------------------------------------------------------------------
# EmbeddingProvider Protocol tests
# ---------------------------------------------------------------------------


class TestEmbeddingProviderProtocol:
    def test_protocol_is_runtime_checkable(self):
        """EmbeddingProvider should be decorated with @runtime_checkable."""
        assert hasattr(EmbeddingProvider, "__protocol_attrs__") or hasattr(
            EmbeddingProvider, "__abstractmethods__"
        ) or isinstance(EmbeddingProvider, type)
        # A class implementing all methods should pass isinstance check
        class _FakeProvider:
            @property
            def dimensions(self) -> int:
                return 768

            @property
            def provider_name(self) -> str:
                return "fake"

            @property
            def model_name(self) -> str:
                return "fake-model"

            def embed(self, text: str, task_type: str = "query") -> np.ndarray:
                return np.zeros(768, dtype=np.float32)

            def embed_batch(
                self, texts: list[str], task_type: str = "document"
            ) -> list[np.ndarray]:
                return [np.zeros(768, dtype=np.float32)]

        assert isinstance(_FakeProvider(), EmbeddingProvider)

    def test_non_conforming_class_fails_isinstance(self):
        """A class missing required methods should NOT match the protocol."""
        class _Incomplete:
            pass

        assert not isinstance(_Incomplete(), EmbeddingProvider)


# ---------------------------------------------------------------------------
# Mock helpers for parametrized provider tests
# ---------------------------------------------------------------------------


def _mock_gemini_embed(mock_genai, values_list: list[list[float]]):
    """Set up a Gemini mock to return given embedding values."""
    embeddings = []
    for values in values_list:
        emb = MagicMock()
        emb.values = values
        embeddings.append(emb)
    response = MagicMock()
    response.embeddings = embeddings
    mock_genai.Client.return_value.models.embed_content.return_value = response


def _mock_openai_embed(mock_sdk, values_list: list[list[float]]):
    """Set up an OpenAI mock to return given embedding values."""
    data = []
    for values in values_list:
        obj = MagicMock()
        obj.embedding = values
        data.append(obj)
    response = MagicMock()
    response.data = data
    mock_sdk.OpenAI.return_value.embeddings.create.return_value = response


def _mock_ollama_embed(mock_sdk, values_list: list[list[float]]):
    """Set up an Ollama mock to return given embedding values."""
    mock_sdk.Client.return_value.embed.return_value = {
        "embeddings": values_list
    }


def _mock_voyage_embed(mock_sdk, values_list: list[list[float]]):
    """Set up a Voyage mock to return given embedding values."""
    result_obj = MagicMock()
    result_obj.embeddings = values_list
    mock_sdk.Client.return_value.embed.return_value = result_obj


def _make_gemini(mock_genai, mock_types, **kwargs):
    """Create a GeminiProvider with mocks applied."""
    return GeminiProvider(api_key=kwargs.pop("api_key", "key"), **kwargs)


def _make_openai(mock_sdk, _unused, **kwargs):
    """Create an OpenAIProvider with mocks applied."""
    return OpenAIProvider(api_key=kwargs.pop("api_key", "key"), **kwargs)


def _make_ollama(mock_sdk, _unused, **kwargs):
    """Create an OllamaProvider with mocks applied."""
    kwargs.pop("api_key", None)
    return OllamaProvider(**kwargs)


def _make_voyage(mock_sdk, _unused, **kwargs):
    """Create a VoyageProvider with mocks applied."""
    return VoyageProvider(api_key=kwargs.pop("api_key", "key"), **kwargs)


def _fail_gemini_embed(mock_genai, error):
    mock_genai.Client.return_value.models.embed_content.side_effect = error


def _fail_openai_embed(mock_sdk, error):
    mock_sdk.OpenAI.return_value.embeddings.create.side_effect = error


def _fail_ollama_embed(mock_sdk, error):
    mock_sdk.Client.return_value.embed.side_effect = error


def _fail_voyage_embed(mock_sdk, error):
    mock_sdk.Client.return_value.embed.side_effect = error


# Provider test configurations: (patches, factory, mock_setup, fail_setup, defaults)
_PROVIDER_CONFIGS = {
    "gemini": {
        "patches": ["semantic_memory.embedding.types", "semantic_memory.embedding.genai"],
        "factory": _make_gemini,
        "mock_embed": _mock_gemini_embed,
        "fail_embed": _fail_gemini_embed,
        "defaults": {"model": "gemini-embedding-001", "dimensions": 768, "provider_name": "gemini"},
        "embed_error_match": "Gemini embedding failed",
        "batch_error_match": "Gemini batch embedding failed",
        # mock index: which patched arg is the main SDK mock
        "sdk_idx": 1,
    },
    "openai": {
        "patches": ["semantic_memory.embedding.openai_sdk"],
        "factory": _make_openai,
        "mock_embed": _mock_openai_embed,
        "fail_embed": _fail_openai_embed,
        "defaults": {"model": "text-embedding-3-small", "dimensions": 1536, "provider_name": "openai"},
        "embed_error_match": "OpenAI embedding failed",
        "batch_error_match": "OpenAI batch embedding failed",
        "sdk_idx": 0,
    },
    "ollama": {
        "patches": ["semantic_memory.embedding.ollama_sdk"],
        "factory": _make_ollama,
        "mock_embed": _mock_ollama_embed,
        "fail_embed": _fail_ollama_embed,
        "defaults": {"model": "nomic-embed-text", "dimensions": 768, "provider_name": "ollama"},
        "embed_error_match": "Ollama embedding failed",
        "batch_error_match": "Ollama batch embedding failed",
        "sdk_idx": 0,
    },
    "voyage": {
        "patches": ["semantic_memory.embedding.voyageai_sdk"],
        "factory": _make_voyage,
        "mock_embed": _mock_voyage_embed,
        "fail_embed": _fail_voyage_embed,
        "defaults": {"model": "voyage-3", "dimensions": 1024, "provider_name": "voyage"},
        "embed_error_match": "Voyage embedding failed",
        "batch_error_match": "Voyage batch embedding failed",
        "sdk_idx": 0,
    },
}

_ALL_PROVIDERS = list(_PROVIDER_CONFIGS.keys())


class _ProviderTestBase:
    """Mixin that applies the correct patches for each provider parametrization."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self, request, provider_name):
        cfg = _PROVIDER_CONFIGS[provider_name]
        patchers = [patch(p) for p in cfg["patches"]]
        mocks = [p.start() for p in patchers]
        # Store on instance for test methods
        self._sdk_mock = mocks[cfg["sdk_idx"]]
        self._all_mocks = mocks
        self._cfg = cfg
        yield
        for p in patchers:
            p.stop()

    def _create(self, **kwargs):
        return self._cfg["factory"](self._all_mocks[self._cfg["sdk_idx"]], self._all_mocks[0], **kwargs)

    def _setup_embed(self, values_list):
        self._cfg["mock_embed"](self._all_mocks[self._cfg["sdk_idx"]], values_list)

    def _setup_fail(self, error):
        self._cfg["fail_embed"](self._all_mocks[self._cfg["sdk_idx"]], error)


# ---------------------------------------------------------------------------
# Parametrized: Init tests (default model, custom model, dimensions, provider_name)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_name", _ALL_PROVIDERS)
class TestProviderInit(_ProviderTestBase):
    def test_default_model(self, provider_name):
        provider = self._create()
        assert provider.model_name == self._cfg["defaults"]["model"]

    def test_custom_model(self, provider_name):
        provider = self._create(model="custom-model")
        assert provider.model_name == "custom-model"

    def test_default_dimensions(self, provider_name):
        provider = self._create()
        assert provider.dimensions == self._cfg["defaults"]["dimensions"]

    def test_custom_dimensions(self, provider_name):
        provider = self._create(dimensions=384)
        assert provider.dimensions == 384

    def test_provider_name(self, provider_name):
        provider = self._create()
        assert provider.provider_name == self._cfg["defaults"]["provider_name"]


# ---------------------------------------------------------------------------
# Parametrized: embed() tests (returns ndarray, correct values, wraps errors)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_name", _ALL_PROVIDERS)
class TestProviderEmbed(_ProviderTestBase):
    def test_returns_ndarray(self, provider_name):
        self._setup_embed([[0.1, 0.2, 0.3]])
        provider = self._create(dimensions=3)
        result = provider.embed("test text")
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32

    def test_returns_correct_values(self, provider_name):
        self._setup_embed([[1.0, 2.0, 3.0]])
        provider = self._create(dimensions=3)
        result = provider.embed("hello")
        np.testing.assert_array_almost_equal(result, [1.0, 2.0, 3.0])

    def test_wraps_errors(self, provider_name):
        provider = self._create()
        self._setup_fail(Exception("API failure"))
        with pytest.raises(EmbeddingError, match=self._cfg["embed_error_match"]):
            provider.embed("test")


# ---------------------------------------------------------------------------
# Parametrized: embed_batch() tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_name", _ALL_PROVIDERS)
class TestProviderEmbedBatch(_ProviderTestBase):
    def test_returns_list_of_ndarrays(self, provider_name):
        self._setup_embed([[0.1, 0.2], [0.3, 0.4]])
        provider = self._create(dimensions=2)
        result = provider.embed_batch(["text1", "text2"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(v, np.ndarray) for v in result)

    def test_returns_correct_values(self, provider_name):
        self._setup_embed([[1.0, 2.0], [3.0, 4.0]])
        provider = self._create(dimensions=2)
        result = provider.embed_batch(["a", "b"])
        np.testing.assert_array_almost_equal(result[0], [1.0, 2.0])
        np.testing.assert_array_almost_equal(result[1], [3.0, 4.0])

    def test_wraps_errors(self, provider_name):
        provider = self._create()
        self._setup_fail(Exception("batch fail"))
        with pytest.raises(EmbeddingError, match=self._cfg["batch_error_match"]):
            provider.embed_batch(["a", "b"])

    def test_float32_dtype(self, provider_name):
        self._setup_embed([[0.5, 0.6]])
        provider = self._create(dimensions=2)
        result = provider.embed_batch(["text"])
        assert result[0].dtype == np.float32


# ---------------------------------------------------------------------------
# Parametrized: Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_name", _ALL_PROVIDERS)
class TestProviderProtocolConformance(_ProviderTestBase):
    def test_isinstance_check(self, provider_name):
        provider = self._create()
        assert isinstance(provider, EmbeddingProvider)


# ---------------------------------------------------------------------------
# Gemini-specific tests (task_type mapping, output_dimensionality, old SDK)
# ---------------------------------------------------------------------------


class TestGeminiSpecific:
    @patch("semantic_memory.embedding.types")
    @patch("semantic_memory.embedding.genai")
    def test_raises_runtime_error_on_old_sdk(self, mock_genai, mock_types):
        """Should raise RuntimeError if SDK doesn't support task_type."""
        mock_types.EmbedContentConfig.side_effect = TypeError("no task_type")
        with pytest.raises(RuntimeError, match="google-genai SDK does not support task_type"):
            GeminiProvider(api_key="key")

    def test_task_type_map_has_document_and_query(self):
        """TASK_TYPE_MAP should map 'document' and 'query'."""
        assert GeminiProvider.TASK_TYPE_MAP == {
            "document": "RETRIEVAL_DOCUMENT",
            "query": "RETRIEVAL_QUERY",
        }

    @patch("semantic_memory.embedding.types")
    @patch("semantic_memory.embedding.genai")
    def test_embed_default_task_type_is_query(self, mock_genai, mock_types):
        """embed() default task_type should be 'query' -> RETRIEVAL_QUERY."""
        mock_types.EmbedContentConfig = lambda **kw: SimpleNamespace(**kw)
        _mock_gemini_embed(mock_genai, [[0.1]])

        provider = GeminiProvider(api_key="key", dimensions=1)
        provider.embed("test")

        call_kwargs = mock_genai.Client.return_value.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_QUERY"

    @patch("semantic_memory.embedding.types")
    @patch("semantic_memory.embedding.genai")
    def test_embed_document_task_type(self, mock_genai, mock_types):
        """embed(task_type='document') should use RETRIEVAL_DOCUMENT."""
        mock_types.EmbedContentConfig = lambda **kw: SimpleNamespace(**kw)
        _mock_gemini_embed(mock_genai, [[0.1]])

        provider = GeminiProvider(api_key="key", dimensions=1)
        provider.embed("test", task_type="document")

        call_kwargs = mock_genai.Client.return_value.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_DOCUMENT"

    @patch("semantic_memory.embedding.types")
    @patch("semantic_memory.embedding.genai")
    def test_embed_passes_output_dimensionality(self, mock_genai, mock_types):
        """embed() should pass output_dimensionality in the config."""
        mock_types.EmbedContentConfig = lambda **kw: SimpleNamespace(**kw)
        _mock_gemini_embed(mock_genai, [[0.1] * 384])

        provider = GeminiProvider(api_key="key", dimensions=384)
        provider.embed("test")

        call_kwargs = mock_genai.Client.return_value.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.output_dimensionality == 384

    @patch("semantic_memory.embedding.types")
    @patch("semantic_memory.embedding.genai")
    def test_embed_invalid_task_type_raises(self, mock_genai, _mock_types):
        """embed() with an unknown task_type should raise EmbeddingError."""
        provider = GeminiProvider(api_key="key")
        with pytest.raises(EmbeddingError, match="Unknown task_type"):
            provider.embed("test", task_type="invalid")

    @patch("semantic_memory.embedding.types")
    @patch("semantic_memory.embedding.genai")
    def test_embed_batch_default_task_type_is_document(self, mock_genai, mock_types):
        """embed_batch() default task_type should be 'document'."""
        mock_types.EmbedContentConfig = lambda **kw: SimpleNamespace(**kw)
        _mock_gemini_embed(mock_genai, [[0.1]])

        provider = GeminiProvider(api_key="key", dimensions=1)
        provider.embed_batch(["text"])

        call_kwargs = mock_genai.Client.return_value.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_DOCUMENT"

    @patch("semantic_memory.embedding.types")
    @patch("semantic_memory.embedding.genai")
    def test_embed_batch_invalid_task_type_raises(self, mock_genai, _mock_types):
        """embed_batch() with unknown task_type should raise EmbeddingError."""
        provider = GeminiProvider(api_key="key")
        with pytest.raises(EmbeddingError, match="Unknown task_type"):
            provider.embed_batch(["test"], task_type="bogus")


# ---------------------------------------------------------------------------
# OpenAI-specific tests (ignores task_type, SDK missing)
# ---------------------------------------------------------------------------


class TestOpenAISpecific:
    def test_raises_runtime_error_when_sdk_missing(self):
        """Should raise RuntimeError when openai SDK is not installed."""
        with patch("semantic_memory.embedding.openai_sdk", None):
            with pytest.raises(RuntimeError, match="openai SDK is required"):
                OpenAIProvider(api_key="key")

    @patch("semantic_memory.embedding.openai_sdk")
    def test_embed_ignores_task_type(self, mock_sdk):
        """embed() should accept task_type but not fail on any value."""
        _mock_openai_embed(mock_sdk, [[0.1]])
        provider = OpenAIProvider(api_key="key", dimensions=1)
        provider.embed("test", task_type="document")
        provider.embed("test", task_type="query")
        provider.embed("test", task_type="arbitrary")


# ---------------------------------------------------------------------------
# Ollama-specific tests (host config, env host, SDK missing)
# ---------------------------------------------------------------------------


class TestOllamaSpecific:
    @patch("semantic_memory.embedding.ollama_sdk")
    def test_creates_client_with_host(self, mock_sdk):
        """OllamaProvider should pass host to Client when provided."""
        OllamaProvider(host="http://localhost:11434")
        mock_sdk.Client.assert_called_once_with(host="http://localhost:11434")

    @patch("semantic_memory.embedding.ollama_sdk")
    def test_creates_client_with_env_host(self, mock_sdk):
        """OllamaProvider should use OLLAMA_HOST env var as fallback."""
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://remote:11434"}):
            OllamaProvider()
        mock_sdk.Client.assert_called_once_with(host="http://remote:11434")

    def test_raises_runtime_error_when_sdk_missing(self):
        """Should raise RuntimeError when ollama SDK is not installed."""
        with patch("semantic_memory.embedding.ollama_sdk", None):
            with pytest.raises(RuntimeError, match="ollama SDK is required"):
                OllamaProvider()

    @patch("semantic_memory.embedding.ollama_sdk")
    def test_embed_ignores_task_type(self, mock_sdk):
        """embed() should accept task_type without error."""
        _mock_ollama_embed(mock_sdk, [[0.1]])
        provider = OllamaProvider(dimensions=1)
        provider.embed("test", task_type="document")
        provider.embed("test", task_type="query")


# ---------------------------------------------------------------------------
# Voyage-specific tests (input_type passthrough, output_dimension, SDK missing)
# ---------------------------------------------------------------------------


class TestVoyageSpecific:
    def test_raises_runtime_error_when_sdk_missing(self):
        """Should raise RuntimeError when voyageai SDK is not installed."""
        with patch("semantic_memory.embedding.voyageai_sdk", None):
            with pytest.raises(RuntimeError, match="voyageai SDK is required"):
                VoyageProvider(api_key="key")

    def test_task_type_map_has_query_and_document(self):
        """TASK_TYPE_MAP should map 'query' and 'document'."""
        assert VoyageProvider.TASK_TYPE_MAP == {
            "query": "query",
            "document": "document",
        }

    @patch("semantic_memory.embedding.voyageai_sdk")
    def test_embed_passes_input_type_query(self, mock_sdk):
        """embed(task_type='query') should pass input_type='query' to Voyage."""
        _mock_voyage_embed(mock_sdk, [[0.1]])
        provider = VoyageProvider(api_key="key", dimensions=1)
        provider.embed("test", task_type="query")
        call_kwargs = mock_sdk.Client.return_value.embed.call_args
        assert call_kwargs.kwargs.get("input_type") == "query"

    @patch("semantic_memory.embedding.voyageai_sdk")
    def test_embed_passes_input_type_document(self, mock_sdk):
        """embed(task_type='document') should pass input_type='document' to Voyage."""
        _mock_voyage_embed(mock_sdk, [[0.1]])
        provider = VoyageProvider(api_key="key", dimensions=1)
        provider.embed("test", task_type="document")
        call_kwargs = mock_sdk.Client.return_value.embed.call_args
        assert call_kwargs.kwargs.get("input_type") == "document"

    @patch("semantic_memory.embedding.voyageai_sdk")
    def test_embed_passes_output_dimension(self, mock_sdk):
        """embed() should pass output_dimension to the Voyage API."""
        _mock_voyage_embed(mock_sdk, [[0.1] * 512])
        provider = VoyageProvider(api_key="key", dimensions=512)
        provider.embed("test")
        call_kwargs = mock_sdk.Client.return_value.embed.call_args
        assert call_kwargs.kwargs.get("output_dimension") == 512

    @patch("semantic_memory.embedding.voyageai_sdk")
    def test_embed_batch_default_task_type_is_document(self, mock_sdk):
        """embed_batch() default task_type should be 'document'."""
        _mock_voyage_embed(mock_sdk, [[0.1]])
        provider = VoyageProvider(api_key="key", dimensions=1)
        provider.embed_batch(["text"])
        call_kwargs = mock_sdk.Client.return_value.embed.call_args
        assert call_kwargs.kwargs.get("input_type") == "document"


# ---------------------------------------------------------------------------
# Helper: Fake provider for NormalizingWrapper tests
# ---------------------------------------------------------------------------


class _FakeProvider:
    """Minimal EmbeddingProvider for testing NormalizingWrapper."""

    def __init__(self, embed_result=None, batch_result=None):
        self._embed_result = embed_result
        self._batch_result = batch_result

    @property
    def dimensions(self) -> int:
        return 5

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fake-model-v1"

    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        return self._embed_result

    def embed_batch(
        self, texts: list[str], task_type: str = "document"
    ) -> list[np.ndarray]:
        return self._batch_result


# ---------------------------------------------------------------------------
# NormalizingWrapper tests
# ---------------------------------------------------------------------------


class TestNormalizingWrapperEmbed:
    def test_normalizes_to_unit_length(self):
        """NormalizingWrapper.embed() should L2-normalize the vector."""
        # [3, 4, 0, 0, 0] has norm 5.0
        raw = np.array([3.0, 4.0, 0.0, 0.0, 0.0], dtype=np.float32)
        inner = _FakeProvider(embed_result=raw)
        wrapper = NormalizingWrapper(inner)

        result = wrapper.embed("hello")
        norm = float(np.linalg.norm(result))
        assert abs(norm - 1.0) < 1e-6, f"Expected unit norm, got {norm}"
        np.testing.assert_array_almost_equal(
            result, [0.6, 0.8, 0.0, 0.0, 0.0]
        )

    def test_zero_vector_raises_embedding_error(self):
        """NormalizingWrapper.embed() should raise EmbeddingError for zero vectors."""
        raw = np.zeros(5, dtype=np.float32)
        inner = _FakeProvider(embed_result=raw)
        wrapper = NormalizingWrapper(inner)

        with pytest.raises(EmbeddingError, match="Zero vector detected"):
            wrapper.embed("empty")

    def test_near_zero_vector_raises_embedding_error(self):
        """Vectors with norm < 1e-9 should be treated as zero vectors."""
        raw = np.array([1e-10, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        inner = _FakeProvider(embed_result=raw)
        wrapper = NormalizingWrapper(inner)

        with pytest.raises(EmbeddingError, match="Zero vector detected"):
            wrapper.embed("tiny")


class TestNormalizingWrapperEmbedBatch:
    def test_normalizes_each_vector_independently(self):
        """embed_batch() should normalize each vector independently."""
        batch = [
            np.array([3.0, 4.0, 0.0], dtype=np.float32),  # norm 5
            np.array([0.0, 0.0, 2.0], dtype=np.float32),  # norm 2
        ]
        inner = _FakeProvider(batch_result=batch)
        wrapper = NormalizingWrapper(inner)

        results = wrapper.embed_batch(["a", "b"])
        assert len(results) == 2

        norm0 = float(np.linalg.norm(results[0]))
        norm1 = float(np.linalg.norm(results[1]))
        assert abs(norm0 - 1.0) < 1e-6
        assert abs(norm1 - 1.0) < 1e-6
        np.testing.assert_array_almost_equal(results[0], [0.6, 0.8, 0.0])
        np.testing.assert_array_almost_equal(results[1], [0.0, 0.0, 1.0])

    def test_zero_vector_in_batch_raises_embedding_error(self):
        """embed_batch() should raise if any vector in the batch is zero."""
        batch = [
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
            np.zeros(3, dtype=np.float32),
        ]
        inner = _FakeProvider(batch_result=batch)
        wrapper = NormalizingWrapper(inner)

        with pytest.raises(EmbeddingError, match="Zero vector detected"):
            wrapper.embed_batch(["ok", "zero"])


class TestNormalizingWrapperProperties:
    def test_dimensions_forwarded(self):
        """dimensions should be forwarded from the inner provider."""
        inner = _FakeProvider()
        wrapper = NormalizingWrapper(inner)
        assert wrapper.dimensions == 5

    def test_provider_name_forwarded(self):
        """provider_name should be forwarded from the inner provider."""
        inner = _FakeProvider()
        wrapper = NormalizingWrapper(inner)
        assert wrapper.provider_name == "fake"

    def test_model_name_forwarded(self):
        """model_name should be forwarded from the inner provider."""
        inner = _FakeProvider()
        wrapper = NormalizingWrapper(inner)
        assert wrapper.model_name == "fake-model-v1"

    def test_satisfies_embedding_provider_protocol(self):
        """NormalizingWrapper should satisfy EmbeddingProvider protocol."""
        inner = _FakeProvider()
        wrapper = NormalizingWrapper(inner)
        assert isinstance(wrapper, EmbeddingProvider)


# ---------------------------------------------------------------------------
# create_provider tests
# ---------------------------------------------------------------------------


class TestCreateProvider:
    @patch("semantic_memory.embedding._load_dotenv_once")
    def test_returns_none_when_env_var_missing(self, _mock_dotenv):
        """create_provider should return None when the required API key is missing."""
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = create_provider(config)
        assert result is None

    @patch("semantic_memory.embedding._load_dotenv_once")
    def test_returns_none_for_unknown_provider(self, _mock_dotenv):
        """create_provider should return None for an unknown provider name."""
        config = {
            "memory_embedding_provider": "unknown-provider",
            "memory_embedding_model": "some-model",
        }
        with patch.dict(os.environ, {"UNKNOWN_API_KEY": "key"}, clear=False):
            result = create_provider(config)
        assert result is None

    @patch("semantic_memory.embedding._load_dotenv_once")
    @patch("semantic_memory.embedding.GeminiProvider")
    def test_returns_normalizing_wrapper_for_gemini(self, mock_gemini_cls, _mock_dotenv):
        """create_provider should return a NormalizingWrapper wrapping GeminiProvider."""
        mock_gemini_cls.return_value = _FakeProvider()
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            result = create_provider(config)

        assert isinstance(result, NormalizingWrapper)
        mock_gemini_cls.assert_called_once_with(
            api_key="test-key", model="gemini-embedding-001"
        )

    @patch("semantic_memory.embedding._load_dotenv_once")
    @patch("semantic_memory.embedding.GeminiProvider", side_effect=Exception("SDK error"))
    def test_returns_none_on_construction_error(self, mock_gemini_cls, _mock_dotenv):
        """create_provider should return None if provider construction fails."""
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            result = create_provider(config)
        assert result is None

    @patch("semantic_memory.embedding._load_dotenv_once")
    def test_returns_none_for_voyage_without_key(self, _mock_dotenv):
        """create_provider should return None when VOYAGE_API_KEY is missing."""
        config = {
            "memory_embedding_provider": "voyage",
            "memory_embedding_model": "voyage-3",
        }
        env = {k: v for k, v in os.environ.items() if k != "VOYAGE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = create_provider(config)
        assert result is None

    @patch("semantic_memory.embedding._load_dotenv_once")
    def test_returns_none_for_openai_without_key(self, _mock_dotenv):
        """create_provider should return None when OPENAI_API_KEY is missing."""
        config = {
            "memory_embedding_provider": "openai",
            "memory_embedding_model": "text-embedding-3-small",
        }
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = create_provider(config)
        assert result is None

    @patch("semantic_memory.embedding._load_dotenv_once")
    @patch("semantic_memory.embedding.OllamaProvider")
    def test_returns_normalizing_wrapper_for_ollama(self, mock_ollama_cls, _mock_dotenv):
        """create_provider should return a NormalizingWrapper wrapping OllamaProvider."""
        mock_ollama_cls.return_value = _FakeProvider()
        config = {
            "memory_embedding_provider": "ollama",
            "memory_embedding_model": "nomic-embed-text",
        }
        result = create_provider(config)
        assert isinstance(result, NormalizingWrapper)
        mock_ollama_cls.assert_called_once_with(model="nomic-embed-text")

    @patch("semantic_memory.embedding._load_dotenv_once")
    @patch("semantic_memory.embedding.OpenAIProvider")
    def test_returns_normalizing_wrapper_for_openai(self, mock_openai_cls, _mock_dotenv):
        """create_provider should return a NormalizingWrapper wrapping OpenAIProvider."""
        mock_openai_cls.return_value = _FakeProvider()
        config = {
            "memory_embedding_provider": "openai",
            "memory_embedding_model": "text-embedding-3-small",
        }
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            result = create_provider(config)
        assert isinstance(result, NormalizingWrapper)
        mock_openai_cls.assert_called_once_with(
            api_key="test-key", model="text-embedding-3-small"
        )

    @patch("semantic_memory.embedding._load_dotenv_once")
    @patch("semantic_memory.embedding.VoyageProvider")
    def test_returns_normalizing_wrapper_for_voyage(self, mock_voyage_cls, _mock_dotenv):
        """create_provider should return a NormalizingWrapper wrapping VoyageProvider."""
        mock_voyage_cls.return_value = _FakeProvider()
        config = {
            "memory_embedding_provider": "voyage",
            "memory_embedding_model": "voyage-3",
        }
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "test-key"}, clear=False):
            result = create_provider(config)
        assert isinstance(result, NormalizingWrapper)
        mock_voyage_cls.assert_called_once_with(
            api_key="test-key", model="voyage-3"
        )

    @patch("semantic_memory.embedding.np", None)
    def test_returns_none_when_numpy_unavailable(self):
        """create_provider should return None when numpy is not installed."""
        config = {
            "memory_embedding_provider": "gemini",
            "memory_embedding_model": "gemini-embedding-001",
        }
        result = create_provider(config)
        assert result is None
