export const overviewMock = {
  users_total: 42,
  users_active_24h: 7,
  messages_total: 1280,
  messages_24h: 54,
  tasks_pending: 3,
  appointments_upcoming: 2,
};

export const integrationsMock = {
  baileys: { enabled: true },
};

export const whatsappMock = {
  connections: [
    {
      provider: "baileys",
      instance_id: "local",
      status: "connected",
      details: "connected",
      checked_at: "2026-02-05T12:10:00Z",
    },
  ],
};

export const costsMock = {
  input_tokens: 12000,
  output_tokens: 3400,
  note: "Estimativa local com dados mockados.",
};

export const tablesMock = {
  tables: {
    messages: 1280,
    contacts: 120,
    sessions: 42,
  },
};

export const logsMock = {
  logs: [
    {
      id: "log_1",
      received_at: "2026-02-05T12:00:00Z",
      source: "baileys",
      direction: "inbound",
      contact_phone: "+5511999999999",
    },
    {
      id: "log_2",
      received_at: "2026-02-05T12:05:00Z",
      source: "baileys",
      direction: "outbound",
      contact_phone: "+5511888888888",
    },
  ],
};

export const usersMock = {
  users: [
    {
      id: "user_1",
      phone_number: "+5511999999999",
      name: "Carlos",
      created_at: "2026-01-20",
    },
    {
      id: "user_2",
      phone_number: "+5511888888888",
      name: "Marina",
      created_at: "2026-01-22",
    },
  ],
};

// Instance mocks for QA tests
export const instanceMockConnected = {
  id: "inst-001",
  name: "WhatsApp Pessoal",
  phone: "+5511999999999",
  owner_e164: "+5511999999999",
  gateway_user_id: "inst-001",
  status: "connected",
  live_status: "connected",
  live_phone: "+5511999999999",
  created_at: "2026-02-10T10:00:00Z",
  connected_at: "2026-02-10T10:01:00Z",
  disconnected_at: null,
};

export const instanceMockQrPending = {
  id: "inst-002",
  name: "WhatsApp Empresa",
  phone: null,
  owner_e164: null,
  gateway_user_id: "inst-002",
  status: "qr_pending",
  live_status: "qr_pending",
  live_phone: null,
  created_at: "2026-02-10T12:00:00Z",
  connected_at: null,
  disconnected_at: null,
};

export const instanceMockDisconnected = {
  id: "inst-003",
  name: "WhatsApp Antigo",
  phone: "+5511888888888",
  owner_e164: "+5511888888888",
  gateway_user_id: "inst-003",
  status: "disconnected",
  live_status: "disconnected",
  live_phone: null,
  created_at: "2026-02-01T08:00:00Z",
  connected_at: "2026-02-01T08:01:00Z",
  disconnected_at: "2026-02-09T22:00:00Z",
};

export const instanceStatsMock = {
  messages: 142,
  sessions: 5,
  input_tokens: 85000,
  output_tokens: 12000,
  total_cost: 0.0234,
};

export const instanceConversationsMock = {
  conversations: [
    {
      id: "sess-1",
      participant_phone: "+5511977776666",
      message_count: 23,
      input_tokens: 12000,
      output_tokens: 3000,
      last_activity_at: "2026-02-10T15:30:00Z",
    },
  ],
};

export const instanceCostsMock = {
  providers: {
    anthropic: {
      input_tokens: 85000,
      output_tokens: 12000,
      cost_usd: 0.0198,
      calls: 45,
    },
  },
  total_cost: 0.0198,
  days: 30,
};

export const instanceLogsMock = {
  logs: [
    {
      day: "2026-02-10",
      provider: "anthropic",
      input_tokens: 5000,
      output_tokens: 800,
      cost: 0.0012,
    },
  ],
};
