"""
SecurityAudit - Framework de auditoria de segurança para Shadow MVP.

Baseado nos padrões do Moltbot, fornece:
- Verificação de secrets expostos
- Validação de permissões
- Rate limiting
- Auditoria de configuração
- Proteção contra path traversal (moltbot 2026.2.x)
- Validação de phone numbers
"""

import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal


# === Security: Input Validation (inspired by moltbot 2026.2.x) ===

class ValidationError(Exception):
    """Erro de validação de entrada."""
    pass


def validate_phone_number(phone: str | None) -> str | None:
    """
    Valida e normaliza um número de telefone para formato E.164.
    Protege contra path traversal e injection attacks.

    Args:
        phone: Número de telefone a validar

    Returns:
        Número normalizado ou None se inválido

    Example:
        >>> validate_phone_number("+5511999999999")
        '+5511999999999'
        >>> validate_phone_number("../../../etc")
        None
    """
    if not phone or not isinstance(phone, str):
        return None

    cleaned = phone.strip()

    # Detecta tentativas de path traversal ou injection
    dangerous_patterns = ["..", "/", "\\", "\0", "<", ">", "|", "&", ";", "$", "`"]
    for pattern in dangerous_patterns:
        if pattern in cleaned:
            return None

    # Remove caracteres não numéricos exceto + no início
    has_plus = cleaned.startswith("+")
    digits = re.sub(r"[^\d]", "", cleaned)

    # Verifica tamanho válido (E.164: 10-15 dígitos)
    if len(digits) < 10 or len(digits) > 15:
        return None

    # Verifica se são apenas dígitos
    if not digits.isdigit():
        return None

    # Retorna no formato E.164
    return f"+{digits}" if has_plus or len(digits) >= 11 else digits


def validate_path_component(name: str) -> str:
    """
    Valida um componente de path para prevenir path traversal.

    Args:
        name: Nome do componente (arquivo, diretório, session key, etc.)

    Returns:
        Nome validado

    Raises:
        ValidationError: Se o nome contém caracteres perigosos

    Example:
        >>> validate_path_component("session_123")
        'session_123'
        >>> validate_path_component("../../../etc/passwd")
        ValidationError: Path traversal detected
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Name cannot be empty")

    # Caracteres perigosos para paths
    dangerous = ["..", "/", "\\", "\0", ":", "*", "?", '"', "<", ">", "|"]

    for char in dangerous:
        if char in name:
            raise ValidationError(f"Path traversal detected: {char!r} in {name[:50]!r}")

    # Verifica tamanho razoável
    if len(name) > 255:
        raise ValidationError(f"Name too long: {len(name)} chars")

    return name


def sanitize_session_key(key: str) -> str:
    """
    Sanitiza uma chave de sessão para uso seguro.
    Aceita formatos como: phone@s.whatsapp.net, phone@g.us

    Args:
        key: Chave de sessão (geralmente um JID do WhatsApp)

    Returns:
        Chave sanitizada

    Raises:
        ValidationError: Se a chave contém caracteres perigosos

    Example:
        >>> sanitize_session_key("5511999999999@s.whatsapp.net")
        '5511999999999@s.whatsapp.net'
        >>> sanitize_session_key("../../../etc")
        ValidationError: Invalid session key format
    """
    if not key or not isinstance(key, str):
        raise ValidationError("Session key cannot be empty")

    # Detecta path traversal
    if ".." in key or "/" in key or "\\" in key or "\0" in key:
        raise ValidationError(f"Invalid session key format: {key[:50]!r}")

    # Valida formato básico de JID ou telefone
    # Aceita: digits@suffix, +digits, digits
    jid_pattern = r"^[\d+]+(@[a-zA-Z0-9._-]+)?$"
    if not re.match(jid_pattern, key):
        # Tenta validar como telefone puro
        validated = validate_phone_number(key)
        if validated:
            return validated
        raise ValidationError(f"Invalid session key format: {key[:50]!r}")

    return key


def sanitize_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitiza metadados para prevenir injection em prompts/logs.
    Remove caracteres de controle e trunca strings longas.

    Args:
        data: Dicionário de metadados

    Returns:
        Dicionário sanitizado (cópia)
    """
    MAX_STRING_LENGTH = 10000

    def sanitize_value(value: Any) -> Any:
        if isinstance(value, str):
            # Remove caracteres de controle (exceto newlines e tabs)
            clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
            # Trunca strings muito longas
            if len(clean) > MAX_STRING_LENGTH:
                clean = clean[:MAX_STRING_LENGTH] + "...[truncated]"
            return clean
        elif isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(item) for item in value]
        else:
            return value

    return sanitize_value(data)


