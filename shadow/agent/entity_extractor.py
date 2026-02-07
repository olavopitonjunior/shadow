"""
Entity Extractor Module

Extracts structured entities (tasks, meetings, contacts, reminders) from messages
using LLM (Gemini) for sophisticated natural language understanding.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Any

import google.generativeai as genai

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractedEntity:
    """A single extracted entity from a message."""
    entity_type: Literal["task", "meeting", "contact", "reminder"]
    data: dict[str, Any]
    confidence: float
    source_text: str


@dataclass
class ExtractionResult:
    """Result of entity extraction from a message."""
    entities: list[ExtractedEntity] = field(default_factory=list)
    contacts_mentioned: list[str] = field(default_factory=list)
    has_action_items: bool = False


EXTRACTION_PROMPT = """Analise a mensagem abaixo e extraia entidades estruturadas.

Mensagem: "{message}"
Remetente: {sender_name}
Telefone: {sender_phone}
Tipo de chat: {chat_type}

Contexto recente (ultimas mensagens):
{recent_context}

Extraia as seguintes entidades (SE PRESENTES na mensagem):

1. TAREFAS (task): Acoes a fazer, pedidos, compromissos de entrega
   - description: descricao da tarefa
   - due_date: data/hora se mencionada (formato ISO: YYYY-MM-DDTHH:MM:SS)
   - priority: "alta", "media" ou "baixa" (infira do contexto)
   - assigned_to: nome da pessoa responsavel (se mencionado)

2. REUNIOES (meeting): Encontros, calls, eventos agendados
   - title: titulo/assunto
   - datetime: data e hora (formato ISO)
   - participants: lista de nomes dos participantes
   - location: local fisico ou link de videoconferencia

3. CONTATOS (contact): Pessoas mencionadas na conversa
   - name: nome da pessoa
   - phone: telefone se mencionado
   - relation: relacao (cliente, colega, fornecedor, amigo, etc)
   - context: contexto em que foi mencionado

4. LEMBRETES (reminder): Coisas para lembrar no futuro
   - message: o que lembrar
   - when: quando lembrar (formato ISO)

REGRAS IMPORTANTES:
- SO extraia entidades que estao CLARAMENTE presentes na mensagem
- NAO invente informacoes que nao estao na mensagem
- Se uma data/hora nao esta clara, omita o campo
- Retorne lista vazia se nao houver entidades relevantes
- Use o contexto recente para entender melhor a conversa

