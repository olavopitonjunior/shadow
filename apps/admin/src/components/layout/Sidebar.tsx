import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Server,
  MessageSquare,
  DollarSign,
  Activity,
  FileText,
  Settings
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  icon: React.ElementType;
  label: string;
}

const navItems: NavItem[] = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/instances", icon: Server, label: "Instancias" },
  { to: "/conversations", icon: MessageSquare, label: "Conversas" },
  { to: "/costs", icon: DollarSign, label: "Custos API" },
  { to: "/observability", icon: Activity, label: "Observabilidade" },
  { to: "/logs", icon: FileText, label: "Logs" },
  { to: "/settings", icon: Settings, label: "Configuracoes" },
];

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  return (
    <aside className={cn("w-64 h-screen bg-sidebar border-r fixed left-0 top-0", className)}>
      <div className="flex flex-col h-full">
        {/* Brand */}
        <div className="p-6 border-b">
          <h1 className="text-xl font-bold text-foreground">Shadow Admin</h1>
          <p className="text-sm text-muted-foreground">Dashboard de Controle</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors",
                  "hover:bg-accent hover:text-accent-foreground",
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground"
                )
              }
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t text-xs text-muted-foreground">
          Shadow MVP v0.1
        </div>
      </div>
    </aside>
  );
}
