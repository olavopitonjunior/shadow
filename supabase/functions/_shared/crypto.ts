const ENC_PREFIX = "enc::v1::";
const SALT = new TextEncoder().encode("shadow:user-key:v1");

function b64encode(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes));
}

function b64decode(data: string): Uint8Array {
  const bin = atob(data);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) {
    bytes[i] = bin.charCodeAt(i);
  }
  return bytes;
}

function strToBytes(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function bytesToStr(value: Uint8Array): string {
  return new TextDecoder().decode(value);
}

async function importMasterKey(masterKeyB64: string): Promise<CryptoKey> {
  const raw = b64decode(masterKeyB64);
  return await crypto.subtle.importKey("raw", raw, "HKDF", false, ["deriveKey"]);
}

async function deriveUserKey(masterKey: CryptoKey, userId: string): Promise<CryptoKey> {
  return await crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: SALT,
      info: strToBytes(userId),
    },
    masterKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

function isEncrypted(value: string | null | undefined): boolean {
  return Boolean(value && value.startsWith(ENC_PREFIX));
}

export async function encryptText(
  plaintext: string,
  userId: string,
  aad?: string,
): Promise<string> {
  const masterKeyB64 = Deno.env.get("SHADOW_MASTER_KEY") ?? "";
  if (!masterKeyB64) return plaintext;
  const masterKey = await importMasterKey(masterKeyB64);
  const userKey = await deriveUserKey(masterKey, userId);

  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aadBytes = aad ? strToBytes(aad) : undefined;
  const cipher = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce, additionalData: aadBytes },
    userKey,
    strToBytes(plaintext),
  );

  const payload = {
    alg: "AES-256-GCM",
    nonce: b64encode(nonce),
    ciphertext: b64encode(new Uint8Array(cipher)),
    aad: aadBytes ? b64encode(aadBytes) : null,
  };

  const raw = JSON.stringify(payload);
  return `${ENC_PREFIX}${b64encode(strToBytes(raw))}`;
}

export async function decryptText(
  value: string,
  userId: string,
  aad?: string,
): Promise<string> {
  if (!isEncrypted(value)) return value;
  const masterKeyB64 = Deno.env.get("SHADOW_MASTER_KEY") ?? "";
  if (!masterKeyB64) return value;
  const masterKey = await importMasterKey(masterKeyB64);
  const userKey = await deriveUserKey(masterKey, userId);

  const rawPayload = bytesToStr(b64decode(value.slice(ENC_PREFIX.length)));
  const payload = JSON.parse(rawPayload);
  const nonce = b64decode(payload.nonce);
  const cipher = b64decode(payload.ciphertext);
  const aadBytes = aad
    ? strToBytes(aad)
    : payload.aad
    ? b64decode(payload.aad)
    : undefined;

  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce, additionalData: aadBytes },
    userKey,
    cipher,
  );
  return bytesToStr(new Uint8Array(plain));
}
