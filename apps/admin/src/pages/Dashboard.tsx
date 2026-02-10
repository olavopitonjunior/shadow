import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { adminApi } from "@/api/client";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, Calendar, CheckCircle2, MessageSquare, Server } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Dashboard() {
  // Poll every 30 seconds
  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["stats", "overview"],
    queryFn: () => adminApi.getStatsOverview(),
    refetchInterval: 30000,
  });

  const { data: agentStatus, isLoading: agentLoading } = useQuery({
    queryKey: ["proxy", "agent", "status"],
    queryFn: () => adminApi.getProxyAgentStatus(),
    refetchInterval: 30000,
  });

  const { data: whatsappStats } = useQuery({
    queryKey: ["stats", "whatsapp"],
    queryFn: () => adminApi.getStatsWhatsApp(),
    refetchInterval: 30000,
  });

  const { data: usageHistory } = useQuery({
    queryKey: ["stats", "usage", "history"],
    queryFn: () => adminApi.getStatsUsageHistory(),
    refetchInterval: 30000,
  });

  const { data: logs } = useQuery({
    queryKey: ["logs", "recent"],
    queryFn: () => adminApi.getLogs({ limit: 10 }),
    refetchInterval: 30000,
  });

  // Prepare chart data - aggregate by day
  const chartData = usageHistory?.history
    ? Object.values(
        usageHistory.history.reduce((acc, item) => {
          if (!acc[item.day]) {
            acc[item.day] = { day: item.day, input: 0, output: 0 };
          }
          acc[item.day].input += item.input_tokens;
          acc[item.day].output += item.output_tokens;
          return acc;
        }, {} as Record<string, { day: string; input: number; output: number }>)
      ).slice(-7)
    : [];

  // Format day for display
  const formatDay = (day: string) => {
    const date = new Date(day);
    return date.toLocaleDateString("pt-BR", { month: "short", day: "numeric" });
  };

  // Health status components
  const healthStatuses = [
    { name: "Agent", status: agentStatus?.status || "unknown" },
    { name: "Gateway", status: whatsappStats?.connections?.[0]?.status || "unknown" },
    { name: "Storage", status: agentStatus?.components?.storage || "unknown" },
    { name: "Scheduler", status: agentStatus?.components?.scheduler || "unknown" },
  ];

  return (
    <PageLayout title="Dashboard">
      <div className="space-y-6">
        {/* Health Status Row */}
        <div className="flex gap-3 flex-wrap">
          {healthStatuses.map((item) => (
            <Badge
              key={item.name}
              variant={item.status === "healthy" || item.status === "connected" ? "default" : "destructive"}
              className={cn(
                "px-3 py-1",
                item.status === "healthy" || item.status === "connected"
                  ? "bg-green-500 hover:bg-green-600"
                  : "bg-red-500 hover:bg-red-600"
              )}
            >
              {item.name}: {item.status}
            </Badge>
          ))}
        </div>

        {/* Stats Cards Row */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {overviewLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">
                    {overview?.messages_total?.toLocaleString() || "0"}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {overview?.messages_24h || 0} nas ultimas 24h
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active Sessions</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {agentLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">
                    {agentStatus?.sessions?.active_sessions || 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {agentStatus?.sessions?.total_sessions || 0} total
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Pending Tasks</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {overviewLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">{overview?.tasks_pending || 0}</div>
                  <p className="text-xs text-muted-foreground mt-1">Aguardando conclusao</p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Upcoming Appointments</CardTitle>
              <Calendar className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {overviewLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">{overview?.appointments_upcoming || 0}</div>
                  <p className="text-xs text-muted-foreground mt-1">Proximos 7 dias</p>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Token Usage Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Token Usage (Last 7 Days)</CardTitle>
          </CardHeader>
          <CardContent>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorInput" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorOutput" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#a855f7" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="day"
                    tickFormatter={formatDay}
                    stroke="#888888"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    stroke="#888888"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="rounded-lg border bg-background p-2 shadow-sm">
                            <div className="grid grid-cols-2 gap-2">
                              <div className="flex flex-col">
                                <span className="text-[0.70rem] uppercase text-muted-foreground">
                                  Input
                                </span>
                                <span className="font-bold text-blue-500">
                                  {payload[0].value?.toLocaleString()}
                                </span>
                              </div>
                              <div className="flex flex-col">
                                <span className="text-[0.70rem] uppercase text-muted-foreground">
                                  Output
                                </span>
                                <span className="font-bold text-purple-500">
                                  {payload[1].value?.toLocaleString()}
                                </span>
                              </div>
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="input"
                    stroke="#3b82f6"
                    fillOpacity={1}
                    fill="url(#colorInput)"
                  />
                  <Area
                    type="monotone"
                    dataKey="output"
                    stroke="#a855f7"
                    fillOpacity={1}
                    fill="url(#colorOutput)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                No usage data available
              </div>
            )}
          </CardContent>
        </Card>

        {/* WhatsApp Connections & Recent Activity */}
        <div className="grid gap-4 md:grid-cols-2">
          {/* WhatsApp Connections */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                WhatsApp Connections
              </CardTitle>
            </CardHeader>
            <CardContent>
              {whatsappStats?.connections && whatsappStats.connections.length > 0 ? (
                <div className="space-y-3">
                  {whatsappStats.connections.map((conn, idx) => (
                    <div key={idx} className="flex items-center justify-between p-3 border rounded-lg">
                      <div>
                        <p className="font-medium">{conn.provider}</p>
                        <p className="text-sm text-muted-foreground">{conn.instance_id}</p>
                      </div>
                      <Badge
                        variant={conn.status === "connected" ? "default" : "destructive"}
                        className={cn(
                          conn.status === "connected"
                            ? "bg-green-500 hover:bg-green-600"
                            : "bg-red-500 hover:bg-red-600"
                        )}
                      >
                        {conn.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No connections available</p>
              )}
            </CardContent>
          </Card>

          {/* Recent Activity */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
            </CardHeader>
            <CardContent>
              {logs && logs.length > 0 ? (
                <div className="space-y-2 max-h-[280px] overflow-y-auto">
                  {logs.map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-sm border-b pb-2 last:border-0">
                      <Badge
                        variant={log.level === "ERROR" ? "destructive" : "secondary"}
                        className="text-xs"
                      >
                        {log.level || "INFO"}
                      </Badge>
                      <div className="flex-1 min-w-0">
                        <p className="truncate">{log.message || log.msg || "No message"}</p>
                        {log.timestamp && (
                          <p className="text-xs text-muted-foreground">
                            {new Date(log.timestamp).toLocaleString("pt-BR")}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No recent activity</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageLayout>
  );
}
