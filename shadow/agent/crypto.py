import base64
import json
import os
from dataclasses import dataclass
from typing import Any

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
except Exception:  # pragma: no cover - optional dependency
    AESGCM = None  # type: ignore
    HKDF = None  # type: ignore
    hashes = None  # type: ignore

ENC_PREFIX = "enc::v1::"
DEFAULT_SALT = b"shadow:user-key:v1"


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data.encode("utf-8"))


@dataclass
class CryptoConfig:
    master_key_b64: str | None
    default_user_id: str | None


class CryptoManager:
    def __init__(self, config: CryptoConfig) -> None:
        self._config = config
        self._enabled = bool(config.master_key_b64 and AESGCM and HKDF and hashes)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_master_key(self) -> bytes | None:
        if not self._config.master_key_b64:
            return None
        try:
            return _b64decode(self._config.master_key_b64)
        except Exception:
            return None

    def _derive_user_key(self, user_id: str) -> bytes | None:
        if not self.enabled:
            return None
        master = self._get_master_key()
        if not master:
            return None
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=DEFAULT_SALT,
            info=user_id.encode("utf-8"),
        )
        return hkdf.derive(master)

    def _resolve_user_id(self, user_id: str | None) -> str | None:
        return user_id or self._config.default_user_id

    def is_encrypted(self, value: str | None) -> bool:
        return bool(value and isinstance(value, str) and value.startswith(ENC_PREFIX))

    def encrypt_text(self, text: str, user_id: str | None = None, aad: str | None = None) -> str:
        if not text:
            return text
        if not self.enabled:
            return text
        uid = self._resolve_user_id(user_id)
        if not uid:
            return text
        key = self._derive_user_key(uid)
        if not key:
            return text
        nonce = os.urandom(12)
        aead = AESGCM(key)
        aad_bytes = aad.encode("utf-8") if aad else None
        cipher = aead.encrypt(nonce, text.encode("utf-8"), aad_bytes)
        payload = {
            "alg": "AES-256-GCM",
            "nonce": _b64encode(nonce),
            "ciphertext": _b64encode(cipher),
            "aad": _b64encode(aad_bytes) if aad_bytes else None,
        }
        raw = json.dumps(payload, separators=(",", ":"))
        return f"{ENC_PREFIX}{_b64encode(raw.encode('utf-8'))}"

    def decrypt_text(self, value: str, user_id: str | None = None, aad: str | None = None) -> str:
        if not value:
            return value
        if not self.is_encrypted(value):
            return value
        if not self.enabled:
            return value
        uid = self._resolve_user_id(user_id)
        if not uid:
            return value
        key = self._derive_user_key(uid)
        if not key:
            return value
        try:
            b64_payload = value[len(ENC_PREFIX):]
            raw = _b64decode(b64_payload).decode("utf-8")
            payload = json.loads(raw)
            nonce = _b64decode(payload["nonce"])
            cipher = _b64decode(payload["ciphertext"])
            if aad is not None:
                aad_bytes = aad.encode("utf-8")
            else:
                aad_b64 = payload.get("aad")
                aad_bytes = _b64decode(aad_b64) if aad_b64 else None
            aead = AESGCM(key)
            plain = aead.decrypt(nonce, cipher, aad_bytes)
            return plain.decode("utf-8")
        except Exception:
            return value

    def encrypt_json(self, data: Any, user_id: str | None = None, aad: str | None = None) -> str:
        raw = json.dumps(data, ensure_ascii=False)
        return self.encrypt_text(raw, user_id=user_id, aad=aad)

    def decrypt_json(self, value: str, user_id: str | None = None, aad: str | None = None, default: Any = None) -> Any:
        if not value:
            return default
        raw = self.decrypt_text(value, user_id=user_id, aad=aad)
        try:
            return json.loads(raw)
        except Exception:
            return default


_crypto_instance: CryptoManager | None = None


def get_crypto() -> CryptoManager:
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = CryptoManager(
            CryptoConfig(
                master_key_b64=os.getenv("SHADOW_MASTER_KEY"),
                default_user_id=os.getenv("SHADOW_OWNER_E164"),
            )
        )
    return _crypto_instance
