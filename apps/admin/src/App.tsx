import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Instances = lazy(() => import("@/pages/Instances"));
const InstanceDetail = lazy(() => import("@/pages/InstanceDetail"));
const Conversations = lazy(() => import("@/pages/Conversations"));
const Costs = lazy(() => import("@/pages/Costs"));
const Observability = lazy(() => import("@/pages/Observability"));
const Logs = lazy(() => import("@/pages/Logs"));
const Settings = lazy(() => import("@/pages/Settings"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 30000,
      staleTime: 10000,
      retry: 1,
    },
  },
});

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-screen bg-background">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-muted-foreground">Carregando...</p>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/instances" element={<Instances />} />
            <Route path="/instances/:id" element={<InstanceDetail />} />
            <Route path="/conversations" element={<Conversations />} />
            <Route path="/costs" element={<Costs />} />
            <Route path="/observability" element={<Observability />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
