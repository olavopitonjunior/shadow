import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/api/client";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { QRCodeDisplay } from "./QRCodeDisplay";
import { AlertCircle, CheckCircle2, Loader2, Smartphone } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface CreateInstanceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type Step = "name" | "qr" | "connected";

export function CreateInstanceDialog({ open, onOpenChange }: CreateInstanceDialogProps) {
  const [step, setStep] = useState<Step>("name");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [instanceId, setInstanceId] = useState<string | null>(null);
  const [initialQR, setInitialQR] = useState<string | null>(null);
  const [connectedPhone, setConnectedPhone] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const createMutation = useMutation({
    mutationFn: (instanceName: string) => adminApi.createInstance(instanceName),
    onSuccess: (data) => {
      setError(null);
      setInstanceId(data.id);
      setInitialQR(data.qr || null);
      setStep("qr");
      queryClient.invalidateQueries({ queryKey: ["instances"] });
    },
    onError: (err: Error) => {
      setError(
        err.message.includes("fetch")
          ? "Nao foi possivel conectar ao servidor. Verifique se o admin-api esta rodando."
          : `Erro ao criar instancia: ${err.message}`
      );
    },
  });

  const handleCreate = () => {
    if (!name.trim()) return;
    createMutation.mutate(name.trim());
  };

  const handleConnected = (phone: string) => {
    setConnectedPhone(phone);
    setStep("connected");
    queryClient.invalidateQueries({ queryKey: ["instances"] });
  };

  const handleClose = () => {
    setStep("name");
    setName("");
    setError(null);
    setInstanceId(null);
    setInitialQR(null);
    setConnectedPhone(null);
    onOpenChange(false);
  };

  const handleViewInstance = () => {
    handleClose();
    if (instanceId) {
      navigate(`/instances/${instanceId}`);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {step === "name" && "Nova Instancia"}
            {step === "qr" && "Conectar WhatsApp"}
            {step === "connected" && "Conectado!"}
          </DialogTitle>
          <DialogDescription>
            {step === "name" && "Escolha um nome para identificar esta conexao WhatsApp"}
            {step === "qr" && "Escaneie o QR Code com o WhatsApp do seu celular"}
            {step === "connected" && "Seu WhatsApp foi conectado com sucesso"}
          </DialogDescription>
        </DialogHeader>

        {step === "name" && (
          <div className="space-y-4">
            <Input
              placeholder="Ex: Meu WhatsApp, Empresa..."
              value={name}
              onChange={(e) => { setName(e.target.value); setError(null); }}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
            {error && (
              <div className="flex items-start gap-2 rounded-md bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={handleClose}>Cancelar</Button>
              <Button
                onClick={handleCreate}
                disabled={!name.trim() || createMutation.isPending}
              >
                {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Criar
              </Button>
            </div>
          </div>
        )}

        {step === "qr" && instanceId && (
          <QRCodeDisplay
            instanceId={instanceId}
            initialQR={initialQR}
            onConnected={handleConnected}
          />
        )}

        {step === "connected" && (
          <div className="flex flex-col items-center gap-4 py-4">
            <div className="rounded-full bg-green-100 dark:bg-green-900 p-3">
              <CheckCircle2 className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            {connectedPhone && (
              <div className="flex items-center gap-2 text-sm">
                <Smartphone className="h-4 w-4" />
                <span>{connectedPhone}</span>
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleClose}>Fechar</Button>
              <Button onClick={handleViewInstance}>Ver Instancia</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
