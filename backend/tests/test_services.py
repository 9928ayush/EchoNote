import subprocess
from types import SimpleNamespace

import httpx
import pytest

from app.services import audio, providers
from app.services.errors import ServiceError
from app.services.summary import split_text, summarize_long


@pytest.mark.parametrize("code,retryable", [(400, False), (403, False), (429, True), (503, True)])
def test_provider_error_mapping(code, retryable, monkeypatch):
    monkeypatch.setattr(providers.time, "sleep", lambda _: None)
    calls = []

    def send():
        calls.append(1)
        return httpx.Response(code, json={"error": "private upstream body"})

    with pytest.raises(ServiceError) as result:
        providers.request_json("Transcription", send)
    assert result.value.retryable == retryable
    assert "private" not in str(result.value)
    assert len(calls) == (3 if retryable else 1)


def test_provider_timeout_is_bounded(monkeypatch):
    monkeypatch.setattr(providers.time, "sleep", lambda _: None)
    calls = []

    def send():
        calls.append(1)
        raise httpx.ReadTimeout("secret URL")

    with pytest.raises(ServiceError, match="could not be reached"):
        providers.request_json("Transcription", send)
    assert len(calls) == 3


def test_gnani_contract_and_no_invented_segments(tmp_path, monkeypatch):
    for name in (
        "ALL_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "all_proxy",
        "https_proxy",
        "http_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "chunk.wav"
    path.write_bytes(b"wave")
    monkeypatch.setattr(
        providers,
        "settings",
        lambda: SimpleNamespace(
            gnani_api_key="test-key", gnani_url="https://api.vachana.ai/stt/v3"
        ),
    )

    def post(self, url, **kwargs):
        assert url.endswith("/stt/v3")
        assert kwargs["headers"] == {"X-API-Key-ID": "test-key"}
        assert kwargs["data"] == {"language_code": "hi-IN"}
        assert kwargs["files"]["audio_file"][1].read() == b"wave"
        return httpx.Response(200, json={"success": True, "transcript": " नमस्ते "})

    monkeypatch.setattr(httpx.Client, "post", post)
    assert providers.GnaniASR().transcribe(path, "hi-IN") == "नमस्ते"


def test_split_text_preserves_unicode_and_all_content():
    source = "नमस्ते दुनिया! " * 10000
    chunks = split_text(source)
    assert "".join(chunks) == source
    assert all(len(c.encode("utf-8")) <= 12000 for c in chunks)


def test_long_summary_reduces_and_heartbeats():
    calls, heartbeats = [], []

    class Provider:
        def summarize(self, text):
            calls.append(text)
            return "A concise summary."

    assert (
        summarize_long("facts " * 5000, Provider(), lambda: heartbeats.append(1))
        == "A concise summary."
    )
    assert len(calls) > 1
    assert all(len(c.encode()) <= 12000 for c in calls)
    assert len(heartbeats) == len(calls) * 2


def test_empty_transcript_fails():
    with pytest.raises(ServiceError, match="No speech"):
        summarize_long(" ", None, lambda: None)


def test_non_shrinking_summary_fails():
    class Echo:
        def summarize(self, text):
            return text

    with pytest.raises(ServiceError, match="condensed"):
        summarize_long("a" * 15000, Echo(), lambda: None)


def test_corrupt_audio_rejected(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_text("not an audio file")
    with pytest.raises(ServiceError) as result:
        audio.inspect_audio(path)
    assert not result.value.retryable


def test_audio_over_two_minutes_chunked(tmp_path):
    source = tmp_path / "long.wav"
    chunk = tmp_path / "chunk.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=125",
            "-ar",
            "16000",
            str(source),
        ],
        check=True,
    )
    assert audio.inspect_audio(source) == pytest.approx(125, abs=0.01)
    audio.extract_chunk(source, chunk, 4)
    assert audio.inspect_audio(chunk) == pytest.approx(5, abs=0.01)


def test_openai_contract_and_truncation(monkeypatch):
    for name in (
        "ALL_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "all_proxy",
        "https_proxy",
        "http_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        providers,
        "settings",
        lambda: SimpleNamespace(
            llm_api_key="test-key",
            llm_base_url="https://api.openai.com/v1",
            llm_model="gpt-4.1-mini",
        ),
    )
    finish = ["stop"]

    def post(self, url, **kwargs):
        assert url == "https://api.openai.com/v1/chat/completions"
        assert kwargs["json"]["max_completion_tokens"] == 700
        assert kwargs["json"]["messages"][1]["content"] == "source facts"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Summary"}, "finish_reason": finish[0]}]}
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    assert providers.OpenAISummary().summarize("source facts") == "Summary"
    finish[0] = "length"
    with pytest.raises(ServiceError, match="complete result"):
        providers.OpenAISummary().summarize("source facts")


def test_empty_s3_endpoint_uses_aws_default():
    from app.config import Settings

    config = Settings(_env_file=None, s3_endpoint_url="", s3_public_endpoint_url="")
    assert config.s3_endpoint_url is None
    assert config.s3_public_endpoint_url is None
