"""Tests for the PromptBuilder and dynamic prompt assembly."""

import pytest


class TestPromptBuilder:
    """PromptBuilder unit tests."""

    def test_build_minimal_prompt(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        prompt = builder.build_system_prompt()
        assert "Shadow" in prompt
        assert "REGRAS DE EXECUÇÃO" in prompt

    def test_build_prompt_with_settings(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        settings = {
            "timezone": "Europe/Lisbon",
            "language": "pt-PT",
            "use_emojis": False,
            "verbose_responses": True,
            "always_ask_incomplete": True,
            "auto_create_from_conversations": False,
            "group_monitoring_enabled": False,
            "default_reminder_minutes": 15,
            "morning_summary_enabled": True,
            "morning_summary_time": "08:00",
        }
        prompt = builder.build_system_prompt(settings=settings)
        assert "Europe/Lisbon" in prompt
        assert "pt-PT" in prompt
        assert "PREFERÊNCIAS DO USUÁRIO" in prompt

    def test_build_prompt_with_learned_patterns(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        settings = {"timezone": "America/Sao_Paulo"}
        learned = {
            "time_preferences": "Prefere reuniões de manhã (9-11h)",
            "top_categories": "trabalho (60%), pessoal (30%)",
        }
        prompt = builder.build_system_prompt(
            settings=settings, learned_patterns=learned
        )
        assert "Prefere reuniões de manhã" in prompt
        assert "trabalho (60%)" in prompt

    def test_build_prompt_with_corrections(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        settings = {"timezone": "America/Sao_Paulo"}
        corrections = [
            {"trigger_text": "reunião amanhã", "learned_action": "perguntar horário"},
            {"trigger_text": "tarefa pro João", "learned_action": "confirmar contato"},
        ]
        prompt = builder.build_system_prompt(
            settings=settings, recent_corrections=corrections
        )
        assert "reunião amanhã" in prompt
        assert "perguntar horário" in prompt

    def test_build_prompt_with_memories(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        settings = {"timezone": "America/Sao_Paulo"}
        memories = ["João prefere café sem açúcar", "Reunião semanal às quartas"]
        prompt = builder.build_system_prompt(
            settings=settings, important_memories=memories
        )
        assert "João prefere café sem açúcar" in prompt

    def test_build_context_section_empty(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        section = builder.build_context_section()
        assert "Sem contexto" in section

    def test_build_context_section_with_contact(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        contact = {
            "name": "João Silva",
            "phone": "+5511999991111",
            "relationship_type": "colleague",
            "summary": "Developed the frontend together",
        }
        section = builder.build_context_section(contact_context=contact)
        assert "João Silva" in section
        assert "colleague" in section

    def test_soul_and_identity_loaded(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        prompt = builder.build_system_prompt()
        # SOUL.md content should be present
        assert "PERSONALIDADE" in prompt
        # IDENTITY.md content should be present
        assert "CAPACIDADES" in prompt

    def test_singleton(self):
        from prompt_builder import get_prompt_builder

        b1 = get_prompt_builder()
        b2 = get_prompt_builder()
        assert b1 is b2

    def test_cache_clearing(self):
        from prompt_builder import PromptBuilder

        builder = PromptBuilder()
        # Load files into cache
        builder.get_soul()
        assert len(builder._cache) > 0
        builder.clear_cache()
        assert len(builder._cache) == 0
