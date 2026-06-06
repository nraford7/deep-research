import config, dispatch

class FakeChat:
    def __init__(self): self.kwargs = None
    class _Msg:
        def __init__(self, content): self.message = type("M", (), {"content": content})
    def create(self, **kw):
        self.kwargs = kw
        return type("R", (), {"choices": [FakeChat._Msg("OPENAI-REPORT")]})

class FakeOpenAI:
    def __init__(self): self.chat = type("C", (), {"completions": FakeChat()})()

class FakeAnthropic:
    def __init__(self): self.kwargs = None; self.messages = self
    def create(self, **kw):
        self.kwargs = kw
        return type("R", (), {"content": [type("B", (), {"text": "ANTHROPIC-REPORT"})]})

class FakeOverloadError(Exception):
    status_code = 503


class FakeGemini:
    def __init__(self, fail_first=0):
        self.calls = []; self.fail_first = fail_first
        self.models = self
    def generate_content(self, **kw):
        self.calls.append(kw["model"])
        if len(self.calls) <= self.fail_first:
            raise FakeOverloadError("503 overloaded")
        return type("R", (), {"text": "GEMINI-REPORT"})

def test_call_openai_passes_max_tokens_and_system(tmp_path):
    prov = config.Provider("ds", "openai", "k", "deepseek-v4-pro", base_url="https://x", max_tokens=4096)
    at = config.AgentType("academic", "STRAT", "SYS")
    client = FakeOpenAI()
    out = tmp_path / "o.md"
    text = dispatch.call_openai(client, prov, at, "PROMPT", out)
    assert text == "OPENAI-REPORT" and out.read_text() == "OPENAI-REPORT"
    kw = client.chat.completions.kwargs
    assert kw["model"] == "deepseek-v4-pro" and kw["max_tokens"] == 4096
    assert kw["messages"][0] == {"role": "system", "content": "SYS"}
    assert kw["messages"][1]["content"] == "PROMPT"

def test_call_anthropic_uses_max_tokens_no_base_url(tmp_path):
    prov = config.Provider("claude", "anthropic", "k", "claude-opus-4-20250514", max_tokens=120000)
    at = config.AgentType("academic", "STRAT", "SYS")
    client = FakeAnthropic()
    text = dispatch.call_anthropic(client, prov, at, "PROMPT", tmp_path / "a.md")
    assert text == "ANTHROPIC-REPORT" and client.kwargs["max_tokens"] == 120000
    assert client.kwargs["model"] == "claude-opus-4-20250514"
    assert client.kwargs["system"] == "SYS"
    assert all(m["role"] != "system" for m in client.kwargs["messages"])

def test_call_gemini_uses_max_output_tokens_and_walks_fallback(tmp_path):
    prov = config.Provider("g", "gemini", "k", "gemini-2.5-pro", max_tokens=65536,
                           fallback_models=("gemini-2.5-flash",))
    at = config.AgentType("grey-literature", "STRAT", "SYS")
    client = FakeGemini(fail_first=1)
    text = dispatch.call_gemini(client, prov, at, "PROMPT", tmp_path / "g.md")
    assert text == "GEMINI-REPORT"
    assert client.calls == ["gemini-2.5-pro", "gemini-2.5-flash"]


# Fix 12: overload-shaped errors walk the chain; non-overload errors propagate immediately

class FakeGeminiAlwaysOverloaded:
    """All models raise an overload-shaped error (status_code=503)."""
    def __init__(self):
        self.calls = []
        self.models = self

    def generate_content(self, **kw):
        self.calls.append(kw["model"])
        raise FakeOverloadError("overloaded")


def test_call_gemini_all_overloaded_raises_runtime_error(tmp_path):
    """When every model raises an overload error, call_gemini raises RuntimeError mentioning 'All Gemini models failed'."""
    prov = config.Provider("g", "gemini", "k", "gemini-2.5-pro", max_tokens=65536,
                           fallback_models=("gemini-2.5-flash",))
    at = config.AgentType("grey-literature", "STRAT", "SYS")
    client = FakeGeminiAlwaysOverloaded()
    try:
        dispatch.call_gemini(client, prov, at, "PROMPT", tmp_path / "g.md")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "All Gemini models failed" in str(e)
    # Both models were attempted (walked the fallback chain)
    assert client.calls == ["gemini-2.5-pro", "gemini-2.5-flash"]


class FakeGeminiNonOverload:
    """Raises a plain ValueError (non-overload) on every call."""
    def __init__(self):
        self.calls = []
        self.models = self

    def generate_content(self, **kw):
        self.calls.append(kw["model"])
        raise ValueError("bad key")


def test_call_gemini_non_overload_propagates_immediately(tmp_path):
    """A non-overload error must propagate immediately without trying fallback models."""
    prov = config.Provider("g", "gemini", "k", "gemini-2.5-pro", max_tokens=65536,
                           fallback_models=("gemini-2.5-flash",))
    at = config.AgentType("grey-literature", "STRAT", "SYS")
    client = FakeGeminiNonOverload()
    try:
        dispatch.call_gemini(client, prov, at, "PROMPT", tmp_path / "g.md")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "bad key" in str(e)
    # Only the first model was tried — fallback NOT attempted
    assert client.calls == ["gemini-2.5-pro"]


