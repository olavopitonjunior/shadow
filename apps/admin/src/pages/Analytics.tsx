import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { analyticsApi } from "@/api/client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const AGENT_COLORS: Record<string, string> = {
  supervisor: "#6366f1",
  crm: "#06b6d4",
  planner: "#f97316",
  analytics: "#ec4899",
  docgen: "#8b5cf6",
  collector: "#14b8a6",
};

export default function Analytics() {
  const { data: overview } = useQuery({
    queryKey: ["analytics", "overview"],
    queryFn: () => analyticsApi.getOverview(),
    refetchInterval: 30000,
  });
  const { data: toolUsage } = useQuery({
    queryKey: ["analytics", "tools"],
    queryFn: analyticsApi.getToolUsage,
    refetchInterval: 30000,
  });
  const { data: agentStats } = useQuery({
    queryKey: ["analytics", "agents"],
    queryFn: analyticsApi.getAgentStats,
    refetchInterval: 30000,
  });
  const { data: quality } = useQuery({
    queryKey: ["analytics", "quality"],
    queryFn: analyticsApi.getQuality,
    refetchInterval: 60000,
  });

  const metrics = [
    { label: "Tarefas", value: overview?.tasks_total ?? "-" },
    { label: "Compromissos", value: overview?.appointments_total ?? "-" },
    { label: "Conclusao", value: overview?.completion_rate ? `${overview.completion_rate}%` : "-" },
    { label: "Contatos", value: overview?.contacts_total ?? "-" },
  ];

  // Tool usage chart data
  const toolData = (toolUsage?.tools || []).slice(0, 10);

  // Agent stats pie data
  const agentCalls = agentStats?.agent_calls || {};
  const pieData = Object.entries(agentCalls)
    .filter(([name]) => name in AGENT_COLORS)
    .map(([name, calls]) => ({
      name,
      value: calls as number,
      color: AGENT_COLORS[name] || "#94a3b8",
    }));

  return (
    <PageLayout title="Analytics">
      <div className="space-y-6">
        {/* Metric Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {metrics.map((m) => (
            <Card key={m.label}>
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-bold">{m.value}</p>
                <p className="text-sm text-muted-foreground">{m.label}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Tool Usage Heatmap */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Uso de Tools (Top 10)</CardTitle>
            </CardHeader>
            <CardContent>
              {toolData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={toolData} layout="vertical" margin={{ left: 100 }}>
                    <XAxis type="number" />
                    <YAxis dataKey="name" type="category" tick={{ fontSize: 12 }} width={100} />
                    <Tooltip />
                    <Bar dataKey="calls" fill="#6366f1" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Dados de uso serao coletados quando o LangGraph estiver ativo
                </p>
              )}
            </CardContent>
          </Card>

          {/* Agent Distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Distribuicao por Agente</CardTitle>
            </CardHeader>
            <CardContent>
              {pieData.length > 0 ? (
                <div className="flex items-center gap-4">
                  <ResponsiveContainer width="50%" height={250}>
                    <PieChart>
                      <Pie
                        data={pieData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        innerRadius={40}
                      >
                        {pieData.map((entry) => (
                          <Cell key={entry.name} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="space-y-2">
                    {pieData.map((d) => (
                      <div key={d.name} className="flex items-center gap-2 text-sm">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: d.color }} />
                        <span className="capitalize">{d.name}</span>
                        <span className="text-muted-foreground ml-auto">{d.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Dados de agentes serao coletados quando o LangGraph estiver ativo
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Quality Metrics */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Qualidade das Conversas</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-6">
              <div className="text-center">
                <p className="text-3xl font-bold text-green-600">
                  {quality?.task_completion_rate ?? "-"}%
                </p>
                <p className="text-sm text-muted-foreground">Taxa de conclusao</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-bold text-blue-600">
                  {quality?.avg_steps_per_task ?? "-"}
                </p>
                <p className="text-sm text-muted-foreground">Passos por tarefa</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-bold text-purple-600">
                  {quality?.tool_accuracy ?? "-"}%
                </p>
                <p className="text-sm text-muted-foreground">Precisao de tools</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
