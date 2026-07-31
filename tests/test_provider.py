"""Tests for hermes-llmwiki MemoryProvider and curation engine."""

import json
import tempfile
from pathlib import Path

from hermes_llmwiki import LlmwikiMemoryProvider, curate_vault
from hermes_llmwiki.curator import (
    _archive_old_notes,
    _extract_with_llm,
    _extract_with_regex,
    _parse_json_from_response,
    _write_compiled_note,
)
from hermes_llmwiki.search import search_wiki
from hermes_llmwiki.writer import atomic_write_text, expand_path, safe_filename

# ---------------------------------------------------------------------------
# Writer tests
# ---------------------------------------------------------------------------


class TestWriter:
    def test_atomic_write_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.md"
            atomic_write_text(path, "hello world")
            assert path.read_text(encoding="utf-8") == "hello world"

    def test_atomic_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.md"
            atomic_write_text(path, "first")
            atomic_write_text(path, "second")
            assert path.read_text(encoding="utf-8") == "second"

    def test_expand_path(self):
        assert expand_path("~/test").name == "test"

    def test_safe_filename(self):
        assert safe_filename("Hello: World?") == "Hello_ World_"
        assert safe_filename("   ") == "untitled"
        assert safe_filename("normal-name") == "normal-name"


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "entities").mkdir()
            atomic_write_text(
                vault / "entities" / "Bitcoin.md",
                "# Bitcoin\n\nBitcoin is a cryptocurrency.",
            )
            results = search_wiki(vault, "cryptocurrency", engine="python")
            assert len(results) == 1
            assert "Bitcoin" in results[0]["title"]

    def test_search_empty_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            results = search_wiki(vault, "anything", engine="python")
            assert results == []

    def test_search_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "entities").mkdir()
            atomic_write_text(vault / "entities" / "Apple.md", "# Apple\n\nA fruit.")
            results = search_wiki(vault, "bitcoin", engine="python")
            assert results == []


# ---------------------------------------------------------------------------
# Curator tests
# ---------------------------------------------------------------------------


class TestCuratorExtraction:
    def test_extract_with_regex_explicit_markers(self):
        text = """
### Entity: Bitcoin
A decentralized digital currency.

### Concept: Zettelkasten
A note-taking method.
"""
        items = _extract_with_regex(text)
        assert len(items) == 2
        assert items[0]["type"] == "entity"
        assert items[0]["name"] == "Bitcoin"
        assert items[1]["type"] == "concept"

    def test_extract_with_regex_no_markers_but_substance(self):
        text = "This is a long daily note with many words. " * 20
        items = _extract_with_regex(text)
        assert len(items) == 1
        assert items[0]["type"] == "note"

    def test_extract_with_regex_trivial_note(self):
        text = "Hi. Bye."
        items = _extract_with_regex(text)
        assert items == []

    def test_extract_with_llm_mock(self):
        def fake_llm(prompt: str) -> str:
            return json.dumps(
                [
                    {
                        "type": "entity",
                        "name": "TestCoin",
                        "content": "A test cryptocurrency designed for blockchain education and development testing.",
                        "tags": ["test"],
                    },
                    {
                        "type": "concept",
                        "name": "Mocking",
                        "content": "Using fake implementations for testing purposes in software development.",
                        "tags": [],
                    },
                ]
            )

        text = "Some daily note content here."
        items = _extract_with_llm(text, fake_llm)
        assert len(items) == 2
        assert items[0]["name"] == "TestCoin"
        assert items[0]["tags"] == ["test"]

    def test_extract_with_llm_invalid_response(self):
        def bad_llm(prompt: str) -> str:
            return "This is not JSON at all"

        text = "Some content."
        items = _extract_with_llm(text, bad_llm)
        assert items == []

    def test_parse_json_from_response_code_block(self):
        response = '```json\n[{"a": 1}]\n```'
        result = _parse_json_from_response(response)
        assert result == [{"a": 1}]

    def test_parse_json_from_response_array_in_text(self):
        response = 'Here is the result: [{"a": 1}] and more text'
        result = _parse_json_from_response(response)
        assert result == [{"a": 1}]

    def test_parse_json_from_response_invalid(self):
        response = "No array here"
        result = _parse_json_from_response(response)
        assert result == []