@dataclass
class SecurityFinding:
    """Representa um achado de segurança."""
    check_id: str
    severity: Literal["critical", "warn", "info"]
    title: str
    detail: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "remediation": self.remediation,
        }


@dataclass
class SecurityAuditSummary:
    """Resumo da auditoria."""
    critical: int = 0
    warn: int = 0
    info: int = 0


@dataclass
class SecurityAuditReport:
    """Relatório completo de auditoria."""
    timestamp: str
    summary: SecurityAuditSummary
    findings: list[SecurityFinding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "summary": {
                "critical": self.summary.critical,
                "warn": self.summary.warn,
                "info": self.summary.info,
            },
            "findings": [f.to_dict() for f in self.findings],
        }


class SecurityAudit:
    """
    Framework de auditoria de segurança.

    Exemplo de uso:
    ```python
    audit = SecurityAudit()
    report = audit.run_full_audit()

    if report.summary.critical > 0:
        print("ALERTA: Problemas críticos encontrados!")
        for f in report.findings:
            if f.severity == "critical":
                print(f"  - {f.title}: {f.detail}")
    ```
    """

    # Padrões de secrets comuns
    SECRET_PATTERNS = [
        (r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?[\w-]{20,}['\"]?", "API Key exposta"),
        (r"(?i)(secret|password|passwd|pwd)\s*[=:]\s*['\"]?[\w-]{8,}['\"]?", "Secret/Password exposto"),
        (r"(?i)(token)\s*[=:]\s*['\"]?[\w-]{20,}['\"]?", "Token exposto"),
        (r"(?i)(aws[_-]?access[_-]?key[_-]?id)\s*[=:]\s*['\"]?[A-Z0-9]{20}['\"]?", "AWS Access Key"),
        (r"(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[=:]\s*['\"]?[\w+/]{40}['\"]?", "AWS Secret Key"),
        (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key"),
        (r"(?i)eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*", "JWT Token"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
        (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token"),
    ]

    # Variáveis de ambiente sensíveis
    SENSITIVE_ENV_VARS = [
        "SUPABASE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SHADOW_AGENT_TOKEN",
        "SHADOW_MASTER_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ]

    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def check_exposed_secrets_in_file(self, file_path: Path) -> list[SecurityFinding]:
        """Verifica secrets expostos em um arquivo."""
        findings = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return findings

        for pattern, description in self.SECRET_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                findings.append(SecurityFinding(
                    check_id="SECRET_EXPOSED_IN_FILE",
                    severity="critical",
                    title=f"{description} em arquivo",
                    detail=f"Encontrado em {file_path.relative_to(self.base_path)}",
                    remediation="Remova o secret do arquivo e use variáveis de ambiente",
                ))

        return findings

    def check_exposed_secrets(self) -> list[SecurityFinding]:
        """Verifica secrets expostos em arquivos de configuração."""
        findings = []

        # Arquivos a verificar
        config_patterns = [
            "*.env",
            ".env*",
            "*.json",
            "*.yaml",
            "*.yml",
            "*.toml",
            "config.*",
        ]

        # Diretórios a ignorar
        ignore_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}

        for pattern in config_patterns:
            for file_path in self.base_path.rglob(pattern):
                # Ignora diretórios excluídos
                if any(part in ignore_dirs for part in file_path.parts):
                    continue

                # Ignora .env.example
                if file_path.name.endswith(".example"):
                    continue

                findings.extend(self.check_exposed_secrets_in_file(file_path))

        return findings

    def check_env_vars(self) -> list[SecurityFinding]:
        """Verifica variáveis de ambiente sensíveis."""
        findings = []

        for var in self.SENSITIVE_ENV_VARS:
            value = os.getenv(var)
            if value:
                # Verifica se parece ser um placeholder
                if value.lower() in ["your_key_here", "xxx", "changeme", "placeholder"]:
                    findings.append(SecurityFinding(
                        check_id="ENV_VAR_PLACEHOLDER",
                        severity="warn",
                        title=f"Variável {var} com valor placeholder",
                        detail=f"A variável {var} parece ter um valor de exemplo",
                        remediation=f"Configure um valor real para {var}",
                    ))
            else:
                # Algumas variáveis são opcionais
                if var not in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
                    findings.append(SecurityFinding(
                        check_id="ENV_VAR_MISSING",
                        severity="info",
                        title=f"Variável {var} não configurada",
                        detail=f"A variável {var} não está definida",
                        remediation=f"Configure {var} se necessário",
                    ))

        return findings

    def check_file_permissions(self) -> list[SecurityFinding]:
        """Verifica permissões de arquivos sensíveis."""
        findings = []

        # No Windows, essa verificação é limitada
        if os.name == "nt":
            findings.append(SecurityFinding(
                check_id="PLATFORM_WINDOWS",
                severity="info",
                title="Sistema Windows detectado",
                detail="Verificação de permissões de arquivo limitada no Windows",
                remediation=None,
            ))
            return findings

        # Arquivos sensíveis para verificar
        sensitive_files = [
            ".env",
            ".env.local",
            "shadow.db",
            "credentials.json",
        ]

        for filename in sensitive_files:
            file_path = self.base_path / filename
            if file_path.exists():
                try:
                    mode = file_path.stat().st_mode
                    # Verifica se é legível por outros (o+r)
                    if mode & 0o004:
                        findings.append(SecurityFinding(
                            check_id="FILE_WORLD_READABLE",
                            severity="warn",
                            title=f"Arquivo {filename} legível por todos",
                            detail=f"O arquivo {filename} tem permissões muito abertas",
                            remediation=f"Execute: chmod 600 {filename}",
                        ))
                except Exception:
                    pass

        return findings

    def check_database_security(self) -> list[SecurityFinding]:
        """Verifica segurança do banco de dados."""
        findings = []

        # Verifica se SQLite está em local seguro
        db_path = os.getenv("SHADOW_DB_PATH", "./data/shadow.db")
        db_file = Path(db_path)

        if db_file.exists():
            # Verifica se está em diretório público
            public_dirs = ["public", "static", "www", "html"]
            if any(part in public_dirs for part in db_file.parts):
                findings.append(SecurityFinding(
                    check_id="DB_IN_PUBLIC_DIR",
                    severity="critical",
                    title="Banco de dados em diretório público",
                    detail=f"O arquivo {db_path} está em um diretório público",
                    remediation="Mova o banco de dados para um diretório não público",
                ))

        # Verifica Supabase RLS
        supabase_url = os.getenv("SUPABASE_URL")
        if supabase_url:
            findings.append(SecurityFinding(
                check_id="SUPABASE_RLS_REMINDER",
                severity="info",
                title="Lembre-se de configurar RLS no Supabase",
                detail="Row Level Security deve estar habilitado nas tabelas",
                remediation="Verifique as políticas RLS no painel do Supabase",
            ))

        return findings

    def check_api_security(self) -> list[SecurityFinding]:
        """Verifica segurança da API."""
        findings = []

        # Verifica se token de autenticação está configurado
        agent_token = os.getenv("SHADOW_AGENT_TOKEN")
        if not agent_token:
            findings.append(SecurityFinding(
                check_id="API_NO_AUTH",
                severity="warn",
                title="API sem token de autenticação",
                detail="SHADOW_AGENT_TOKEN não configurado",
                remediation="Configure SHADOW_AGENT_TOKEN para proteger a API",
            ))
        elif len(agent_token) < 32:
            findings.append(SecurityFinding(
                check_id="API_WEAK_TOKEN",
                severity="warn",
                title="Token de API muito curto",
                detail="SHADOW_AGENT_TOKEN deve ter pelo menos 32 caracteres",
                remediation="Use um token mais longo e aleatório",
            ))

        return findings

    def run_full_audit(self) -> SecurityAuditReport:
        """Executa auditoria completa."""
        findings: list[SecurityFinding] = []

        # Executa todas as verificações
        findings.extend(self.check_exposed_secrets())
        findings.extend(self.check_env_vars())
        findings.extend(self.check_file_permissions())
        findings.extend(self.check_database_security())
        findings.extend(self.check_api_security())

        # Calcula resumo
        summary = SecurityAuditSummary()
        for f in findings:
            if f.severity == "critical":
                summary.critical += 1
            elif f.severity == "warn":
                summary.warn += 1
            else:
                summary.info += 1

        return SecurityAuditReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            findings=findings,
        )


class RateLimiter:
    """
    Rate limiter simples baseado em janela deslizante.

    Exemplo de uso:
    ```python
    limiter = RateLimiter(max_requests=10, window_seconds=60)

    if limiter.is_allowed(phone="+5511999999999"):
        # Processa mensagem
        pass
    else:
        # Retorna erro de rate limit
        pass
    ```
    """

    def __init__(
        self,
        max_requests: int = 30,
        window_seconds: int = 60,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup_old_requests(self, key: str) -> None:
        """Remove requisições antigas fora da janela."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[key] = [
            ts for ts in self._requests[key]
            if ts > cutoff
        ]

    def is_allowed(self, key: str) -> bool:
        """
        Verifica se uma requisição é permitida.

        Args:
            key: Identificador único (telefone, IP, etc.)

        Returns:
            True se permitido, False se rate limited
        """
        self._cleanup_old_requests(key)

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(time.time())
        return True

    def remaining(self, key: str) -> int:
        """Retorna número de requisições restantes."""
        self._cleanup_old_requests(key)
        return max(0, self.max_requests - len(self._requests[key]))

    def reset_time(self, key: str) -> float | None:
        """Retorna tempo até reset (em segundos)."""
        if not self._requests[key]:
            return None

        oldest = min(self._requests[key])
        reset_at = oldest + self.window_seconds
        remaining = reset_at - time.time()

        return max(0, remaining)

    def reset(self, key: str) -> None:
        """Reseta contador para uma chave."""
        self._requests[key] = []


class AccessPolicy:
    """
    Política de acesso para controlar quem pode interagir.

    Modos:
    - "open": Qualquer um pode interagir
    - "allowlist": Apenas números na lista permitida
    - "owner_only": Apenas o dono configurado
    """

    def __init__(
        self,
        mode: Literal["open", "allowlist", "owner_only"] = "owner_only",
        owner_phone: str | None = None,
        allowlist: list[str] | None = None,
    ) -> None:
        self.mode = mode
        self.owner_phone = self._normalize_phone(owner_phone) if owner_phone else None
        self.allowlist = {self._normalize_phone(p) for p in (allowlist or [])}

        # Adiciona owner à allowlist automaticamente
        if self.owner_phone:
            self.allowlist.add(self.owner_phone)

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normaliza número de telefone para E.164."""
        # Remove caracteres não numéricos
        digits = re.sub(r"\D", "", phone)

        # Adiciona + se não tiver
        if not digits.startswith("+"):
            digits = f"+{digits}"

        return digits

    def is_allowed(self, phone: str) -> bool:
        """Verifica se um número tem permissão para interagir."""
        normalized = self._normalize_phone(phone)

        if self.mode == "open":
            return True

        if self.mode == "owner_only":
            return normalized == self.owner_phone

        if self.mode == "allowlist":
            return normalized in self.allowlist

        return False

    def add_to_allowlist(self, phone: str) -> None:
        """Adiciona número à allowlist."""
        self.allowlist.add(self._normalize_phone(phone))

    def remove_from_allowlist(self, phone: str) -> None:
        """Remove número da allowlist."""
        normalized = self._normalize_phone(phone)
        if normalized != self.owner_phone:  # Não remove o owner
            self.allowlist.discard(normalized)


# === Singleton global para uso simplificado ===

_rate_limiter: RateLimiter | None = None
_access_policy: AccessPolicy | None = None


def get_rate_limiter() -> RateLimiter:
    """Obtém instância global do RateLimiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            max_requests=int(os.getenv("SHADOW_RATE_LIMIT_MAX", "30")),
            window_seconds=int(os.getenv("SHADOW_RATE_LIMIT_WINDOW", "60")),
        )
    return _rate_limiter


def get_access_policy() -> AccessPolicy:
    """Obtém instância global do AccessPolicy."""
    global _access_policy
    if _access_policy is None:
        owner = os.getenv("SHADOW_OWNER_E164", "")
        mode = os.getenv("SHADOW_ACCESS_MODE", "owner_only")
        allowlist_str = os.getenv("SHADOW_ALLOWLIST", "")
        allowlist = [p.strip() for p in allowlist_str.split(",") if p.strip()]

        _access_policy = AccessPolicy(
            mode=mode,  # type: ignore
            owner_phone=owner,
            allowlist=allowlist,
        )
    return _access_policy


# === Exemplo de uso ===

if __name__ == "__main__":
    # Auditoria
    print("=== Auditoria de Segurança ===\n")
    audit = SecurityAudit()
    report = audit.run_full_audit()

    print(f"Timestamp: {report.timestamp}")
    print(f"Resumo: {report.summary.critical} críticos, {report.summary.warn} avisos, {report.summary.info} info\n")

    for finding in report.findings:
        icon = "🔴" if finding.severity == "critical" else "🟡" if finding.severity == "warn" else "🔵"
        print(f"{icon} [{finding.check_id}] {finding.title}")
        print(f"   {finding.detail}")
        if finding.remediation:
            print(f"   → {finding.remediation}")
        print()

    # Rate Limiter
    print("\n=== Rate Limiter ===\n")
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    phone = "+5511999999999"
    for i in range(7):
        allowed = limiter.is_allowed(phone)
        remaining = limiter.remaining(phone)
        print(f"Request {i+1}: {'✅' if allowed else '❌'} (restantes: {remaining})")

    # Access Policy
    print("\n=== Access Policy ===\n")
    policy = AccessPolicy(mode="owner_only", owner_phone="+5511999999999")

    test_numbers = ["+5511999999999", "+5511888888888", "+5521999999999"]
    for num in test_numbers:
        allowed = policy.is_allowed(num)
        print(f"{num}: {'✅ Permitido' if allowed else '❌ Bloqueado'}")
