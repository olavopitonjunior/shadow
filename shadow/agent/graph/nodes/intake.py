"""
Intake node - Parse incoming payload and process multimodal content.

Responsibilities:
- Extract message body, sender info, chat context
- Transcribe audio (Gemini/Whisper)
- OCR images (Gemini Vision)
- Extract text from documents (PDF/DOCX)
- Summarize URLs
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from langchain_core.messages import HumanMessage

from graph.state import ShadowState


def intake_node(state: ShadowState) -> dict[str, Any]:
    """Parse raw payload into structured state fields.

    Handles multimodal content:
    - Audio → transcription via existing media.py
    - Images → OCR/description via existing media.py
    - Documents → text extraction
    - URLs → fetch and summarize
    """
    payload = state.get("raw_payload", {})

    # Extract core fields from payload
    body = (
        payload.get("body")
        or payload.get("text", "")
    )
    sender_phone = payload.get("sender_phone") or payload.get("phone")
    sender_name = payload.get("sender_name") or payload.get("senderName")
    chat_id = (
        payload.get("chat_id")
        or (payload.get("metadata") or {}).get("remoteJid")
        or sender_phone
    )
    chat_type = "group" if payload.get("isGroup") else "direct"
    is_owner = payload.get("is_owner", False)
    session_id = payload.get("session_id")
    media_type = payload.get("media_type")
    media_url = payload.get("media_url")

    # Process multimodal content
    multimodal_context = None
    if media_type and media_url:
        multimodal_context = _process_media(media_type, media_url, body)

    # Extract and summarize URLs from message body
    url_context = None
    if body and not media_type:
        url_context = _extract_and_summarize_urls(body)

    # Combine multimodal context
    if url_context and multimodal_context:
        multimodal_context = f"{multimodal_context}\n\n--- URL Content ---\n{url_context}"
    elif url_context:
        multimodal_context = url_context

    # Use transcription as body if audio and body is empty
    if media_type == "audio" and multimodal_context and not body:
        body = multimodal_context

    # Build initial message for LangGraph message history
    display_body = body or multimodal_context or "[empty message]"
    if multimodal_context and body and media_type != "audio":
        display_body = f"{body}\n\n[{media_type}]: {multimodal_context}"
    messages = [HumanMessage(content=display_body)]

    return {
        "messages": messages,
        "body": body or "",
        "multimodal_context": multimodal_context,
        "sender_phone": sender_phone,
        "sender_name": sender_name,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "is_owner": is_owner,
        "session_id": session_id,
        "media_type": media_type,
        "media_url": media_url,
        "steps": [{"node": "intake", "body_length": len(body or ""), "has_media": bool(media_type)}],
    }


def _process_media(
    media_type: str, media_url: str, caption: str | None = None
) -> str | None:
    """Process media using existing async MediaProcessor.

    Runs the async processor in a sync context (LangGraph node).
    Returns extracted text/transcription or None on failure.
    """
    try:
        from media import get_media_processor

        processor = get_media_processor()

        # Run async processor — get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in async context — use a new thread to avoid deadlock
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    _async_process_media(processor, media_type, media_url, caption),
                )
                return future.result(timeout=120)
        else:
            return asyncio.run(
                _async_process_media(processor, media_type, media_url, caption)
            )

    except Exception as e:
        print(f"[intake] Media processing error: {e}")
        return None


async def _async_process_media(
    processor, media_type: str, media_url: str, caption: str | None
) -> str | None:
    """Async media processing dispatcher."""
    if media_type == "audio":
        result = await processor.process_audio(url=media_url)
        return result.text if result and result.success else None

    if media_type == "image":
        result = await processor.process_image(url=media_url, prompt=caption)
        return result.text if result and result.success else None

    if media_type == "document":
        result = await processor.process_document(url=media_url)
        return result.text if result and result.success else None

    # Generic fallback — let processor detect type
    result = await processor.process(url=media_url)
    return result.text if result and result.success else None


# ---------------------------------------------------------------------------
# URL extraction + summarization
# ---------------------------------------------------------------------------

_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"')\]]+",
    re.IGNORECASE,
)


def _extract_and_summarize_urls(body: str) -> str | None:
    """Extract URLs from message body and fetch a brief summary.

    Only processes the first URL found to avoid excessive API calls.
    Returns summarized content or None.
    """
    urls = _URL_PATTERN.findall(body)
    if not urls:
        return None

    url = urls[0]  # Process only the first URL

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _async_fetch_url(url))
                return future.result(timeout=30)
        else:
            return asyncio.run(_async_fetch_url(url))
    except Exception as e:
        print(f"[intake] URL fetch error for {url}: {e}")
        return None


async def _async_fetch_url(url: str) -> str | None:
    """Fetch URL content and extract readable text (first 2000 chars)."""
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 Shadow-Agent/1.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            # Only process text/html content
            if "text/html" not in content_type and "text/plain" not in content_type:
                return f"[Link: {url} — tipo: {content_type}]"

            text = response.text

            # Strip HTML tags for a rough text extraction
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            # Extract title if present
            title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.DOTALL | re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else ""

            # Truncate to 2000 chars
            content = text[:2000]
            if title:
                content = f"Título: {title}\n\n{content}"

            return f"[Conteúdo de {url}]\n{content}"

    except Exception as e:
        print(f"[intake] URL fetch failed: {e}")
        return f"[Link: {url} — não foi possível acessar]"