class TestCuratorWrite:
    def test_write_compiled_note_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            entities = vault / "entities"
            entities.mkdir()
            compiled_dirs = {"entities": entities}

            item = {
                "type": "entity",
                "name": "Bitcoin",
                "content": "A cryptocurrency",
                "date": "2026-07-29",
                "tags": ["crypto"],
            }
            _write_compiled_note(vault, compiled_dirs, item)

            note = entities / "Bitcoin.md"
            assert note.exists()
            text = note.read_text(encoding="utf-8")
            assert "## For future Claude" in text
            assert "crypto" in text

    def test_write_compiled_note_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            entities = vault / "entities"
            entities.mkdir()
            compiled_dirs = {"entities": entities}

            # First write
            item1 = {
                "type": "entity",
                "name": "Bitcoin",
                "content": "First content",
                "date": "2026-07-29",
                "tags": [],
            }
            _write_compiled_note(vault, compiled_dirs, item1)

            # Second write with different content
            item2 = {
                "type": "entity",
                "name": "Bitcoin",
                "content": "Second content",
                "date": "2026-07-30",
                "tags": [],
            }
            _write_compiled_note(vault, compiled_dirs, item2)

            text = (entities / "Bitcoin.md").read_text(encoding="utf-8")
            assert "First content" in text
            assert "Second content" in text
            assert "## Update" in text

    def test_write_compiled_note_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            entities = vault / "entities"
            entities.mkdir()
            compiled_dirs = {"entities": entities}

            item = {
                "type": "entity",
                "name": "Bitcoin",
                "content": "Same content",
                "date": "2026-07-29",
                "tags": [],
            }
            _write_compiled_note(vault, compiled_dirs, item)
            _write_compiled_note(vault, compiled_dirs, item)  # Same again

            text = (entities / "Bitcoin.md").read_text(encoding="utf-8")
            assert text.count("Same content") == 1


class TestCuratorArchive:
    def test_archive_old_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily = Path(tmp) / "daily"
            daily.mkdir()

            # Create an old note
            old_note = daily / "2026-01-01.md"
            old_note.write_text("old", encoding="utf-8")

            # Create a recent note
            recent_note = daily / "2099-12-31.md"
            recent_note.write_text("recent", encoding="utf-8")

            archived = _archive_old_notes(daily, 30)
            assert archived == 1
            assert not old_note.exists()
            assert (daily / "archive" / "2026-01-01.md").exists()
            assert recent_note.exists()

    def test_archive_zero_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            daily = Path(tmp) / "daily"
            daily.mkdir()
            note = daily / "2026-01-01.md"
            note.write_text("x", encoding="utf-8")

            archived = _archive_old_notes(daily, 0)
            assert archived == 0
            assert note.exists()


