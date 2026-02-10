import { QRCodeSVG } from "qrcode.react";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/api/client";
import { Button } from "@/components/ui/button";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";

interface QRCodeDisplayProps {
  instanceId: string;
  initialQR?: string | null;
  onConnected?: (phone: string) => void;
}

export function QRCodeDisplay({ instanceId, initialQR, onConnected }: QRCodeDisplayProps) {
  // Poll status every 3 seconds
  const { data: statusData, isError: statusError, failureCount, refetch: refetchStatus } = useQuery({
    queryKey: ["instance-status", instanceId],
    queryFn: () => adminApi.getInstanceStatus(instanceId),
    refetchInterval: 3000,
    retry: 2,
  });

  // Poll QR if no QR yet
  const { data: qrData } = useQuery({
    queryKey: ["instance-qr", instanceId],
    queryFn: () => adminApi.getInstanceQR(instanceId),
    refetchInterval: statusData?.status === "qr_pending" ? 5000 : false,
    enabled: !initialQR && statusData?.status === "qr_pending",
    retry: 2,
  });

  const currentQR = statusData?.qr || qrData?.qr || initialQR;
  const status = statusData?.status || "connecting";

  // Notify when connected
  if (status === "connected" && statusData?.phone && onConnected) {
    onConnected(statusData.phone);
  }

  if (status === "connected") {
    return null; // Parent handles connected state
  }

  // Error state - API unreachable after retries
  if (statusError && failureCount > 2) {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <div className="rounded-full bg-destructive/10 p-3">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <p className="text-sm text-center text-muted-foreground">
          Nao foi possivel conectar ao gateway.
          <br />
          Verifique se o admin-api e o gateway estao rodando.
        </p>
        <Button variant="outline" size="sm" onClick={() => refetchStatus()}>
          <RefreshCw className="mr-2 h-4 w-4" /> Tentar Novamente
        </Button>
      </div>
    );
  }

  if (!currentQR && status !== "qr_pending") {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Conectando ao WhatsApp...</p>
      </div>
    );
  }

  if (!currentQR && status === "qr_pending") {
    return (
      <div className="flex flex-col items-center gap-4 py-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Gerando QR Code...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="rounded-lg border bg-white p-4">
        <QRCodeSVG value={currentQR!} size={256} level="M" />
      </div>
      <p className="text-sm text-muted-foreground">
        Abra o WhatsApp no seu celular e escaneie o QR Code
      </p>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Aguardando conexao...
      </div>
    </div>
  );
}
