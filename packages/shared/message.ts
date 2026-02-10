export type MessageDirection = "inbound" | "outbound";

export type NormalizedMessage = {
  source?: string;
  user_phone?: string;
  contact_phone?: string;
  direction?: MessageDirection;
  content?: string;
  content_type?: "text" | "audio" | "image" | "document";
  timestamp?: string;
  is_group?: boolean;
  metadata?: Record<string, unknown>;
};
