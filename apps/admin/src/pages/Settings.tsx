import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { adminApi } from "@/api/client";
import { Key, Server, DollarSign, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Settings() {
  const { data: envData, isLoading: envLoading } = useQuery({
    queryKey: ["config", "environment"],
    queryFn: () => adminApi.getConfigEnvironment(),
    refetchInterval: 60000,
  });

  const { data: providersData, isLoading: providersLoading } = useQuery({
    queryKey: ["config", "providers"],
    queryFn: () => adminApi.getConfigProviders(),
    refetchInterval: 60000,
  });

  const { data: pricingData, isLoading: pricingLoading } = useQuery({
    queryKey: ["config", "pricing"],
    queryFn: () => adminApi.getConfigPricing(),
    refetchInterval: 60000,
  });

  const { data: agentHealth } = useQuery({
    queryKey: ["health", "agent"],
    queryFn: () => adminApi.getProxyAgentStatus(),
    refetchInterval: 30000,
  });

  const { data: gatewayHealth } = useQuery({
    queryKey: ["health", "gateway"],
    queryFn: () => adminApi.getStatsWhatsApp(),
    refetchInterval: 30000,
  });

  // Service connections data
  const serviceConnections = [
    {
      name: "Gateway (Baileys)",
      url: import.meta.env.VITE_GATEWAY_URL || "http://localhost:18790",
      status: gatewayHealth?.connections?.[0]?.status || "unknown",
    },
    {
      name: "Agent API",
      url: import.meta.env.VITE_AGENT_API_URL || "http://localhost:8090",
      status: agentHealth?.status || "unknown",
    },
    {
      name: "Admin API",
      url: import.meta.env.VITE_ADMIN_API_URL || "http://localhost:8099",
      status: "healthy", // We're connected if this is running
    },
  ];

  return (
    <PageLayout title="Configuracoes">
      <div className="space-y-6">
        <p className="text-muted-foreground">
          Configure parametros do sistema e preferencias
        </p>

        {/* Environment Variables Section */}
        <div>
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Key className="h-5 w-5" />
            Variaveis de Ambiente
          </h3>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {envLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <Card key={i}>
                  <CardHeader>
                    <Skeleton className="h-5 w-40" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-4 w-full" />
                  </CardContent>
                </Card>
              ))
            ) : envData?.variables ? (
              Object.entries(envData.variables).map(([key, value]) => (
                <Card key={key}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <CardTitle className="text-sm font-medium truncate">{key}</CardTitle>
                      <Badge
                        className={cn(
                          value.configured
                            ? "bg-green-500 hover:bg-green-600"
                            : "bg-gray-400 hover:bg-gray-500"
                        )}
                      >
                        {value.configured ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs font-mono text-muted-foreground truncate">
                      {value.masked_value || "Nao configurado"}
                    </p>
                  </CardContent>
                </Card>
              ))
            ) : (
              <Card className="col-span-full">
                <CardContent className="py-8 text-center">
                  <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">
                    Nao foi possivel carregar variaveis de ambiente
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>

        {/* Provider Status Section */}
        <div>
          <h3 className="text-lg font-semibold mb-4">Status dos Providers</h3>
          <div className="grid gap-4 md:grid-cols-3">
            {providersLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <Card key={i}>
                  <CardHeader>
                    <Skeleton className="h-5 w-32" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-20 w-full" />
                  </CardContent>
                </Card>
              ))
            ) : providersData?.providers ? (
              Object.entries(providersData.providers).map(([provider, data]) => (
                <Card key={provider}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base capitalize">{provider}</CardTitle>
                      <Badge
                        className={cn(
                          data.configured
                            ? "bg-green-500 hover:bg-green-600"
                            : "bg-red-500 hover:bg-red-600"
                        )}
                      >
                        {data.configured ? "Configurado" : "Ausente"}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-1">
                      <p className="text-xs font-medium text-muted-foreground">Modelos:</p>
                      {data.models && data.models.length > 0 ? (
                        <ul className="space-y-0.5">
                          {data.models.map((model) => (
                            <li key={model} className="text-xs font-mono truncate">
                              {model}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground">Nenhum modelo disponivel</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))
            ) : (
              <Card className="col-span-full">
                <CardContent className="py-8 text-center">
                  <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">
                    Nao foi possivel carregar providers
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>

        {/* Pricing Table Section */}
        <div>
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <DollarSign className="h-5 w-5" />
            Tabela de Precos
          </h3>
          <Card>
            <CardContent className="pt-6">
              {pricingLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : pricingData?.pricing && pricingData.pricing.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Provider</TableHead>
                      <TableHead>Model</TableHead>
                      <TableHead className="text-right">Input ($/MTok)</TableHead>
                      <TableHead className="text-right">Output ($/MTok)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pricingData.pricing.map((item, idx) => (
                      <TableRow key={idx}>
                        <TableCell className="font-medium capitalize">{item.provider}</TableCell>
                        <TableCell className="font-mono text-xs">{item.model}</TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          ${item.input_price_per_mtok.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          ${item.output_price_per_mtok.toFixed(2)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Nenhuma informacao de preco disponivel
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Service Connections Section */}
        <div>
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Server className="h-5 w-5" />
            Conexoes de Servico
          </h3>
          <div className="grid gap-4 md:grid-cols-3">
            {serviceConnections.map((service) => {
              const isHealthy = service.status === "healthy" || service.status === "connected";

              return (
                <Card key={service.name}>
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium">{service.name}</CardTitle>
                      <Badge
                        className={cn(
                          isHealthy
                            ? "bg-green-500 hover:bg-green-600"
                            : "bg-gray-400 hover:bg-gray-500"
                        )}
                      >
                        {service.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs font-mono text-muted-foreground truncate">
                      {service.url}
                    </p>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
