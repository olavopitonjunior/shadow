import { useCallback, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/api/client";
import { PageLayout } from "@/components/layout/PageLayout";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Plus, Server, X } from "lucide-react";
import { InstanceCard } from "@/components/instances/InstanceCard";
import { CreateInstanceDialog } from "@/components/instances/CreateInstanceDialog";

export default function Instances() {
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Auto-dismiss error after 5s
  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 5000);
    return () => clearTimeout(t);
  }, [error]);

  const onMutationError = useCallback((err: Error) => {
    setError(err.message.includes("fetch")
      ? "Nao foi possivel conectar ao servidor."
      : err.message);
  }, []);

  const { data, isLoading } = useQuery({
    queryKey: ["instances"],
    queryFn: () => adminApi.getInstances(),
  });

  const connectMutation = useMutation({
    mutationFn: (id: string) => adminApi.connectInstance(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["instances"] }),
    onError: onMutationError,
  });

  const disconnectMutation = useMutation({
    mutationFn: (id: string) => adminApi.disconnectInstance(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["instances"] }),
    onError: onMutationError,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminApi.deleteInstance(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["instances"] }),
    onError: onMutationError,
  });

  const instances = data?.instances || [];

  return (
    <PageLayout title="Instancias">
      <div className="space-y-4">
        {error && (
          <div className="flex items-center justify-between rounded-md bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)} className="hover:opacity-70">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground">
            Gerencie suas conexoes WhatsApp
          </p>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" /> Nova Instancia
          </Button>
        </div>

        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-48" />
            ))}
          </div>
        ) : instances.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Server className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">Nenhuma instancia</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Crie sua primeira instancia para conectar um WhatsApp
            </p>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" /> Nova Instancia
            </Button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {instances.map((instance) => (
              <InstanceCard
                key={instance.id}
                instance={instance}
                onConnect={(id) => connectMutation.mutate(id)}
                onDisconnect={(id) => disconnectMutation.mutate(id)}
                onDelete={(id) => deleteMutation.mutate(id)}
              />
            ))}
          </div>
        )}
      </div>

      <CreateInstanceDialog open={createOpen} onOpenChange={setCreateOpen} />
    </PageLayout>
  );
}