class TestCurateVault:
    def test_curate_vault_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            config = {
                "schema": {
                    "raw": "raw/",
                    "daily": "chronicle/daily/",
                    "entities": "entities/",
                    "concepts": "concepts/",
                    "comparisons": "comparisons/",
                    "projects": "projects/",
                },
                "auto_curate": {"enabled": True, "archive_after_days": 30},
            }

            daily_dir = vault / "chronicle" / "daily"
            daily_dir.mkdir(parents=True)
            atomic_write_text(
                daily_dir / "2026-07-29.md",
                "### Entity: TestCoin\n"
                "A test cryptocurrency designed for demonstration purposes. "
                "It uses a novel consensus mechanism and has been deployed on "
                "multiple testnets for evaluation. TestCoin serves as a reference "
                "implementation for educational blockchain development.\n",
            )

            stats = curate_vault(vault, config)
            print("DEBUG curate stats:", stats)
            assert stats["status"] == "ok"
            assert stats["processed"] == 1, f"Expected 1 processed, got {stats}"
            assert stats["created"] >= 1
            assert (vault / "entities" / "TestCoin.md").exists()

    def test_curate_vault_llm(self):
        def fake_llm(prompt: str) -> str:
            return json.dumps(
                [
                    {
                        "type": "concept",
                        "name": "LLM Curation",
                        "content": "Using LLMs to extract knowledge.",
                        "tags": ["ai"],
                    },
                ]
            )

        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            config = {
                "schema": {
                    "raw": "raw/",
                    "daily": "chronicle/daily/",
                    "entities": "entities/",
                    "concepts": "concepts/",
                    "comparisons": "comparisons/",
                    "projects": "projects/",
                },
                "auto_curate": {"enabled": True, "archive_after_days": 30},
            }

            daily_dir = vault / "chronicle" / "daily"
            daily_dir.mkdir(parents=True)
            atomic_write_text(
                daily_dir / "2026-07-29.md",
                "Today we discussed using LLMs for knowledge extraction in our wiki system. "
                "The approach involves analyzing daily chronicle notes and extracting "
                "structured entities, concepts, and decisions. This enables the system "
                "to build a compounding knowledge base over time without manual effort.",
            )

            stats = curate_vault(vault, config, llm_generate=fake_llm)
            assert stats["llm_mode"] is True
            assert stats["created"] >= 1, f"Expected >=1 created, got {stats}"
            assert (vault / "concepts" / "LLM Curation.md").exists()

    def test_curate_vault_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            config = {
                "schema": {"daily": "chronicle/daily/"},
                "auto_curate": {"enabled": True, "archive_after_days": 30},
            }
            stats = curate_vault(vault, config)
            assert stats["status"] == "no_notes"


# ---------------------------------------------------------------------------
# Provider tests
# ---------------------------------------------------------------------------


