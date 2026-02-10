import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { FileText, AlertCircle, Webhook, Search } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { adminApi } from "@/api/client";

type LogTab = "webhook" | "application" | "errors";

const tabs: { id: LogTab; label: string; icon: React.ElementType }[] = [
  { id: "webhook", label: "Webhook", icon: Webhook },
  { id: "application", label: "Aplicacao", icon: FileText },
  { id: "errors", label: "Erros", icon: AlertCircle },
];

function formatTime(isoString?: string): string {
  if (!isoString) return "-";
  try {
    const date = new Date(isoString);
    return date.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "-";
  }
}

function maskPhone(phone?: string): string {
  if (!phone) return "-";
  if (phone.length <= 4) return phone;
  return `...${phone.slice(-4)}`;
}

function formatTokens(tokens?: number): string {
  if (!tokens) return "0";
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`;
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
  return String(tokens);
}

function formatCost(cost?: number): string {
  if (!cost) return "$0.00";
  return `$${cost.toFixed(4)}`;
}

export default function Logs() {
  const [activeTab, setActiveTab] = useState<LogTab>("webhook");

  // Filter states
  const [instanceId, setInstanceId] = useState<string>("");
  const [direction, setDirection] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");

  // Fetch instances for dropdown
  const { data: instancesData } = useQuery({
    queryKey: ["instances"],
    queryFn: adminApi.getInstances,
  });

  // Webhook logs query
  const { data: webhookData, isLoading: webhookLoading } = useQuery({
    queryKey: ["webhookLogs", instanceId, direction, search, dateFrom, dateTo],
    queryFn: () => adminApi.getWebhookLogs({
      source: instanceId || undefined,
      direction: direction || undefined,
      search: search || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: 100,
    }),
    enabled: activeTab === "webhook",
  });

  // Application logs (usage history)
  const { data: usageData, isLoading: usageLoading } = useQuery({
    queryKey: ["usageHistory"],
    queryFn: adminApi.getStatsUsageHistory,
    enabled: activeTab === "application",
  });

  // Error logs query
  const { data: errorData, isLoading: errorLoading } = useQuery({
    queryKey: ["errorLogs"],
    queryFn: () => adminApi.getErrorLogs(50),
    enabled: activeTab === "errors",
  });

  const webhookLogs = webhookData?.logs || [];
  const usageHistory = usageData?.history || [];
  const errorLogs = errorData?.errors || [];

  // Calculate stats
  const totalLogs = webhookLogs.length;
  const errorCount = errorLogs.length;
  const warningCount = 0; // Not yet implemented

  const handleResetFilters = () => {
    setInstanceId("");
    setDirection("");
    setSearch("");
    setDateFrom("");
    setDateTo("");
  };

  return (
    <PageLayout title="Logs">
      <div className="space-y-4">
        <p className="text-muted-foreground">
          Visualize e filtre logs de diferentes componentes do sistema
        </p>

        <div className="flex gap-2 border-b">
          {tabs.map((tab) => (
            <Button
              key={tab.id}
              variant="ghost"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "rounded-b-none border-b-2",
                activeTab === tab.id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground"
              )}
            >
              <tab.icon className="w-4 h-4 mr-2" />
              {tab.label}
            </Button>
          ))}
        </div>

        {/* Filters Bar - Only for webhook tab */}
        {activeTab === "webhook" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Filtros</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
                {/* Instance dropdown */}
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Instancia
                  </label>
                  <select
                    value={instanceId}
                    onChange={(e) => setInstanceId(e.target.value)}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">Todas</option>
                    {instancesData?.instances.map((instance) => (
                      <option key={instance.id} value={instance.id}>
                        {instance.name} ({maskPhone(instance.phone)})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Direction dropdown */}
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Direcao
                  </label>
                  <select
                    value={direction}
                    onChange={(e) => setDirection(e.target.value)}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">Todos</option>
                    <option value="inbound">Inbound</option>
                    <option value="outbound">Outbound</option>
                  </select>
                </div>

                {/* Search input */}
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Buscar Telefone
                  </label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder="Buscar..."
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                </div>

                {/* Date from */}
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Data Inicial
                  </label>
                  <Input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                  />
                </div>

                {/* Date to */}
                <div>
                  <label className="text-xs text-muted-foreground mb-1 block">
                    Data Final
                  </label>
                  <Input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                  />
                </div>
              </div>

              <div className="mt-4">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleResetFilters}
                >
                  Limpar Filtros
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Webhook Tab */}
        {activeTab === "webhook" && (
          <Card>
            <CardHeader>
              <CardTitle>Webhook Logs</CardTitle>
              <CardDescription>
                Requisicoes recebidas do WhatsApp
              </CardDescription>
            </CardHeader>
            <CardContent>
              {webhookLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : webhookLogs.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-medium">Data/Hora</th>
                        <th className="text-left py-3 px-4 font-medium">Fonte</th>
                        <th className="text-left py-3 px-4 font-medium">Direcao</th>
                        <th className="text-left py-3 px-4 font-medium">Telefone</th>
                        <th className="text-left py-3 px-4 font-medium">Tipo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {webhookLogs.map((log) => (
                        <tr
                          key={log.id}
                          className="border-b last:border-0 hover:bg-muted/50"
                        >
                          <td className="py-3 px-4 text-xs text-muted-foreground">
                            {formatTime(log.received_at)}
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant="outline">{log.source}</Badge>
                          </td>
                          <td className="py-3 px-4">
                            <Badge
                              variant={log.direction === "inbound" ? "default" : "secondary"}
                            >
                              {log.direction}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 font-mono">
                            {maskPhone(log.contact_phone || log.user_phone)}
                          </td>
                          <td className="py-3 px-4 text-xs text-muted-foreground">
                            {log.content_type || "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <Webhook className="w-12 h-12 text-muted-foreground mb-4" />
                  <p className="text-sm text-muted-foreground">
                    Nenhum log registrado
                  </p>
                  {webhookData?.source === "no_storage" && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Nota: Supabase nao configurado
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Application Tab */}
        {activeTab === "application" && (
          <Card>
            <CardHeader>
              <CardTitle>Historico de Uso da API</CardTitle>
              <CardDescription>
                Logs de uso de APIs e tokens consumidos
              </CardDescription>
            </CardHeader>
            <CardContent>
              {usageLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : usageHistory.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-medium">Data</th>
                        <th className="text-left py-3 px-4 font-medium">Provider</th>
                        <th className="text-left py-3 px-4 font-medium">Modelo</th>
                        <th className="text-left py-3 px-4 font-medium">Input Tokens</th>
                        <th className="text-left py-3 px-4 font-medium">Output Tokens</th>
                        <th className="text-left py-3 px-4 font-medium">Custo</th>
                        <th className="text-left py-3 px-4 font-medium">Chamadas</th>
                        <th className="text-left py-3 px-4 font-medium">Latencia</th>
                      </tr>
                    </thead>
                    <tbody>
                      {usageHistory.map((usage, idx) => (
                        <tr
                          key={`${usage.day}-${usage.provider}-${idx}`}
                          className="border-b last:border-0 hover:bg-muted/50"
                        >
                          <td className="py-3 px-4 text-xs text-muted-foreground">
                            {new Date(usage.day).toLocaleDateString("pt-BR")}
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant="outline">{usage.provider}</Badge>
                          </td>
                          <td className="py-3 px-4 text-xs">
                            {usage.model || "-"}
                          </td>
                          <td className="py-3 px-4">
                            {formatTokens(usage.input_tokens)}
                          </td>
                          <td className="py-3 px-4">
                            {formatTokens(usage.output_tokens)}
                          </td>
                          <td className="py-3 px-4 font-mono text-xs">
                            {formatCost(usage.cost)}
                          </td>
                          <td className="py-3 px-4">
                            {usage.calls}
                          </td>
                          <td className="py-3 px-4 text-xs text-muted-foreground">
                            {usage.avg_latency_ms ? `${usage.avg_latency_ms.toFixed(0)}ms` : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <FileText className="w-12 h-12 text-muted-foreground mb-4" />
                  <p className="text-sm text-muted-foreground">
                    Nenhum log de uso registrado
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Errors Tab */}
        {activeTab === "errors" && (
          <Card>
            <CardHeader>
              <CardTitle>Logs de Erro</CardTitle>
              <CardDescription>
                Erros e excecoes capturadas pelo sistema
              </CardDescription>
            </CardHeader>
            <CardContent>
              {errorLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : errorLogs.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-medium">Data/Hora</th>
                        <th className="text-left py-3 px-4 font-medium">Tipo</th>
                        <th className="text-left py-3 px-4 font-medium">Mensagem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {errorLogs.map((error: any, idx: number) => (
                        <tr
                          key={idx}
                          className="border-b last:border-0 hover:bg-muted/50"
                        >
                          <td className="py-3 px-4 text-xs text-muted-foreground">
                            {formatTime(error.timestamp)}
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant="destructive">{error.type || "Error"}</Badge>
                          </td>
                          <td className="py-3 px-4 text-xs">
                            {error.message || "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <AlertCircle className="w-12 h-12 text-muted-foreground mb-4" />
                  <p className="text-sm text-muted-foreground">
                    Nenhum erro registrado
                  </p>
                  {errorData?.note && (
                    <p className="text-xs text-muted-foreground mt-2">
                      {errorData.note}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Stats Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Total de Logs</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{totalLogs}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Webhooks registrados
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Erros</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{errorCount}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Erros capturados
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Warnings</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{warningCount}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Avisos registrados
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageLayout>
  );
}