Retorne APENAS um JSON valido no formato:
{{
  "entities": [
    {{
      "type": "task|meeting|contact|reminder",
      "data": {{ ... campos especificos ... }},
      "confidence": 0.0-1.0
    }}
  ],
  "contacts_mentioned": ["nome1", "nome2"],
  "has_action_items": true/false
}}"""


class EntityExtractor:
    """
    Extracts structured entities from messages using Gemini LLM.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize the entity extractor.

        Args:
            api_key: Gemini API key. If None, extraction will be disabled.
        """
        self.api_key = api_key
        self.model = None

        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel("gemini-2.5-flash-lite")
                logger.info("EntityExtractor initialized with Gemini")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
                self.model = None
        else:
            logger.info("EntityExtractor running without LLM (no API key)")

    async def extract(
        self,
        message: str,
        chat_context: dict[str, Any],
    ) -> ExtractionResult:
        """
        Extract entities from a message.

        Args:
            message: The message text to analyze
            chat_context: Context about the chat:
                - sender_name: Name of the sender
                - sender_phone: Phone number of sender
                - chat_type: "direct" or "group"
                - recent_messages: List of recent messages for context

        Returns:
            ExtractionResult with extracted entities
        """
        if not self.model:
            # Fallback to basic extraction without LLM
            return self._extract_basic(message, chat_context)

        try:
            return await self._extract_with_llm(message, chat_context)
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return self._extract_basic(message, chat_context)

    async def _extract_with_llm(
        self,
        message: str,
        chat_context: dict[str, Any],
    ) -> ExtractionResult:
        """Extract entities using Gemini LLM."""
        # Format recent messages for context
        recent_messages = chat_context.get("recent_messages", [])
        recent_context = "\n".join(
            f"- {m.get('role', 'user')}: {m.get('content', '')[:100]}"
            for m in recent_messages[-5:]
        ) or "(sem contexto anterior)"

        prompt = EXTRACTION_PROMPT.format(
            message=message,
            sender_name=chat_context.get("sender_name", "Desconhecido"),
            sender_phone=chat_context.get("sender_phone", "N/A"),
            chat_type=chat_context.get("chat_type", "direct"),
            recent_context=recent_context,
        )

        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )

        return self._parse_llm_response(response.text, message)

    def _parse_llm_response(self, response_text: str, source_text: str) -> ExtractionResult:
        """Parse the LLM response into ExtractionResult."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON
                json_str = response_text.strip()

            data = json.loads(json_str)

            entities = []
            for entity_data in data.get("entities", []):
                entity = ExtractedEntity(
                    entity_type=entity_data.get("type", "task"),
                    data=entity_data.get("data", {}),
                    confidence=float(entity_data.get("confidence", 0.8)),
                    source_text=source_text[:200],
                )
                entities.append(entity)

            return ExtractionResult(
                entities=entities,
                contacts_mentioned=data.get("contacts_mentioned", []),
                has_action_items=data.get("has_action_items", len(entities) > 0),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return ExtractionResult()

    def _extract_basic(
        self,
        message: str,
        chat_context: dict[str, Any],
    ) -> ExtractionResult:
        """
        Basic entity extraction without LLM (fallback).
        Uses simple pattern matching.
        """
        entities = []
        contacts = []
        lower = message.lower()

        # Detect tasks
        task_patterns = [
            r"(?:preciso|tenho que|devo|fazer|enviar|ligar|mandar|responder)\s+(.+)",
            r"tarefa[:\s]+(.+)",
            r"(?:to-?do|pendencia)[:\s]+(.+)",
        ]
        for pattern in task_patterns:
            match = re.search(pattern, lower)
            if match:
                entities.append(ExtractedEntity(
                    entity_type="task",
                    data={"description": match.group(1).strip()[:120]},
                    confidence=0.6,
                    source_text=message[:200],
                ))
                break

        # Detect meetings
        meeting_patterns = [
            r"(?:reuniao|call|meeting|encontro)\s+(?:com\s+)?(.+?)(?:\s+(?:as|amanha|hoje|\d))",
            r"(?:agendar|marcar)\s+(?:reuniao|call|meeting)\s+(.+)",
        ]
        for pattern in meeting_patterns:
            match = re.search(pattern, lower)
            if match:
                entities.append(ExtractedEntity(
                    entity_type="meeting",
                    data={"title": match.group(1).strip()[:100]},
                    confidence=0.5,
                    source_text=message[:200],
                ))
                break

        # Detect reminders
        reminder_patterns = [
            r"(?:lembrar?|lembrete)[:\s]+(.+?)(?:\s+(?:em|as|amanha|hoje|\d)|$)",
            r"(?:nao esquecer|nao posso esquecer)\s+(.+)",
        ]
        for pattern in reminder_patterns:
            match = re.search(pattern, lower)
            if match:
                entities.append(ExtractedEntity(
                    entity_type="reminder",
                    data={"message": match.group(1).strip()[:120]},
                    confidence=0.5,
                    source_text=message[:200],
                ))
                break

        # Extract mentioned names (basic: capitalized words)
        name_pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
        for match in re.finditer(name_pattern, message):
            name = match.group(1)
            # Filter common non-name words
            if name.lower() not in ["shadow", "whatsapp", "ok", "oi", "bom", "dia", "boa", "tarde", "noite"]:
                contacts.append(name)

        # Also check for sender name
        sender_name = chat_context.get("sender_name")
        if sender_name and sender_name not in contacts:
            contacts.append(sender_name)

        return ExtractionResult(
            entities=entities,
            contacts_mentioned=list(set(contacts)),
            has_action_items=len(entities) > 0,
        )
