import re
from dataclasses import dataclass
from typing import Iterable

# Basic prompt injection patterns (expand as needed)
INJECTION_PATTERNS = [
    r"ignore (all|any|previous|above) instructions",
    r"disregard (all|any|previous|above) instructions",
    r"reveal (your|the) (system|developer) prompt",
    r"show (your|the) hidden instructions",
    r"print (the )?system prompt",
    r"exfiltrate",
    r"dump (all|the) (secrets|keys|credentials)",
    r"read .*\.env",
    r"read .*credentials",
    r"run command",
    r"execute shell",
]

# Basic toxicity / profanity list (pt-br + en). Keep minimal, extend over time.
PROFANITY = [
    r"\b(?:idiota|burro|imbecil|estupido|lixo|otario|otaria|merda)\b",
    r"\b(?:fuck|shit|bitch|asshole|dumb)\b",
]

SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",
    r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?[\w-]{20,}['\"]?",
    r"(?i)(secret|password|passwd|pwd)\s*[=:]\s*['\"]?[^'\"\s]{8,}['\"]?",
]


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str | None = None


def _matches_any(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(pat, text, flags=re.IGNORECASE) for pat in patterns)


def detect_prompt_injection(text: str) -> GuardrailResult:
    if _matches_any(INJECTION_PATTERNS, text):
        return GuardrailResult(False, "prompt_injection")
    return GuardrailResult(True, None)


def sanitize_secrets(text: str) -> str:
    sanitized = text
    for pat in SECRET_PATTERNS:
        sanitized = re.sub(pat, "[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


def filter_toxicity(text: str) -> str:
    sanitized = text
    for pat in PROFANITY:
        sanitized = re.sub(pat, "[conteudo removido]", sanitized, flags=re.IGNORECASE)
    return sanitized


def apply_output_guardrails(text: str) -> str:
    if not text:
        return text
    sanitized = sanitize_secrets(text)
    sanitized = filter_toxicity(sanitized)
    return sanitized


def safe_refusal(reason: str | None = None) -> str:
    if reason == "prompt_injection":
        return "Nao posso atender a esse pedido por motivos de seguranca."
    return "Nao posso atender a esse pedido."
