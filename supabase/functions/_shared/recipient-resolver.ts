/**
 * Recipient Resolution - Phase 4 (moltbot pattern)
 *
 * Resolves target recipient for message delivery with priority chain:
 * 1. Explicit - recipient specified directly
 * 2. Reminder target - target_phone from reminder record
 * 3. Session - last recipient from active session
 * 4. Config - owner_phone from config
 * 5. Allowlist - first number from allowlist
 */

import { validatePhoneNumber } from "./shadow.ts";

export type RecipientSource =
  | "explicit"
  | "reminder_target"
  | "session"
  | "config"
  | "allowlist";

export interface ResolvedRecipient {
  /** Target phone number in E.164 format */
  phone: string;
  /** How the recipient was resolved */
  source: RecipientSource;
  /** Confidence score (1.0 = explicit, lower = fallback) */
  confidence: number;
  /** Original input if different from resolved */
  original?: string;
}

export interface RecipientContext {
  /** Explicitly specified recipient */
  explicitRecipient?: string;
  /** Target from reminder record */
  reminderTarget?: string;
  /** Session's last recipient */
  sessionRecipient?: string;
  /** Owner phone from config */
  ownerPhone?: string;
  /** Allowlist for fallback */
  allowlist?: string[];
}

/**
 * Resolves the recipient for message delivery
 *
 * Uses priority chain to find the best target:
 * 1. explicitRecipient (highest priority, user-specified)
 * 2. reminderTarget (from reminder record)
 * 3. sessionRecipient (from active session history)
 * 4. ownerPhone (from config)
 * 5. allowlist first entry (lowest priority fallback)
 *
 * @param context Resolution context with possible recipients
 * @returns Resolved recipient or null if none valid
 */
export function resolveRecipient(
  context: RecipientContext
): ResolvedRecipient | null {
  const {
    explicitRecipient,
    reminderTarget,
    sessionRecipient,
    ownerPhone,
    allowlist,
  } = context;

  // 1. Explicit recipient (highest priority)
  if (explicitRecipient) {
    const validated = validatePhoneNumber(explicitRecipient);
    if (validated) {
      return {
        phone: validated,
        source: "explicit",
        confidence: 1.0,
        original: explicitRecipient,
      };
    }
  }

  // 2. Reminder target
  if (reminderTarget) {
    const validated = validatePhoneNumber(reminderTarget);
    if (validated) {
      return {
        phone: validated,
        source: "reminder_target",
        confidence: 0.95,
        original: reminderTarget,
      };
    }
  }

  // 3. Session recipient (from history)
  if (sessionRecipient) {
    const validated = validatePhoneNumber(sessionRecipient);
    if (validated) {
      return {
        phone: validated,
        source: "session",
        confidence: 0.8,
        original: sessionRecipient,
      };
    }
  }

  // 4. Owner phone (config default)
  if (ownerPhone) {
    const validated = validatePhoneNumber(ownerPhone);
    if (validated) {
      return {
        phone: validated,
        source: "config",
        confidence: 0.6,
        original: ownerPhone,
      };
    }
  }

  // 5. Allowlist fallback
  if (allowlist && allowlist.length > 0) {
    for (const phone of allowlist) {
      const validated = validatePhoneNumber(phone);
      if (validated) {
        return {
          phone: validated,
          source: "allowlist",
          confidence: 0.4,
          original: phone,
        };
      }
    }
  }

  // No valid recipient found
  return null;
}

/**
 * Get debug info about resolution process
 */
export function debugRecipientResolution(
  context: RecipientContext
): { checked: string[]; resolved: ResolvedRecipient | null } {
  const checked: string[] = [];

  if (context.explicitRecipient) checked.push("explicit");
  if (context.reminderTarget) checked.push("reminder_target");
  if (context.sessionRecipient) checked.push("session");
  if (context.ownerPhone) checked.push("config");
  if (context.allowlist?.length) checked.push("allowlist");

  return {
    checked,
    resolved: resolveRecipient(context),
  };
}
