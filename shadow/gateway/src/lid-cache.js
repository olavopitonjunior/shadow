import fs from "node:fs/promises";
import path from "node:path";

/**
 * LID Cache - Persistent cache for LID (Linked ID) to E.164 phone number mappings.
 *
 * WhatsApp LIDs are opaque identifiers that don't contain phone numbers.
 * This cache stores mappings learned from Baileys events and successful resolutions.
 */
export class LidCache {
  /**
   * @param {Object} options
   * @param {string} [options.persistPath] - Path to persist cache (JSON file)
   * @param {number} [options.ttlMs=86400000] - TTL in ms (default 24 hours)
   * @param {number} [options.maxSize=10000] - Max entries before eviction
   * @param {Object} [options.logger] - Logger instance
   */
  constructor(options = {}) {
    this.persistPath = options.persistPath || null;
    this.ttlMs = options.ttlMs ?? 86400000; // 24 hours default
    this.maxSize = options.maxSize ?? 10000;
    this.logger = options.logger || null;

    // Bidirectional maps: LID -> { e164, timestamp } and E164 -> LID
    this.lidToE164 = new Map();
    this.e164ToLid = new Map();

    // Stats
    this.hits = 0;
    this.misses = 0;

    // Debounce save
    this.saveTimeout = null;
    this.saveDebounceMs = 5000; // Save at most every 5 seconds
  }

  /**
   * Normalize LID to canonical form (strip device suffix, lowercase).
   * "45119336108132:5@lid" -> "45119336108132@lid"
   */
  _normalizeLid(lid) {
    if (!lid || typeof lid !== "string") return null;
    const match = lid.match(/^(\d+)(?::\d+)?@lid$/i);
    if (!match) return null;
    return `${match[1]}@lid`.toLowerCase();
  }

  /**
   * Normalize E.164 phone number.
   */
  _normalizeE164(e164) {
    if (!e164 || typeof e164 !== "string") return null;
    const digits = e164.replace(/[^\d+]/g, "");
    if (!digits) return null;
    return digits.startsWith("+") ? digits : `+${digits}`;
  }

  /**
   * Store a LID -> E.164 mapping.
   * @param {string} lid - LID JID
   * @param {string} e164 - E.164 phone number
   */
  set(lid, e164) {
    const normalizedLid = this._normalizeLid(lid);
    const normalizedE164 = this._normalizeE164(e164);

    if (!normalizedLid || !normalizedE164) return;

    // Check if already exists with same value
    const existing = this.lidToE164.get(normalizedLid);
    if (existing && existing.e164 === normalizedE164) {
      // Just update timestamp
      existing.timestamp = Date.now();
      this._scheduleSave();
      return;
    }

    // Evict oldest entries if at max size
    if (this.lidToE164.size >= this.maxSize) {
      this._evictOldest();
    }

    // Store mapping
    this.lidToE164.set(normalizedLid, {
      e164: normalizedE164,
      timestamp: Date.now(),
    });
    this.e164ToLid.set(normalizedE164, normalizedLid);

    if (this.logger) {
      this.logger.debug({ lid: normalizedLid, e164: normalizedE164 }, "LID cache: stored mapping");
    }

    this._scheduleSave();
  }

  /**
   * Get E.164 phone number for a LID.
   * @param {string} lid - LID JID
   * @returns {string|null} - E.164 phone number or null
   */
  getE164(lid) {
    const normalizedLid = this._normalizeLid(lid);
    if (!normalizedLid) {
      this.misses++;
      return null;
    }

    const entry = this.lidToE164.get(normalizedLid);
    if (!entry) {
      this.misses++;
      return null;
    }

    // Check TTL
    if (Date.now() - entry.timestamp > this.ttlMs) {
      this._delete(normalizedLid);
      this.misses++;
      return null;
    }

    this.hits++;
    return entry.e164;
  }

  /**
   * Get LID for an E.164 phone number.
   * @param {string} e164 - E.164 phone number
   * @returns {string|null} - LID or null
   */
  getLid(e164) {
    const normalizedE164 = this._normalizeE164(e164);
    if (!normalizedE164) return null;

    const lid = this.e164ToLid.get(normalizedE164);
    if (!lid) return null;

    // Check if LID entry is still valid
    const entry = this.lidToE164.get(lid);
    if (!entry || Date.now() - entry.timestamp > this.ttlMs) {
      this._delete(lid);
      return null;
    }

    return lid;
  }

