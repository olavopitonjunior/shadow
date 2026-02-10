import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

interface PageLayoutProps {
  title: string;
  status?: "connected" | "disconnected" | "loading";
  children: React.ReactNode;
}

export function PageLayout({ title, status, children }: PageLayoutProps) {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <div className="flex-1 ml-64 flex flex-col">
        <Header title={title} status={status} />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
