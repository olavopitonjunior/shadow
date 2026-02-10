import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Eye, MoreVertical, Power, PowerOff, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface InstanceCardProps {
  instance: {
    id: string;
    name: string;
    phone?: string;
    live_status?: string;
    live_phone?: string;
    status: string;
    created_at: string;
  };
  stats?: {
    messages: number;
    total_cost: number;
  };
  onConnect?: (id: string) => void;
  onDisconnect?: (id: string) => void;
  onDelete?: (id: string) => void;
}

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
  if (clean.length > 4) {
    return "..." + clean.slice(-4);
  }
  return clean;
}

export function InstanceCard({ instance, stats, onConnect, onDisconnect, onDelete }: InstanceCardProps) {
  const navigate = useNavigate();
  const status = instance.live_status || instance.status;
  const phone = instance.live_phone || instance.phone;
  const config = statusConfig[status] || statusConfig.disconnected;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <CardTitle className="text-base">{instance.name}</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={config.variant} className={config.className}>
              {config.label}
            </Badge>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => navigate(`/instances/${instance.id}`)}>
                  <Eye className="mr-2 h-4 w-4" /> Ver detalhes
                </DropdownMenuItem>
                {status !== "connected" && (
                  <DropdownMenuItem onClick={() => onConnect?.(instance.id)}>
                    <Power className="mr-2 h-4 w-4" /> Conectar
                  </DropdownMenuItem>
                )}
                {status === "connected" && (
                  <DropdownMenuItem onClick={() => onDisconnect?.(instance.id)}>
                    <PowerOff className="mr-2 h-4 w-4" /> Desconectar
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem
                  onClick={() => onDelete?.(instance.id)}
                  className="text-destructive"
                >
                  <Trash2 className="mr-2 h-4 w-4" /> Remover
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Telefone</span>
            <span className="font-mono">{phone ? maskPhone(phone) : "-"}</span>
          </div>
          {stats && (
            <>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Mensagens</span>
                <span>{stats.messages.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Custo</span>
                <span>$ {stats.total_cost.toFixed(4)}</span>
              </div>
            </>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          className="w-full mt-3"
          onClick={() => navigate(`/instances/${instance.id}`)}
        >
          Ver detalhes
        </Button>
      </CardContent>
    </Card>
  );
}