  /**
   * Check if a LID is in the cache.
   * @param {string} lid - LID JID
   * @returns {boolean}
   */
  has(lid) {
    const normalizedLid = this._normalizeLid(lid);
    if (!normalizedLid) return false;

    const entry = this.lidToE164.get(normalizedLid);
    if (!entry) return false;

    // Check TTL
    if (Date.now() - entry.timestamp > this.ttlMs) {
      this._delete(normalizedLid);
      return false;
    }

    return true;
  }

  /**
   * Delete a LID mapping.
   */
  _delete(normalizedLid) {
    const entry = this.lidToE164.get(normalizedLid);
    if (entry) {
      this.e164ToLid.delete(entry.e164);
      this.lidToE164.delete(normalizedLid);
      this._scheduleSave();
    }
  }

  /**
   * Evict oldest entries to make room.
   */
  _evictOldest() {
    const entries = Array.from(this.lidToE164.entries());
    entries.sort((a, b) => a[1].timestamp - b[1].timestamp);

    // Remove oldest 10%
    const toRemove = Math.max(1, Math.floor(this.maxSize * 0.1));
    for (let i = 0; i < toRemove && i < entries.length; i++) {
      this._delete(entries[i][0]);
    }

    if (this.logger) {
      this.logger.debug({ removed: toRemove }, "LID cache: evicted oldest entries");
    }
  }

  /**
   * Get cache statistics.
   * @returns {{ size: number, hits: number, misses: number, hitRate: number }}
   */
  getStats() {
    const total = this.hits + this.misses;
    return {
      size: this.lidToE164.size,
      hits: this.hits,
      misses: this.misses,
      hitRate: total > 0 ? this.hits / total : 0,
    };
  }

  /**
   * Schedule a debounced save operation.
   */
  _scheduleSave() {
    if (!this.persistPath) return;

    if (this.saveTimeout) {
      clearTimeout(this.saveTimeout);
    }

    this.saveTimeout = setTimeout(() => {
      this.save().catch((err) => {
        if (this.logger) {
          this.logger.error({ err: String(err) }, "LID cache: save failed");
        }
      });
    }, this.saveDebounceMs);
  }

  /**
   * Load cache from persistent storage.
   * @returns {Promise<void>}
   */
  async load() {
    if (!this.persistPath) return;

    try {
      const data = await fs.readFile(this.persistPath, "utf8");
      const parsed = JSON.parse(data);

      if (!Array.isArray(parsed.entries)) {
        throw new Error("Invalid cache format");
      }

      const now = Date.now();
      let loaded = 0;
      let expired = 0;

      for (const entry of parsed.entries) {
        if (!entry.lid || !entry.e164 || !entry.timestamp) continue;

        // Skip expired entries
        if (now - entry.timestamp > this.ttlMs) {
          expired++;
          continue;
        }

        this.lidToE164.set(entry.lid, {
          e164: entry.e164,
          timestamp: entry.timestamp,
        });
        this.e164ToLid.set(entry.e164, entry.lid);
        loaded++;
      }

      if (this.logger) {
        this.logger.info({ loaded, expired, path: this.persistPath }, "LID cache: loaded from file");
      }
    } catch (err) {
      if (err.code === "ENOENT") {
        // File doesn't exist yet - that's fine
        if (this.logger) {
          this.logger.debug({ path: this.persistPath }, "LID cache: no existing cache file");
        }
      } else {
        if (this.logger) {
          this.logger.warn({ err: String(err), path: this.persistPath }, "LID cache: load failed");
        }
      }
    }
  }

  /**
   * Save cache to persistent storage.
   * @returns {Promise<void>}
   */
  async save() {
    if (!this.persistPath) return;

    try {
      // Ensure directory exists
      const dir = path.dirname(this.persistPath);
      await fs.mkdir(dir, { recursive: true });

      // Serialize entries
      const entries = [];
      for (const [lid, { e164, timestamp }] of this.lidToE164) {
        entries.push({ lid, e164, timestamp });
      }

      const data = JSON.stringify({ entries, savedAt: Date.now() }, null, 2);
      await fs.writeFile(this.persistPath, data, "utf8");

      if (this.logger) {
        this.logger.debug({ entries: entries.length, path: this.persistPath }, "LID cache: saved to file");
      }
    } catch (err) {
      if (this.logger) {
        this.logger.error({ err: String(err), path: this.persistPath }, "LID cache: save failed");
      }
      throw err;
    }
  }

  /**
   * Clear the cache.
   */
  clear() {
    this.lidToE164.clear();
    this.e164ToLid.clear();
    this.hits = 0;
    this.misses = 0;
    this._scheduleSave();
  }
}

export default LidCache;
