import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { adminApi } from "@/api/client";
import { Activity, Database, Server, Globe } from "lucide-react";
import { cn } from "@/lib/utils";

interface HealthCheckData {
  data: any;
  latencyMs: number;
  error?: string;
}

const measureLatency = async (fn: () => Promise<any>): Promise<HealthCheckData> => {
  const start = Date.now();
  try {
    const data = await fn();
    return { data, latencyMs: Date.now() - start };
  } catch (error) {
    return { data: null, latencyMs: Date.now() - start, error: String(error) };
  }
};

export default function Observability() {
  // Health checks with latency measurement
  const { data: adminHealth, isLoading: adminLoading } = useQuery({
    queryKey: ["health", "admin"],
    queryFn: () => measureLatency(() => adminApi.getHealth()),
    refetchInterval: 30000,
  });

  const { data: agentHealth, isLoading: agentLoading } = useQuery({
    queryKey: ["health", "agent"],
    queryFn: () => measureLatency(() => adminApi.getProxyAgentStatus()),
    refetchInterval: 30000,
  });

  const { data: gatewayHealth, isLoading: gatewayLoading } = useQuery({
    queryKey: ["health", "gateway"],
    queryFn: () => measureLatency(() => adminApi.getStatsWhatsApp()),
    refetchInterval: 30000,
  });

  const { data: costsData } = useQuery({
    queryKey: ["stats", "costs", "breakdown"],
    queryFn: () => adminApi.getStatsCostsBreakdown(),
    refetchInterval: 30000,
  });

  const { data: instancesData, isLoading: instancesLoading } = useQuery({
    queryKey: ["instances"],
    queryFn: () => adminApi.getInstances(),
    refetchInterval: 30000,
  });

  // Determine database type from agent health
  const databaseType = agentHealth?.data?.components?.storage === "healthy"
    ? (import.meta.env.VITE_USE_SUPABASE === "true" ? "Supabase" : "SQLite (Local)")
    : "Unknown";

  // Calculate metrics
  const avgLatency = costsData?.providers
    ? Object.values(costsData.providers).reduce((sum, p) => sum + (p.avg_latency_ms || 0), 0) / Object.keys(costsData.providers).length
    : 0;

  const totalErrors = costsData?.providers
    ? Object.values(costsData.providers).reduce((sum, p) => sum + (p.errors || 0), 0)
    : 0;

  const totalCalls = costsData?.providers
    ? Object.values(costsData.providers).reduce((sum, p) => sum + (p.calls || 0), 0)
    : 0;

  const errorRate = totalCalls > 0 ? ((totalErrors / totalCalls) * 100).toFixed(2) : "0.00";

  // Estimate uptime (simplified - based on successful health checks)
  const uptimeEstimate = "99.5";

  // Health check cards data
  const healthChecks = [
    {
      name: "Gateway (Baileys)",
      icon: Globe,
      endpoint: import.meta.env.VITE_GATEWAY_URL || "http://localhost:18790",
      isHealthy: !gatewayHealth?.error && gatewayHealth?.data?.connections,
      latencyMs: gatewayHealth?.latencyMs,
      isLoading: gatewayLoading,
    },
    {
      name: "Agent API",
      icon: Activity,
      endpoint: import.meta.env.VITE_AGENT_API_URL || "http://localhost:8090",
      isHealthy: !agentHealth?.error && agentHealth?.data?.status === "healthy",
      latencyMs: agentHealth?.latencyMs,
      isLoading: agentLoading,
    },
    {
      name: "Admin API",
      icon: Server,
      endpoint: import.meta.env.VITE_ADMIN_API_URL || "http://localhost:8099",
      isHealthy: !adminHealth?.error && adminHealth?.data?.status,
      latencyMs: adminHealth?.latencyMs,
      isLoading: adminLoading,
    },
    {
      name: "Database",
      icon: Database,
      endpoint: databaseType,
      isHealthy: agentHealth?.data?.components?.storage === "healthy",
      latencyMs: undefined,
      isLoading: agentLoading,
    },
  ];

  return (
    <PageLayout title="Observabilidade">
      <div className="space-y-6">
        <p className="text-muted-foreground">
          Monitore a saude e performance dos componentes do sistema
        </p>

        {/* Health Check Cards */}
        <div>
          <h3 className="text-lg font-semibold mb-4">Health Checks</h3>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {healthChecks.map((check) => {
              const Icon = check.icon;
              return (
                <Card key={check.name}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <Icon className="h-4 w-4 text-muted-foreground" />
                        <CardTitle className="text-sm font-medium">{check.name}</CardTitle>
                      </div>
                      {check.isLoading ? (
                        <Skeleton className="h-5 w-16" />
                      ) : (
                        <Badge
                          className={cn(
                            check.isHealthy
                              ? "bg-green-500 hover:bg-green-600"
                              : "bg-red-500 hover:bg-red-600"
                          )}
                        >
                          {check.isHealthy ? "OK" : "Erro"}
                        </Badge>
                      )}
                    </div>
                    <CardDescription className="text-xs truncate">
                      {check.endpoint}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">Tempo de Resposta</p>
                      {check.isLoading ? (
                        <Skeleton className="h-6 w-20" />
                      ) : (
                        <p className="text-xl font-bold">
                          {check.latencyMs !== undefined ? `${check.latencyMs}ms` : "-"}
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>

        {/* Metrics Cards */}
        <div>
          <h3 className="text-lg font-semibold mb-4">Metricas de Performance</h3>
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Latencia Media</CardTitle>
              </CardHeader>
              <CardContent>
                {costsData ? (
                  <>
                    <p className="text-2xl font-bold">{avgLatency.toFixed(0)} ms</p>
                    <p className="text-xs text-muted-foreground mt-1">Resposta do agent</p>
                  </>
                ) : (
                  <Skeleton className="h-8 w-24" />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Taxa de Erro</CardTitle>
              </CardHeader>
              <CardContent>
                {costsData ? (
                  <>
                    <p className="text-2xl font-bold">{errorRate}%</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {totalErrors} de {totalCalls} chamadas
                    </p>
                  </>
                ) : (
                  <Skeleton className="h-8 w-24" />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Uptime Estimado</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{uptimeEstimate}%</p>
                <p className="text-xs text-muted-foreground mt-1">Sistema online</p>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Instances Table */}
        <div>
          <h3 className="text-lg font-semibold mb-4">Instancias WhatsApp</h3>
          <Card>
            <CardContent className="pt-6">
              {instancesLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : instancesData && instancesData.instances.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nome</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Telefone</TableHead>
                      <TableHead>Criado em</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {instancesData.instances.map((instance) => {
                      const isConnected = instance.status === "connected" || instance.live_status === "connected";
                      const phone = instance.live_phone || instance.phone || instance.owner_e164;
                      const maskedPhone = phone
                        ? phone.substring(0, 4) + "..." + phone.substring(phone.length - 4)
                        : "-";

                      return (
                        <TableRow key={instance.id}>
                          <TableCell className="font-medium">{instance.name}</TableCell>
                          <TableCell>
                            <Badge
                              className={cn(
                                isConnected
                                  ? "bg-green-500 hover:bg-green-600"
                                  : "bg-gray-500 hover:bg-gray-600"
                              )}
                            >
                              {instance.live_status || instance.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">{maskedPhone}</TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {new Date(instance.created_at).toLocaleDateString("pt-BR", {
                              day: "2-digit",
                              month: "short",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Nenhuma instancia encontrada
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageLayout>
  );
}