class TestProvider:
    def test_name(self):
        p = LlmwikiMemoryProvider()
        assert p.name == "llmwiki"

    def test_sync_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {"schema": {"daily": "chronicle/daily/"}}
            p._agent_context = "primary"

            p.sync_turn("Hello", "Hi there!")

            daily_files = list((vault / "chronicle" / "daily").glob("*.md"))
            assert len(daily_files) == 1
            content = daily_files[0].read_text(encoding="utf-8")
            assert "Hello" in content
            assert "Hi there!" in content

    def test_sync_turn_skips_non_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {"schema": {"daily": "chronicle/daily/"}}
            p._agent_context = "cron"

            p.sync_turn("Hello", "Hi there!")

            daily_files = list((vault / "chronicle" / "daily").glob("*.md"))
            assert len(daily_files) == 0

    def test_sync_turn_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {"schema": {"daily": "chronicle/daily/"}}
            p._agent_context = "primary"

            long_user = "x" * 10000
            long_assistant = "y" * 10000
            p.sync_turn(long_user, long_assistant)

            daily_files = list((vault / "chronicle" / "daily").glob("*.md"))
            content = daily_files[0].read_text(encoding="utf-8")
            # Should be truncated
            assert len(content) < len(long_user) + len(long_assistant)

    def test_prefetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "entities").mkdir()
            atomic_write_text(
                vault / "entities" / "Bitcoin.md",
                "# Bitcoin\n\ncryptocurrency",
            )

            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {
                "schema": {
                    "entities": "entities/",
                    "concepts": "concepts/",
                    "comparisons": "comparisons/",
                    "projects": "projects/",
                    "queries": "queries/",
                },
                "search": {
                    "engine": "python",
                    "max_results": 10,
                    "context_lines": 3,
                },
            }

            result = p.prefetch("cryptocurrency")
            assert "Bitcoin" in result

    def test_prefetch_with_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "entities").mkdir()
            atomic_write_text(vault / "entities" / "Bitcoin.md", "# Bitcoin\n\ncryptocurrency")

            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {
                "schema": {"entities": "entities/"},
                "search": {"engine": "python", "max_results": 10, "context_lines": 3},
            }

            result = p.prefetch("cryptocurrency", session_id="sess-123")
            assert p._session_id == "sess-123"
            assert "Bitcoin" in result

    def test_prefetch_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "entities").mkdir()
            atomic_write_text(vault / "entities" / "Apple.md", "# Apple\n\nFruit")

            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {
                "schema": {
                    "entities": "entities/",
                    "concepts": "concepts/",
                    "comparisons": "comparisons/",
                    "projects": "projects/",
                    "queries": "queries/",
                },
                "search": {"engine": "python", "max_results": 10, "context_lines": 3},
            }

            result = p.prefetch("zzzzzzzzz")
            assert result == ""

    def test_on_session_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {"schema": {"daily": "chronicle/daily/"}}
            p._agent_context = "primary"

            p.on_session_end(
                [
                    {"role": "user", "content": "Tell me about Python"},
                    {"role": "assistant", "content": "Python is a programming language."},
                ]
            )

            daily_files = list((vault / "chronicle" / "daily").glob("*.md"))
            assert len(daily_files) == 1
            content = daily_files[0].read_text(encoding="utf-8")
            assert "Session End" in content
            assert "python" in content.lower()

    def test_on_session_switch(self):
        p = LlmwikiMemoryProvider()
        p._session_id = "old-session"
        p._turn_buffer = [{"timestamp": "12:00", "user": "hi", "assistant": "hello"}]

        p.on_session_switch("new-session", reset=True)
        assert p._session_id == "new-session"
        assert p._turn_buffer == []

    def test_system_prompt_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault

            block = p.system_prompt_block()
            assert "local Markdown wiki" in block
            assert "create_entity" in block
            assert "search_wiki" in block

    def test_backup_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault

            paths = p.backup_paths()
            assert len(paths) == 1
            assert str(vault) in paths[0]

    def test_save_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            hermes_home = Path(tmp)
            p = LlmwikiMemoryProvider()

            p.save_config({"vault_path": "/tmp/wiki"}, str(hermes_home))

            config_path = hermes_home / "llmwiki.json"
            assert config_path.exists()
            data = json.loads(config_path.read_text(encoding="utf-8"))
            assert data["vault_path"] == "/tmp/wiki"

    def test_get_config_schema(self):
        p = LlmwikiMemoryProvider()
        schema = p.get_config_schema()
        assert isinstance(schema, list)
        assert len(schema) >= 1
        assert schema[0]["key"] == "vault_path"

    def test_tools(self):
        p = LlmwikiMemoryProvider()
        schemas = p.get_tool_schemas()
        names = [s["function"]["name"] for s in schemas]
        assert "search_wiki" in names
        assert "append_note" in names
        assert "create_entity" in names

    def test_tool_append_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {"schema": {"daily": "chronicle/daily/"}}

            result = p.handle_tool_call(
                "append_note",
                {
                    "section": "Entity",
                    "title": "Test",
                    "content": "Test content",
                },
            )
            data = json.loads(result)
            assert data["status"] == "ok"
            assert "Appended" in data["message"]

    def test_tool_create_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {"schema": {"entities": "entities/"}}

            result = p.handle_tool_call(
                "create_entity",
                {
                    "name": "Bitcoin",
                    "type": "entity",
                    "content": "A cryptocurrency",
                    "tags": ["crypto"],
                },
            )
            data = json.loads(result)
            assert data["status"] == "ok"
            assert "Created" in data["message"]
            assert (vault / "entities" / "Bitcoin.md").exists()

    def test_tool_call_returns_json(self):
        """handle_tool_call must return a JSON string per Hermes protocol."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            p = LlmwikiMemoryProvider()
            p._vault_path = vault
            p._config = {"schema": {"entities": "entities/"}}

            result = p.handle_tool_call(
                "create_entity",
                {"name": "X", "type": "concept", "content": "Y"},
            )
            # Must be valid JSON
            parsed = json.loads(result)
            assert "status" in parsed

    def test_post_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            p = LlmwikiMemoryProvider()
            p.post_setup(
                Path.home() / ".hermes",
                {"vault_path": str(vault), "schema": {}},
            )
            assert (vault / "SCHEMA.md").exists()
            assert (vault / "chronicle" / "daily").is_dir()
