import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { adminApi } from "@/api/client";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DollarSign, TrendingUp, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Costs() {
  // Poll every 30 seconds
  const { data: breakdown, isLoading: breakdownLoading } = useQuery({
    queryKey: ["stats", "costs", "breakdown"],
    queryFn: () => adminApi.getStatsCostsBreakdown(),
    refetchInterval: 30000,
  });

  const { data: usageHistory } = useQuery({
    queryKey: ["stats", "usage", "history"],
    queryFn: () => adminApi.getStatsUsageHistory(),
    refetchInterval: 30000,
  });

  const { data: pricing } = useQuery({
    queryKey: ["config", "pricing"],
    queryFn: () => adminApi.getConfigPricing(),
  });

  // Calculate monthly projection
  const daysInMonth = 30;
  const currentDays = breakdown?.days || 1;
  const dailyAverage = breakdown?.total_cost ? breakdown.total_cost / currentDays : 0;
  const monthlyProjection = dailyAverage * daysInMonth;

  // Prepare chart data - aggregate by day and provider
  const chartData = usageHistory?.history
    ? Object.values(
        usageHistory.history.reduce((acc, item) => {
          if (!acc[item.day]) {
            acc[item.day] = { day: item.day, anthropic: 0, google: 0, openai: 0 };
          }
          const provider = item.provider.toLowerCase();
          if (provider in acc[item.day]) {
            acc[item.day][provider as "anthropic" | "google" | "openai"] += item.cost;
          }
          return acc;
        }, {} as Record<string, { day: string; anthropic: number; google: number; openai: number }>)
      ).slice(-30)
    : [];

  // Format day for display
  const formatDay = (day: string) => {
    const date = new Date(day);
    return date.toLocaleDateString("pt-BR", { month: "short", day: "numeric" });
  };

  // Format currency
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }).format(value);
  };

  // Provider colors
  const providerColors: Record<string, { color: string; bgClass: string }> = {
    anthropic: { color: "#3b82f6", bgClass: "bg-blue-500 hover:bg-blue-600" },
    google: { color: "#10b981", bgClass: "bg-green-500 hover:bg-green-600" },
    openai: { color: "#f97316", bgClass: "bg-orange-500 hover:bg-orange-600" },
  };

  // Provider display info
  const providerInfo: Record<string, { name: string; icon: string }> = {
    anthropic: { name: "Anthropic (Claude)", icon: "🤖" },
    google: { name: "Google (Gemini)", icon: "✨" },
    openai: { name: "OpenAI", icon: "🧠" },
  };

  return (
    <PageLayout title="Uso de API & Custos">
      <div className="space-y-6">
        <p className="text-muted-foreground">
          Monitore o consumo de tokens e custos de APIs de LLM
        </p>

        {/* Summary Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Cost (Last {breakdown?.days || 0} days)</CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {breakdownLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">
                    {formatCurrency(breakdown?.total_cost || 0)}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Projection: {formatCurrency(monthlyProjection)}/month
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Input Tokens</CardTitle>
              <Zap className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {breakdownLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">
                    {Object.values(breakdown?.providers || {})
                      .reduce((sum, p) => sum + p.input_tokens, 0)
                      .toLocaleString()}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Last {breakdown?.days || 0} days
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Output Tokens</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {breakdownLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">
                    {Object.values(breakdown?.providers || {})
                      .reduce((sum, p) => sum + p.output_tokens, 0)
                      .toLocaleString()}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Last {breakdown?.days || 0} days
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Cost Over Time Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Cost Over Time (Last 30 Days)</CardTitle>
            <CardDescription>Stacked daily cost by provider</CardDescription>
          </CardHeader>
          <CardContent>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={350}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorAnthropic" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={providerColors.anthropic.color} stopOpacity={0.8} />
                      <stop offset="95%" stopColor={providerColors.anthropic.color} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorGoogle" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={providerColors.google.color} stopOpacity={0.8} />
                      <stop offset="95%" stopColor={providerColors.google.color} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorOpenai" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={providerColors.openai.color} stopOpacity={0.8} />
                      <stop offset="95%" stopColor={providerColors.openai.color} stopOpacity={0} />
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
                    tickFormatter={(value) => `$${value.toFixed(2)}`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const total = payload.reduce((sum, p) => sum + (Number(p.value) || 0), 0);
                        return (
                          <div className="rounded-lg border bg-background p-3 shadow-sm">
                            <div className="mb-2 font-semibold">Total: {formatCurrency(total)}</div>
                            <div className="grid gap-1">
                              {payload.map((p, idx) => (
                                <div key={idx} className="flex items-center gap-2 text-sm">
                                  <div
                                    className="w-3 h-3 rounded-full"
                                    style={{ backgroundColor: p.color }}
                                  />
                                  <span className="capitalize">{p.dataKey}:</span>
                                  <span className="font-medium">{formatCurrency(Number(p.value) || 0)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="anthropic"
                    stackId="1"
                    stroke={providerColors.anthropic.color}
                    fillOpacity={1}
                    fill="url(#colorAnthropic)"
                  />
                  <Area
                    type="monotone"
                    dataKey="google"
                    stackId="1"
                    stroke={providerColors.google.color}
                    fillOpacity={1}
                    fill="url(#colorGoogle)"
                  />
                  <Area
                    type="monotone"
                    dataKey="openai"
                    stackId="1"
                    stroke={providerColors.openai.color}
                    fillOpacity={1}
                    fill="url(#colorOpenai)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[350px] flex items-center justify-center text-muted-foreground">
                No cost data available
              </div>
            )}
          </CardContent>
        </Card>

        {/* Provider Cards */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Provider Breakdown</h3>
          {breakdownLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : breakdown?.providers ? (
            <div className="grid gap-4 md:grid-cols-3">
              {Object.entries(breakdown.providers).map(([provider, data]) => {
                const info = providerInfo[provider.toLowerCase()] || {
                  name: provider,
                  icon: "📊",
                };
                const colors = providerColors[provider.toLowerCase()] || {
                  color: "#6b7280",
                  bgClass: "bg-gray-500 hover:bg-gray-600",
                };

                return (
                  <Card key={provider}>
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="flex items-center gap-2">
                            <span>{info.icon}</span>
                            <span>{info.name}</span>
                          </CardTitle>
                        </div>
                        <Badge className={cn(colors.bgClass)}>Active</Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div>
                          <p className="text-sm font-medium text-muted-foreground">Total Cost</p>
                          <p className="text-2xl font-bold">{formatCurrency(data.cost_usd)}</p>
                        </div>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div>
                            <p className="font-medium text-muted-foreground">Input Tokens</p>
                            <p className="font-semibold">{data.input_tokens.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="font-medium text-muted-foreground">Output Tokens</p>
                            <p className="font-semibold">{data.output_tokens.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="font-medium text-muted-foreground">API Calls</p>
                            <p className="font-semibold">{data.calls.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="font-medium text-muted-foreground">Avg Latency</p>
                            <p className="font-semibold">{data.avg_latency_ms.toFixed(0)}ms</p>
                          </div>
                        </div>
                        {data.models && Object.keys(data.models).length > 0 && (
                          <div className="pt-2 border-t">
                            <p className="text-xs font-medium text-muted-foreground mb-1">Models:</p>
                            <div className="flex flex-wrap gap-1">
                              {Object.keys(data.models).map((model) => (
                                <Badge key={model} variant="outline" className="text-xs">
                                  {model}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No provider data available</p>
          )}
        </div>

        {/* Pricing Configuration */}
        <Card>
          <CardHeader>
            <CardTitle>Pricing Configuration</CardTitle>
            <CardDescription>Current pricing per model (per 1M tokens)</CardDescription>
          </CardHeader>
          <CardContent>
            {pricing?.pricing && pricing.pricing.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-4 font-medium">Provider</th>
                      <th className="text-left py-2 px-4 font-medium">Model</th>
                      <th className="text-right py-2 px-4 font-medium">Input Price</th>
                      <th className="text-right py-2 px-4 font-medium">Output Price</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pricing.pricing.map((item, idx) => (
                      <tr key={idx} className="border-b last:border-0">
                        <td className="py-2 px-4 capitalize">{item.provider}</td>
                        <td className="py-2 px-4 font-mono text-xs">{item.model}</td>
                        <td className="py-2 px-4 text-right">
                          {formatCurrency(item.input_price_per_mtok)}
                        </td>
                        <td className="py-2 px-4 text-right">
                          {formatCurrency(item.output_price_per_mtok)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No pricing data available</p>
            )}
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
