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
