import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  status?: "connected" | "disconnected" | "loading";
  className?: string;
}

const statusConfig = {
  connected: {
    variant: "default" as const,
    label: "Conectado",
    className: "bg-green-500 hover:bg-green-600",
  },
  disconnected: {
    variant: "destructive" as const,
    label: "Desconectado",
    className: "",
  },
  loading: {
    variant: "secondary" as const,
    label: "Carregando...",
    className: "bg-yellow-500 hover:bg-yellow-600",
  },
};

function useTheme() {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    return (
      localStorage.getItem("theme") === "dark" ||
      (!localStorage.getItem("theme") &&
        window.matchMedia("(prefers-color-scheme: dark)").matches)
    );
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return { dark, toggle: () => setDark((d) => !d) };
}

export function Header({ title, status, className }: HeaderProps) {
  const { dark, toggle } = useTheme();

  return (
    <header className={cn("bg-background border-b px-6 py-4", className)}>
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-foreground">{title}</h2>
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={toggle} className="h-9 w-9">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          {status && (
            <Badge
              variant={statusConfig[status].variant}
              className={statusConfig[status].className}
            >
              {statusConfig[status].label}
            </Badge>
          )}
        </div>
      </div>
    </header>
  );
}
