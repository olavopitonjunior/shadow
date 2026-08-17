import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { agentsApi } from "@/api/client";

interface AgentEvent {
  event_id: string;
  event_type: string;
  node_name: string;
  thread_id: string;
  timestamp: string;
  data?: Record<string, any>;
}

function useAgentStream() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const url = agentsApi.getStreamUrl();
    const source = new EventSource(url);

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        if (event.event_type === "heartbeat") return;
        setEvents((prev) => [...prev.slice(-200), event]);
      } catch {}
    };

    return () => source.close();
  }, []);

  return { events, connected };
}

const NODE_COLORS: Record<string, string> = {
  intake: "bg-blue-500",
  rag_retrieve: "bg-purple-500",
  supervisor_think: "bg-yellow-500",
  fast_path: "bg-green-500",
  crm: "bg-cyan-500",
  planner: "bg-orange-500",
  analytics: "bg-pink-500",
  docgen: "bg-indigo-500",
  collector: "bg-teal-500",
  synthesize: "bg-gray-500",
  respond: "bg-emerald-500",
};

export default function AgentMonitor() {
  const { events, connected } = useAgentStream();
  const { data: status } = useQuery({
    queryKey: ["agents", "status"],
    queryFn: agentsApi.getStatus,
    refetchInterval: 10000,
  });
  const { data: history } = useQuery({
    queryKey: ["agents", "history"],
    queryFn: () => agentsApi.getHistory(100),
    refetchInterval: 5000,
  });

  const agents = status?.agents || [];
  const recentEvents = events.length > 0 ? events : (history?.events || []);

  // Group events by thread
  const activeThreads = new Map<string, AgentEvent[]>();
  for (const e of recentEvents.slice(-50)) {
    const tid = e.thread_id || "unknown";
    if (!activeThreads.has(tid)) activeThreads.set(tid, []);
    activeThreads.get(tid)!.push(e);
  }

  return (
    <PageLayout title="Agent Monitor">
      <div className="space-y-6">
        {/* Connection Status */}
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
          <span className="text-sm text-muted-foreground">
            {connected ? "SSE Conectado - Monitoramento ao vivo" : "SSE Desconectado"}
          </span>
          <Badge variant={connected ? "default" : "destructive"}>
            {connected ? "Live" : "Offline"}
          </Badge>
        </div>

        {/* Agent Status Cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {agents.map((agent: any) => (
            <Card key={agent.name}>
              <CardContent className="p-4 text-center">
                <div className={`w-3 h-3 rounded-full mx-auto mb-2 ${agent.status === "active" || agent.status === "ready" ? "bg-green-500" : "bg-gray-400"}`} />
                <p className="font-medium text-sm capitalize">{agent.name}</p>
                <p className="text-xs text-muted-foreground">{agent.type}</p>
                {agent.tools && (
                  <p className="text-xs text-muted-foreground">{agent.tools} tools</p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Graph Visualization Placeholder */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Fluxo do Grafo</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {/* Simplified graph flow */}
                <div className="flex items-center gap-2 flex-wrap">
                  {["intake", "router", "rag_retrieve", "supervisor_think"].map((node) => (
                    <div key={node} className="flex items-center gap-1">
                      <div className={`w-2 h-2 rounded-full ${NODE_COLORS[node] || "bg-gray-400"}`} />
                      <span className="text-xs">{node}</span>
                      <span className="text-muted-foreground text-xs">{">"}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-4 flex-wrap mt-2">
                  {["crm", "planner", "analytics", "docgen", "collector"].map((w) => (
                    <Badge key={w} variant="outline" className="text-xs">
                      <div className={`w-2 h-2 rounded-full mr-1 ${NODE_COLORS[w]}`} />
                      {w}
                    </Badge>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-4">
                  React Flow visualization sera adicionado com @xyflow/react
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Active Sessions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sessoes Ativas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[300px] overflow-y-auto">
              {activeThreads.size === 0 && (
                <p className="text-sm text-muted-foreground">Nenhuma sessao ativa</p>
              )}
              {Array.from(activeThreads.entries()).map(([threadId, threadEvents]) => {
                const lastEvent = threadEvents[threadEvents.length - 1];
                return (
                  <div key={threadId} className="p-2 rounded-md border text-xs">
                    <p className="font-mono truncate">{threadId}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <div className={`w-2 h-2 rounded-full ${NODE_COLORS[lastEvent.node_name] || "bg-gray-400"}`} />
                      <span>{lastEvent.node_name}</span>
                      <Badge variant="outline" className="text-[10px]">
                        {lastEvent.event_type}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>

        {/* Execution Timeline */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Timeline de Execucao</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 max-h-[400px] overflow-y-auto">
              {recentEvents.slice(-30).reverse().map((event: AgentEvent, i: number) => (
                <div key={event.event_id || i} className="flex items-center gap-3 py-1 text-xs border-b last:border-0">
                  <span className="text-muted-foreground w-20 shrink-0">
                    {new Date(event.timestamp).toLocaleTimeString("pt-BR")}
                  </span>
                  <div className={`w-2 h-2 rounded-full shrink-0 ${NODE_COLORS[event.node_name] || "bg-gray-400"}`} />
                  <span className="font-medium w-32 shrink-0">{event.node_name}</span>
                  <Badge
                    variant={event.event_type === "error" ? "destructive" : "outline"}
                    className="text-[10px]"
                  >
                    {event.event_type}
                  </Badge>
                  <span className="text-muted-foreground truncate">
                    {event.thread_id}
                  </span>
                </div>
              ))}
              {recentEvents.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Aguardando eventos... Envie uma mensagem via WhatsApp.
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
