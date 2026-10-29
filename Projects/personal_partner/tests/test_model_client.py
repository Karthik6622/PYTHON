from src import model_client


def test_think_blocks_are_removed_from_a_stream():
    chunks = ["<th", "ink>plan the ", "answer</thi", "nk>\n\nHello ", "there"]
    assert "".join(model_client.strip_think_blocks(iter(chunks))) == "Hello there"
    assert "".join(model_client.strip_think_blocks(iter(["Plain <b>text</b> a < b"]))) == "Plain <b>text</b> a < b"


def test_unfinished_think_block_is_never_spoken():
    assert "".join(model_client.strip_think_blocks(iter(["Hi <think>secret"]))) == "Hi "


def test_error_messages_are_specific():
    class APITimeoutError(Exception):
        pass

    assert "too long" in model_client.describe_model_error(APITimeoutError())
    assert "empty reply" in model_client.describe_model_error(RuntimeError("The configured model returned an empty response."))
    assert "couldn't reply" in model_client.describe_model_error(RuntimeError("x"))
    assert "Add NVIDIA_API_KEY" in model_client.describe_model_error(model_client.ModelConfigurationError("Add NVIDIA_API_KEY"))


def test_timeout_fails_fast_instead_of_trying_every_variant(monkeypatch):
    class APITimeoutError(Exception):
        pass

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            raise APITimeoutError("slow")

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(model_client, "get_model_settings", lambda: model_client.ModelSettings("k", None, "m", 0.5, 500))
    monkeypatch.setattr(model_client, "_openai_client", lambda settings: FakeClient())
    try:
        list(model_client.stream_completion([{"role": "user", "content": "hi"}]))
    except APITimeoutError:
        pass
    else:
        raise AssertionError("expected the timeout to surface")
    assert len(calls) == 1
