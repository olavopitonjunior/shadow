import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/api/client";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { useState } from "react";
import { AlertCircle, ArrowLeft, Power, PowerOff, MessageSquare, DollarSign, FileText, Info, X } from "lucide-react";

const statusConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; className?: string }> = {
  connected: { label: "Conectado", variant: "default", className: "bg-green-500 hover:bg-green-600" },
  qr_pending: { label: "QR Pendente", variant: "secondary", className: "bg-yellow-500 hover:bg-yellow-600 text-white" },
  connecting: { label: "Conectando", variant: "secondary" },
  disconnected: { label: "Desconectado", variant: "outline" },
  logged_out: { label: "Deslogado", variant: "destructive" },
};

function maskPhone(phone: string): string {
  if (!phone) return "-";
  const clean = phone.replace(/[^0-9+]/g, "");
  if (clean.length > 4) return "..." + clean.slice(-4);
  return clean;
}

export default function InstanceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: instance, isLoading } = useQuery({
    queryKey: ["instance", id],
    queryFn: () => adminApi.getInstanceDetail(id!),
    enabled: !!id,
  });

  const { data: stats } = useQuery({
    queryKey: ["instance-stats", id],
    queryFn: () => adminApi.getInstanceStats(id!),
    enabled: !!id,
  });

  const { data: conversationsData } = useQuery({
    queryKey: ["instance-conversations", id],
    queryFn: () => adminApi.getInstanceConversations(id!),
    enabled: !!id,
  });

  const { data: costsData } = useQuery({
    queryKey: ["instance-costs", id],
    queryFn: () => adminApi.getInstanceCosts(id!),
    enabled: !!id,
  });

  const { data: logsData } = useQuery({
    queryKey: ["instance-logs", id],
    queryFn: () => adminApi.getInstanceLogs(id!),
    enabled: !!id,
  });

  const disconnectMutation = useMutation({
    mutationFn: () => adminApi.disconnectInstance(id!),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["instance", id] });
      queryClient.invalidateQueries({ queryKey: ["instances"] });
    },
    onError: (err: Error) => setError(`Erro ao desconectar: ${err.message}`),
  });

  const connectMutation = useMutation({
    mutationFn: () => adminApi.connectInstance(id!),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["instance", id] });
    },
    onError: (err: Error) => setError(`Erro ao conectar: ${err.message}`),
  });

  if (isLoading) {
    return (
      <PageLayout title="Instancia">
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64" />
        </div>
      </PageLayout>
    );
  }

  if (!instance) {
    return (
      <PageLayout title="Instancia">
        <div className="text-center py-16">
          <p className="text-muted-foreground">Instancia nao encontrada</p>
          <Button variant="outline" className="mt-4" onClick={() => navigate("/instances")}>
            Voltar
          </Button>
        </div>
      </PageLayout>
    );
  }

  const status = instance.live_status || instance.status;
  const phone = instance.live_phone || instance.phone;
  const config = statusConfig[status] || statusConfig.disconnected;
  const conversations = conversationsData?.conversations || [];
  const costs = costsData || { providers: {}, total_cost: 0, days: 30 };
  const logs = logsData?.logs || [];

  return (
    <PageLayout title={instance.name}>
      {/* Header with back button and actions */}
      <div className="flex items-center justify-between mb-6">
        <Button variant="ghost" onClick={() => navigate("/instances")}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Instancias
        </Button>
        <div className="flex items-center gap-2">
          <Badge variant={config.variant} className={config.className}>
            {config.label}
          </Badge>
          {status === "connected" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => disconnectMutation.mutate()}
              disabled={disconnectMutation.isPending}
            >
              <PowerOff className="mr-2 h-4 w-4" /> Desconectar
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => connectMutation.mutate()}
              disabled={connectMutation.isPending}
            >
              <Power className="mr-2 h-4 w-4" /> Conectar
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center justify-between rounded-md bg-destructive/10 border border-destructive/20 p-3 mb-4 text-sm text-destructive">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="hover:opacity-70">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <Tabs defaultValue="general" className="space-y-4">
        <TabsList>
          <TabsTrigger value="general"><Info className="mr-2 h-4 w-4" />Geral</TabsTrigger>
          <TabsTrigger value="conversations"><MessageSquare className="mr-2 h-4 w-4" />Conversas</TabsTrigger>
          <TabsTrigger value="costs"><DollarSign className="mr-2 h-4 w-4" />Custos</TabsTrigger>
          <TabsTrigger value="logs"><FileText className="mr-2 h-4 w-4" />Logs</TabsTrigger>
        </TabsList>

        {/* TAB: General */}
        <TabsContent value="general" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Telefone</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold font-mono">{phone ? maskPhone(phone) : "-"}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Mensagens</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{stats?.messages?.toLocaleString() || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Sessoes</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{stats?.sessions || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Custo Total</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">$ {stats?.total_cost?.toFixed(4) || "0.0000"}</p>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Informacoes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">ID</span>
                  <span className="font-mono">{instance.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Gateway ID</span>
                  <span className="font-mono">{instance.gateway_user_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Criado em</span>
                  <span>{new Date(instance.created_at).toLocaleString("pt-BR")}</span>
                </div>
                {instance.connected_at && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Conectado em</span>
                    <span>{new Date(instance.connected_at).toLocaleString("pt-BR")}</span>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Tokens</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Input Tokens</span>
                  <span>{stats?.input_tokens?.toLocaleString() || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Output Tokens</span>
                  <span>{stats?.output_tokens?.toLocaleString() || 0}</span>
                </div>
                <div className="flex justify-between font-medium">
                  <span>Total</span>
                  <span>{((stats?.input_tokens || 0) + (stats?.output_tokens || 0)).toLocaleString()}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* TAB: Conversations */}
        <TabsContent value="conversations">
          <Card>
            <CardHeader>
              <CardTitle>Conversas</CardTitle>
            </CardHeader>
            <CardContent>
              {conversations.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Nenhuma conversa registrada
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left">
                        <th className="pb-2 font-medium">ID</th>
                        <th className="pb-2 font-medium">Telefone</th>
                        <th className="pb-2 font-medium">Mensagens</th>
                        <th className="pb-2 font-medium">Tokens</th>
                        <th className="pb-2 font-medium">Ultima Atividade</th>
                      </tr>
                    </thead>
                    <tbody>
                      {conversations.slice(0, 50).map((conv: any, i: number) => (
                        <tr key={conv.id || i} className="border-b">
                          <td className="py-2 font-mono text-xs">{(conv.id || "").slice(0, 8)}</td>
                          <td className="py-2 font-mono">{maskPhone(conv.participant_phone || conv.phone || "")}</td>
                          <td className="py-2">{conv.message_count || 0}</td>
                          <td className="py-2">{((conv.input_tokens || 0) + (conv.output_tokens || 0)).toLocaleString()}</td>
                          <td className="py-2 text-muted-foreground">
                            {conv.last_activity_at ? new Date(conv.last_activity_at).toLocaleString("pt-BR") : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* TAB: Costs */}
        <TabsContent value="costs" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Custo Total ({costs.days}d)</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">$ {costs.total_cost.toFixed(4)}</p>
              </CardContent>
            </Card>
            {Object.entries(costs.providers || {}).map(([name, data]: [string, any]) => (
              <Card key={name}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium capitalize">{name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Custo</span>
                    <span>$ {data.cost_usd?.toFixed(4) || "0"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Calls</span>
                    <span>{data.calls || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Tokens</span>
                    <span>{((data.input_tokens || 0) + (data.output_tokens || 0)).toLocaleString()}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* TAB: Logs */}
        <TabsContent value="logs">
          <Card>
            <CardHeader>
              <CardTitle>Logs</CardTitle>
            </CardHeader>
            <CardContent>
              {logs.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">
                  Nenhum log registrado
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left">
                        <th className="pb-2 font-medium">Data</th>
                        <th className="pb-2 font-medium">Provider</th>
                        <th className="pb-2 font-medium">Tokens</th>
                        <th className="pb-2 font-medium">Custo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.slice(0, 100).map((log: any, i: number) => (
                        <tr key={i} className="border-b">
                          <td className="py-2 text-muted-foreground">{log.day || log.created_at || "-"}</td>
                          <td className="py-2 capitalize">{log.provider || "-"}</td>
                          <td className="py-2">{((log.input_tokens || 0) + (log.output_tokens || 0)).toLocaleString()}</td>
                          <td className="py-2">$ {(log.cost || 0).toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
