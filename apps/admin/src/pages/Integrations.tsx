import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { integrationsApi } from "@/api/client";
import { Plug, RefreshCw, Database, Brain, MessageSquare, Cpu } from "lucide-react";

const ICONS: Record<string, React.ElementType> = {
  gateway: MessageSquare,
  llm_provider: Cpu,
  vector_db: Database,
  observability: Brain,
  orchestration: Brain,
};

const STATUS_COLORS: Record<string, string> = {
  connected: "bg-green-500",
  active: "bg-green-500",
  configured: "bg-blue-500",
  ready: "bg-blue-500",
  inactive: "bg-gray-400",
  not_configured: "bg-gray-400",
  disconnected: "bg-red-500",
  not_initialized: "bg-yellow-500",
};

export default function Integrations() {
  const { data, refetch } = useQuery({
    queryKey: ["integrations"],
    queryFn: integrationsApi.list,
    refetchInterval: 30000,
  });

  const { data: lanceStats } = useQuery({
    queryKey: ["integrations", "lancedb"],
    queryFn: integrationsApi.getLancedbStats,
    refetchInterval: 60000,
  });

  const integrations = data?.integrations || [];

  // Group by type
  const grouped: Record<string, any[]> = {};
  for (const item of integrations) {
    const type = item.type || "other";
    if (!grouped[type]) grouped[type] = [];
    grouped[type].push(item);
  }

  const typeLabels: Record<string, string> = {
    gateway: "WhatsApp Gateways",
    llm_provider: "LLM Providers",
    vector_db: "Vector Database",
    observability: "Observabilidade",
    orchestration: "Orquestracao",
  };

  return (
    <PageLayout title="Integracoes">
      <div className="space-y-6">
        {Object.entries(grouped).map(([type, items]) => (
          <div key={type}>
            <h2 className="text-lg font-semibold mb-3">{typeLabels[type] || type}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {items.map((item: any) => {
                const Icon = ICONS[type] || Plug;
                const statusColor = STATUS_COLORS[item.status] || "bg-gray-400";

                return (
                  <Card key={item.name}>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                      <div className="flex items-center gap-3">
                        <Icon className="w-5 h-5 text-muted-foreground" />
                        <CardTitle className="text-base capitalize">
                          {item.display_name || item.name}
                        </CardTitle>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className={`w-2.5 h-2.5 rounded-full ${statusColor}`} />
                        <Badge
                          variant={item.status === "connected" || item.status === "active" ? "default" : "outline"}
                          className="text-xs"
                        >
                          {item.status}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {item.url && (
                        <p className="text-xs text-muted-foreground font-mono truncate">{item.url}</p>
                      )}
                      {item.instance_id && (
                        <p className="text-xs text-muted-foreground">
                          Instance: {item.instance_id}
                        </p>
                      )}
                      {item.latency_ms !== undefined && (
                        <p className="text-xs text-muted-foreground">
                          Latencia: {item.latency_ms}ms
                        </p>
                      )}
                      {item.project && (
                        <p className="text-xs text-muted-foreground">
                          Projeto: {item.project}
                        </p>
                      )}
                      {item.path && (
                        <p className="text-xs text-muted-foreground font-mono truncate">
                          {item.path}
                        </p>
                      )}

                      {item.status !== "not_configured" && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="w-full mt-2"
                          onClick={() => integrationsApi.reconnect(item.name).then(() => refetch())}
                        >
                          <RefreshCw className="w-3 h-3 mr-1" />
                          Reconectar
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        ))}

        {/* LanceDB Stats */}
        {lanceStats && !lanceStats.error && (
          <div>
            <h2 className="text-lg font-semibold mb-3">LanceDB - Estatisticas</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardContent className="p-4 text-center">
                  <p className="text-2xl font-bold">{lanceStats.table_count || 0}</p>
                  <p className="text-sm text-muted-foreground">Tabelas</p>
                </CardContent>
              </Card>
              {Object.entries(lanceStats.tables || {}).map(([name, stats]: [string, any]) => (
                <Card key={name}>
                  <CardContent className="p-4">
                    <p className="font-medium text-sm">{name}</p>
                    <p className="text-2xl font-bold mt-1">{stats.row_count || 0}</p>
                    <p className="text-xs text-muted-foreground">vetores</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
