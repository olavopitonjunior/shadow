"""
MediaProcessor - Processamento de mídia para Shadow MVP.

Suporta:
- Download de mídia do WhatsApp
- Transcrição de áudio (Gemini/Whisper)
- OCR de imagens (Gemini Vision)
- Extração de texto de documentos
"""

import base64
import io
import mimetypes
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx


@dataclass
class MediaAttachment:
    """Representa um anexo de mídia."""
    url: str | None = None
    data: bytes | None = None
    mime_type: str = "application/octet-stream"
    file_size: int | None = None
    filename: str | None = None
    caption: str | None = None

    # Resultados do processamento
    transcription: str | None = None
    extracted_text: str | None = None
    analysis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "filename": self.filename,
            "caption": self.caption,
            "transcription": self.transcription,
            "extracted_text": self.extracted_text,
            "analysis": self.analysis,
        }


@dataclass
class MediaProcessResult:
    """Resultado do processamento de mídia."""
    success: bool
    media_type: Literal["audio", "image", "document", "video", "unknown"]
    text: str | None = None  # Texto extraído/transcrito
    summary: str | None = None  # Resumo do conteúdo
    entities: list[dict[str, Any]] = field(default_factory=list)  # Entidades extraídas
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "media_type": self.media_type,
            "text": self.text,
            "summary": self.summary,
            "entities": self.entities,
            "error": self.error,
        }