def test_call_openai_empty_response_raises(tmp_path):
    class _EmptyChat:
        def create(self, **kw):
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": None})})]})
    client = type("X", (), {"chat": type("Y", (), {"completions": _EmptyChat()})()})()
    prov = config.Provider("p", "openai", "k", "m")
    at = config.AgentType("academic", "S", "SYS")
    import pytest
    with pytest.raises(RuntimeError, match="empty response"):
        dispatch.call_openai(client, prov, at, "PROMPT", tmp_path / "o.md")


def test_call_anthropic_empty_content_list_raises(tmp_path):
    class _C:
        messages = None
        def create(self, **kw):
            return type("R", (), {"content": []})
    client = _C(); client.messages = client
    prov = config.Provider("p", "anthropic", "k", "m")
    at = config.AgentType("academic", "S", "SYS")
    import pytest
    with pytest.raises(RuntimeError, match="empty response"):
        dispatch.call_anthropic(client, prov, at, "PROMPT", tmp_path / "a.md")

def test_call_openai_empty_choices_raises(tmp_path):
    class _Chat:
        def create(self, **kw): return type("R", (), {"choices": []})
    client = type("X", (), {"chat": type("Y", (), {"completions": _Chat()})()})()
    prov = config.Provider("p", "openai", "k", "m")
    at = config.AgentType("academic", "S", "SYS")
    import pytest
    with pytest.raises(RuntimeError, match="empty response"):
        dispatch.call_openai(client, prov, at, "PROMPT", tmp_path / "o.md")


def test_call_cli_generic_pipes_system_and_prompt(tmp_path):
    # 'cat' echoes stdin; generic path sends "SYS\n\nPROMPT"
    prov = config.Provider("sub", "cli", "", "", command="cat")
    at = config.AgentType("academic", "STRAT", "SYS")
    out = tmp_path / "o.md"
    text = dispatch.call_cli(None, prov, at, "PROMPT", out)
    assert text == "SYS\n\nPROMPT" and out.read_text() == "SYS\n\nPROMPT"

def test_call_cli_scrubs_api_keys_from_subprocess_env(tmp_path, monkeypatch):
    # a script that reports both ANTHROPIC_API_KEY and OPENAI_API_KEY values
    script = tmp_path / "probe.sh"
    script.write_text('#!/bin/sh\necho "A=$ANTHROPIC_API_KEY|O=$OPENAI_API_KEY"\n')
    script.chmod(0o755)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic-should-be-scrubbed")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-should-be-scrubbed")
    prov = config.Provider("sub", "cli", "", "", command=str(script))
    at = config.AgentType("academic", "S", "SYS")
    text = dispatch.call_cli(None, prov, at, "PROMPT", tmp_path / "o.md")
    assert "sk-anthropic-should-be-scrubbed" not in text
    assert "sk-openai-should-be-scrubbed" not in text
    assert "A=|O=" in text

def test_call_cli_nonzero_exit_raises(tmp_path):
    script = tmp_path / "fail.sh"
    script.write_text('#!/bin/sh\necho "boom" >&2\nexit 3\n'); script.chmod(0o755)
    prov = config.Provider("sub", "cli", "", "", command=str(script))
    at = config.AgentType("academic", "S", "SYS")
    import pytest
    with pytest.raises(RuntimeError, match="exited 3"):
        dispatch.call_cli(None, prov, at, "PROMPT", tmp_path / "o.md")

def test_cli_argv_builder_claude_and_codex():
    at = config.AgentType("real-time", "S", "SYSPROMPT")
    pc = config.Provider("c", "cli", "", "claude-opus-4-20250514", command="/usr/local/bin/claude")
    argv, stdin = dispatch._cli_argv_and_input(pc, at, "USERPROMPT")
    assert argv[:4] == ["/usr/local/bin/claude", "-p", "--system-prompt", "SYSPROMPT"]
    assert "--model" in argv and "claude-opus-4-20250514" in argv and stdin == "USERPROMPT"
    px = config.Provider("x", "cli", "", "", command="codex")
    argv2, stdin2 = dispatch._cli_argv_and_input(px, at, "USERPROMPT")
    assert argv2[:2] == ["codex", "exec"] and "--model" not in argv2 and stdin2 == "SYSPROMPT\n\nUSERPROMPT"


def test_cli_extra_args_appended():
    at = config.AgentType("academic", "S", "SYS")
    p = config.Provider("c", "cli", "", "", command="claude", extra_args=("--allowedTools", "WebSearch"))
    argv, _ = dispatch._cli_argv_and_input(p, at, "PROMPT")
    assert argv[-2:] == ["--allowedTools", "WebSearch"]


def test_call_cli_scrubs_api_keys_from_subprocess_env_both_keys(tmp_path, monkeypatch):
    # Probe both ANTHROPIC_API_KEY and OPENAI_API_KEY
    script = tmp_path / "probe2.sh"
    script.write_text('#!/bin/sh\necho "A=$ANTHROPIC_API_KEY|O=$OPENAI_API_KEY"\n')
    script.chmod(0o755)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret")
    prov = config.Provider("sub", "cli", "", "", command=str(script))
    at = config.AgentType("academic", "S", "SYS")
    text = dispatch.call_cli(None, prov, at, "PROMPT", tmp_path / "o.md")
    assert "sk-anthropic-secret" not in text
    assert "sk-openai-secret" not in text
    assert "A=|O=" in text
