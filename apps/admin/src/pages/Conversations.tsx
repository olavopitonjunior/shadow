import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { MessageSquare, Activity, TrendingUp } from "lucide-react";

function formatTokens(tokens?: number): string {
  if (!tokens) return "0";
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`;
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
  return String(tokens);
}

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

export default function Conversations() {
  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ["agentSessions"],
    queryFn: api.getSessions,
    refetchInterval: 10000,
  });

  const totalSessions = sessions?.length || 0;
  const activeSessions = sessions?.filter((s: any) => s.is_active)?.length || 0;
  const totalMessages = sessions?.reduce((sum: number, s: any) => sum + (s.message_count || 0), 0) || 0;

  return (
    <PageLayout title="Monitoramento de Conversas">
      <div className="space-y-6">
        <p className="text-muted-foreground">
          Acompanhe em tempo real as conversas processadas pelo Shadow
        </p>

        {/* Summary Stats */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <MessageSquare className="w-4 h-4" />
                Total de Sessoes
              </CardTitle>
            </CardHeader>
            <CardContent>
              {sessionsLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <>
                  <p className="text-2xl font-bold">{totalSessions}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {activeSessions} ativas
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Activity className="w-4 h-4" />
                Mensagens Processadas
              </CardTitle>
            </CardHeader>
            <CardContent>
              {sessionsLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <>
                  <p className="text-2xl font-bold">{totalMessages}</p>
                  <p className="text-xs text-muted-foreground mt-1">Total acumulado</p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <TrendingUp className="w-4 h-4" />
                Sessoes Ativas
              </CardTitle>
            </CardHeader>
            <CardContent>
              {sessionsLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <>
                  <p className="text-2xl font-bold">{activeSessions}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {totalSessions > 0
                      ? `${((activeSessions / totalSessions) * 100).toFixed(0)}%`
                      : "0%"}{" "}
                    do total
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sessions Table */}
        <Card>
          <CardHeader>
            <CardTitle>Sessoes Ativas</CardTitle>
          </CardHeader>
          <CardContent>
            {sessionsLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : sessions && sessions.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-3 px-4 font-medium">Session ID</th>
                      <th className="text-left py-3 px-4 font-medium">Telefone</th>
                      <th className="text-left py-3 px-4 font-medium">Mensagens</th>
                      <th className="text-left py-3 px-4 font-medium">Tokens</th>
                      <th className="text-left py-3 px-4 font-medium">Ultima Atividade</th>
                      <th className="text-left py-3 px-4 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((session: any) => {
                      const totalTokens =
                        (session.total_input_tokens || 0) +
                        (session.total_output_tokens || 0);

                      return (
                        <tr
                          key={session.session_id}
                          className="border-b last:border-0 hover:bg-muted/50"
                        >
                          <td className="py-3 px-4 font-mono text-xs">
                            {session.session_id
                              ? `${session.session_id.slice(0, 8)}...`
                              : "-"}
                          </td>
                          <td className="py-3 px-4 font-mono">
                            {maskPhone(session.phone || session.owner_id)}
                          </td>
                          <td className="py-3 px-4">
                            {session.message_count || 0}
                          </td>
                          <td className="py-3 px-4">
                            <span className="text-xs text-muted-foreground">
                              {formatTokens(totalTokens)}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-xs text-muted-foreground">
                            {formatTime(session.last_activity || session.updated_at)}
                          </td>
                          <td className="py-3 px-4">
                            <Badge
                              variant={session.is_active ? "default" : "secondary"}
                            >
                              {session.is_active ? "Ativa" : "Inativa"}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <MessageSquare className="w-12 h-12 text-muted-foreground mb-4" />
                <p className="text-sm text-muted-foreground">
                  Nenhuma sessao registrada ainda
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