class MediaProcessor:
    """
    Processador de mídia com suporte a transcrição e OCR.

    Exemplo de uso:
    ```python
    processor = MediaProcessor()

    # Processar áudio
    result = await processor.process_audio(audio_url="https://...")
    if result.success:
        print(f"Transcrição: {result.text}")

    # Processar imagem
    result = await processor.process_image(image_url="https://...")
    if result.success:
        print(f"Texto extraído: {result.text}")
    ```
    """

    # MIME types suportados
    AUDIO_TYPES = {
        "audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg",
        "audio/webm", "audio/m4a", "audio/aac", "audio/opus",
    }
    IMAGE_TYPES = {
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "image/bmp", "image/tiff",
    }
    DOCUMENT_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    VIDEO_TYPES = {
        "video/mp4", "video/webm", "video/quicktime", "video/x-msvideo",
    }

    def __init__(
        self,
        gemini_api_key: str | None = None,
        openai_api_key: str | None = None,
        cache_dir: str | Path | None = None,
        max_file_size: int = 25 * 1024 * 1024,  # 25MB
    ) -> None:
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.cache_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "shadow_media"
        self.max_file_size = max_file_size

        # Cria diretório de cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _detect_media_type(self, mime_type: str) -> Literal["audio", "image", "document", "video", "unknown"]:
        """Detecta tipo de mídia baseado no MIME type."""
        if mime_type in self.AUDIO_TYPES:
            return "audio"
        if mime_type in self.IMAGE_TYPES:
            return "image"
        if mime_type in self.DOCUMENT_TYPES:
            return "document"
        if mime_type in self.VIDEO_TYPES:
            return "video"
        return "unknown"

    async def download(
        self,
        url: str,
        timeout: float = 30.0,
    ) -> tuple[bytes | None, str | None]:
        """
        Faz download de mídia de uma URL.

        Returns:
            Tuple de (dados, mime_type) ou (None, None) se falhar
        """
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                # Verifica tamanho
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.max_file_size:
                    print(f"[media] Arquivo muito grande: {content_length} bytes")
                    return None, None

                # Detecta MIME type
                mime_type = response.headers.get("content-type", "application/octet-stream")
                mime_type = mime_type.split(";")[0].strip()  # Remove charset

                return response.content, mime_type

        except Exception as e:
            print(f"[media] Erro no download: {e}")
            return None, None

    async def process(
        self,
        url: str | None = None,
        data: bytes | None = None,
        mime_type: str | None = None,
    ) -> MediaProcessResult:
        """
        Processa mídia automaticamente baseado no tipo.

        Args:
            url: URL da mídia
            data: Dados binários da mídia
            mime_type: MIME type (obrigatório se data for fornecido)
        """
        # Download se necessário
        if url and not data:
            data, detected_mime = await self.download(url)
            if not data:
                return MediaProcessResult(
                    success=False,
                    media_type="unknown",
                    error="Falha no download da mídia",
                )
            mime_type = mime_type or detected_mime

        if not data:
            return MediaProcessResult(
                success=False,
                media_type="unknown",
                error="Nenhum dado de mídia fornecido",
            )

        mime_type = mime_type or "application/octet-stream"
        media_type = self._detect_media_type(mime_type)

        if media_type == "audio":
            return await self.process_audio(data=data, mime_type=mime_type)
        elif media_type == "image":
            return await self.process_image(data=data, mime_type=mime_type)
        elif media_type == "document":
            return await self.process_document(data=data, mime_type=mime_type)
        elif media_type == "video":
            return MediaProcessResult(
                success=False,
                media_type="video",
                error="Processamento de vídeo não implementado",
            )
        else:
            return MediaProcessResult(
                success=False,
                media_type="unknown",
                error=f"Tipo de mídia não suportado: {mime_type}",
            )

    async def process_audio(
        self,
        url: str | None = None,
        data: bytes | None = None,
        mime_type: str = "audio/mpeg",
    ) -> MediaProcessResult:
        """
        Transcreve áudio usando Gemini ou Whisper.
        """
        # Download se necessário
        if url and not data:
            data, detected_mime = await self.download(url)
            if not data:
                return MediaProcessResult(
                    success=False,
                    media_type="audio",
                    error="Falha no download do áudio",
                )
            mime_type = detected_mime or mime_type

        if not data:
            return MediaProcessResult(
                success=False,
                media_type="audio",
                error="Nenhum dado de áudio fornecido",
            )

        # Tenta Gemini primeiro
        if self.gemini_api_key:
            result = await self._transcribe_with_gemini(data, mime_type)
            if result.success:
                return result

        # Fallback para Whisper (OpenAI)
        if self.openai_api_key:
            result = await self._transcribe_with_whisper(data, mime_type)
            if result.success:
                return result

        return MediaProcessResult(
            success=False,
            media_type="audio",
            error="Nenhuma API de transcrição disponível (configure GEMINI_API_KEY ou OPENAI_API_KEY)",
        )

    async def _transcribe_with_gemini(
        self,
        data: bytes,
        mime_type: str,
    ) -> MediaProcessResult:
        """Transcreve áudio usando Gemini."""
        try:
            # Converte para base64
            audio_b64 = base64.b64encode(data).decode("utf-8")

            # Chama API do Gemini
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"

            payload = {
                "contents": [{
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": audio_b64,
                            }
                        },
                        {
                            "text": "Transcreva este áudio em português. Retorne apenas o texto transcrito, sem comentários adicionais."
                        }
                    ]
                }]
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                result = response.json()
                text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

                if text:
                    return MediaProcessResult(
                        success=True,
                        media_type="audio",
                        text=text.strip(),
                    )

        except Exception as e:
            print(f"[media] Erro Gemini transcription: {e}")

        return MediaProcessResult(
            success=False,
            media_type="audio",
            error="Falha na transcrição com Gemini",
        )

    async def _transcribe_with_whisper(
        self,
        data: bytes,
        mime_type: str,
    ) -> MediaProcessResult:
        """Transcreve áudio usando OpenAI Whisper."""
        try:
            # Determina extensão do arquivo
            ext_map = {
                "audio/mpeg": "mp3",
                "audio/mp3": "mp3",
                "audio/wav": "wav",
                "audio/ogg": "ogg",
                "audio/webm": "webm",
                "audio/m4a": "m4a",
            }
            ext = ext_map.get(mime_type, "mp3")

            url = "https://api.openai.com/v1/audio/transcriptions"

            # Prepara multipart form
            files = {
                "file": (f"audio.{ext}", io.BytesIO(data), mime_type),
                "model": (None, "whisper-1"),
                "language": (None, "pt"),
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    files=files,
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                )
                response.raise_for_status()

                result = response.json()
                text = result.get("text", "")

                if text:
                    return MediaProcessResult(
                        success=True,
                        media_type="audio",
                        text=text.strip(),
                    )

        except Exception as e:
            print(f"[media] Erro Whisper transcription: {e}")

        return MediaProcessResult(
            success=False,
            media_type="audio",
            error="Falha na transcrição com Whisper",
        )

    async def process_image(
        self,
        url: str | None = None,
        data: bytes | None = None,
        mime_type: str = "image/jpeg",
        prompt: str | None = None,
    ) -> MediaProcessResult:
        """
        Extrai texto e analisa imagem usando Gemini Vision.
        """
        # Download se necessário
        if url and not data:
            data, detected_mime = await self.download(url)
            if not data:
                return MediaProcessResult(
                    success=False,
                    media_type="image",
                    error="Falha no download da imagem",
                )
            mime_type = detected_mime or mime_type

        if not data:
            return MediaProcessResult(
                success=False,
                media_type="image",
                error="Nenhum dado de imagem fornecido",
            )

        if not self.gemini_api_key:
            return MediaProcessResult(
                success=False,
                media_type="image",
                error="GEMINI_API_KEY não configurada para OCR",
            )

        try:
            # Converte para base64
            image_b64 = base64.b64encode(data).decode("utf-8")

            # Prompt padrão para OCR e análise
            default_prompt = """Analise esta imagem e extraia as seguintes informações em português:

1. **Texto visível**: Transcreva todo o texto que aparecer na imagem (OCR)
2. **Descrição**: Descreva brevemente o que a imagem mostra
3. **Entidades**: Liste nomes de pessoas, empresas, datas, valores monetários, telefones ou emails se houver

Formato da resposta:
TEXTO: [texto extraído]
DESCRIÇÃO: [descrição breve]
ENTIDADES: [lista de entidades encontradas]"""

            url_api = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"

            payload = {
                "contents": [{
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": image_b64,
                            }
                        },
                        {
                            "text": prompt or default_prompt,
                        }
                    ]
                }]
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url_api, json=payload)
                response.raise_for_status()

                result = response.json()
                text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

                if text:
                    # Parse resultado
                    extracted_text = ""
                    summary = ""
                    entities = []

                    lines = text.split("\n")
                    current_section = None

                    for line in lines:
                        line = line.strip()
                        if line.startswith("TEXTO:"):
                            current_section = "text"
                            extracted_text = line[6:].strip()
                        elif line.startswith("DESCRIÇÃO:"):
                            current_section = "desc"
                            summary = line[10:].strip()
                        elif line.startswith("ENTIDADES:"):
                            current_section = "entities"
                            entities_str = line[10:].strip()
                            if entities_str:
                                entities = [{"value": e.strip()} for e in entities_str.split(",")]
                        elif current_section == "text" and line:
                            extracted_text += " " + line
                        elif current_section == "desc" and line:
                            summary += " " + line

                    return MediaProcessResult(
                        success=True,
                        media_type="image",
                        text=extracted_text.strip() or text,
                        summary=summary.strip() or None,
                        entities=entities,
                    )

        except Exception as e:
            print(f"[media] Erro Gemini Vision: {e}")

        return MediaProcessResult(
            success=False,
            media_type="image",
            error="Falha na análise da imagem",
        )

    async def process_document(
        self,
        url: str | None = None,
        data: bytes | None = None,
        mime_type: str = "application/pdf",
    ) -> MediaProcessResult:
        """
        Extrai texto de documentos (PDF, DOCX, TXT).
        """
        # Download se necessário
        if url and not data:
            data, detected_mime = await self.download(url)
            if not data:
                return MediaProcessResult(
                    success=False,
                    media_type="document",
                    error="Falha no download do documento",
                )
            mime_type = detected_mime or mime_type

        if not data:
            return MediaProcessResult(
                success=False,
                media_type="document",
                error="Nenhum dado de documento fornecido",
            )

        # TXT é simples
        if mime_type == "text/plain":
            try:
                text = data.decode("utf-8")
                return MediaProcessResult(
                    success=True,
                    media_type="document",
                    text=text,
                )
            except Exception as e:
                return MediaProcessResult(
                    success=False,
                    media_type="document",
                    error=f"Erro ao decodificar texto: {e}",
                )

        # PDF via Gemini
        if mime_type == "application/pdf" and self.gemini_api_key:
            try:
                pdf_b64 = base64.b64encode(data).decode("utf-8")

                url_api = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"

                payload = {
                    "contents": [{
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "application/pdf",
                                    "data": pdf_b64,
                                }
                            },
                            {
                                "text": "Extraia todo o texto deste documento PDF em português. Mantenha a estrutura e formatação quando possível."
                            }
                        ]
                    }]
                }

                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(url_api, json=payload)
                    response.raise_for_status()

                    result = response.json()
                    text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

                    if text:
                        return MediaProcessResult(
                            success=True,
                            media_type="document",
                            text=text.strip(),
                        )

            except Exception as e:
                print(f"[media] Erro PDF extraction: {e}")

        return MediaProcessResult(
            success=False,
            media_type="document",
            error=f"Extração de texto não implementada para {mime_type}",
        )

    async def extract_tasks_from_text(self, text: str) -> list[dict[str, Any]]:
        """
        Extrai tarefas, compromissos e lembretes de texto transcrito.

        Usa Gemini para análise semântica.
        """
        if not self.gemini_api_key:
            return []

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"

            prompt = f"""Analise o seguinte texto e extraia:
1. Tarefas mencionadas (coisas a fazer)
2. Compromissos/reuniões com data/hora
3. Lembretes

Texto: "{text}"

Responda em formato JSON:
{{
  "tasks": [
    {{"title": "...", "due_date": "YYYY-MM-DD ou null"}}
  ],
  "appointments": [
    {{"title": "...", "datetime": "YYYY-MM-DDTHH:MM ou null", "duration_minutes": 60}}
  ],
  "reminders": [
    {{"message": "...", "remind_at": "YYYY-MM-DDTHH:MM ou null"}}
  ]
}}

Se não encontrar nada, retorne listas vazias."""

            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                }
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                result = response.json()
                text_result = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")

                import json
                entities = json.loads(text_result)

                all_entities = []
                for task in entities.get("tasks", []):
                    all_entities.append({"type": "task", **task})
                for appt in entities.get("appointments", []):
                    all_entities.append({"type": "appointment", **appt})
                for reminder in entities.get("reminders", []):
                    all_entities.append({"type": "reminder", **reminder})

                return all_entities

        except Exception as e:
            print(f"[media] Erro ao extrair entidades: {e}")
            return []


# === Singleton global para uso simplificado ===

_media_processor: MediaProcessor | None = None


def get_media_processor() -> MediaProcessor:
    """Obtém instância global do MediaProcessor."""
    global _media_processor
    if _media_processor is None:
        _media_processor = MediaProcessor()
    return _media_processor


# === Exemplo de uso ===

if __name__ == "__main__":
    import asyncio

    async def main():
        processor = MediaProcessor()

        # Teste simples
        print("=== MediaProcessor ===")
        print(f"Gemini API: {'✅' if processor.gemini_api_key else '❌'}")
        print(f"OpenAI API: {'✅' if processor.openai_api_key else '❌'}")
        print(f"Cache dir: {processor.cache_dir}")

        # Se tiver uma URL de teste
        # result = await processor.process_audio(url="https://...")
        # print(f"Transcrição: {result.text}")

    asyncio.run(main())
