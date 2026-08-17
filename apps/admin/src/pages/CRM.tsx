import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { crmApi } from "@/api/client";
import { Search, User, Clock, Brain, Share2, Upload } from "lucide-react";

export default function CRM() {
  const [search, setSearch] = useState("");
  const [selectedPhone, setSelectedPhone] = useState<string | null>(null);

  const { data: contactsData } = useQuery({
    queryKey: ["crm", "contacts", search],
    queryFn: () => crmApi.getContacts(search || undefined),
    refetchInterval: 30000,
  });

  const { data: contactDetail } = useQuery({
    queryKey: ["crm", "contact", selectedPhone],
    queryFn: () => crmApi.getContact(selectedPhone!),
    enabled: !!selectedPhone,
  });

  const { data: timeline } = useQuery({
    queryKey: ["crm", "timeline", selectedPhone],
    queryFn: () => crmApi.getTimeline(selectedPhone!),
    enabled: !!selectedPhone,
  });

  const { data: memories } = useQuery({
    queryKey: ["crm", "memories", selectedPhone],
    queryFn: () => crmApi.getMemories(selectedPhone!),
    enabled: !!selectedPhone,
  });

  const contacts = contactsData?.contacts || [];

  return (
    <PageLayout title="CRM">
      <div className="flex gap-6 h-[calc(100vh-120px)]">
        {/* Contact List */}
        <div className="w-80 shrink-0 space-y-3">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Buscar contato..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <Button size="icon" variant="outline" title="Importar do WhatsApp">
              <Upload className="w-4 h-4" />
            </Button>
          </div>

          <div className="space-y-1 overflow-y-auto max-h-[calc(100vh-200px)]">
            {contacts.map((c: any) => (
              <button
                key={c.phone}
                onClick={() => setSelectedPhone(c.phone)}
                className={`w-full text-left p-3 rounded-lg transition-colors ${
                  selectedPhone === c.phone
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-muted"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <User className="w-4 h-4 text-primary" />
                  </div>
                  <div className="overflow-hidden">
                    <p className="font-medium text-sm truncate">
                      {c.name || c.phone}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {c.phone}
                    </p>
                  </div>
                  {c.relationship_type && (
                    <Badge variant="outline" className="text-[10px] ml-auto shrink-0">
                      {c.relationship_type}
                    </Badge>
                  )}
                </div>
              </button>
            ))}
            {contacts.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-8">
                Nenhum contato encontrado
              </p>
            )}
          </div>

          <p className="text-xs text-muted-foreground text-center">
            {contactsData?.total || 0} contatos
          </p>
        </div>

        {/* Contact Detail */}
        <div className="flex-1 overflow-y-auto">
          {selectedPhone && contactDetail ? (
            <div className="space-y-4">
              {/* Header */}
              <Card>
                <CardContent className="p-6">
                  <div className="flex items-center gap-4">
                    <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                      <User className="w-8 h-8 text-primary" />
                    </div>
                    <div>
                      <h2 className="text-xl font-bold">
                        {contactDetail.name || contactDetail.phone}
                      </h2>
                      <p className="text-muted-foreground">{contactDetail.phone}</p>
                      {contactDetail.relationship_type && (
                        <Badge className="mt-1">{contactDetail.relationship_type}</Badge>
                      )}
                    </div>
                  </div>
                  {contactDetail.notes && (
                    <p className="mt-4 text-sm text-muted-foreground">{contactDetail.notes}</p>
                  )}
                </CardContent>
              </Card>

              {/* Tabs */}
              <Tabs defaultValue="timeline">
                <TabsList>
                  <TabsTrigger value="timeline" className="gap-1">
                    <Clock className="w-3 h-3" /> Timeline
                  </TabsTrigger>
                  <TabsTrigger value="memories" className="gap-1">
                    <Brain className="w-3 h-3" /> Memorias
                  </TabsTrigger>
                  <TabsTrigger value="graph" className="gap-1">
                    <Share2 className="w-3 h-3" /> Grafo
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="timeline" className="space-y-2 mt-4">
                  {(timeline?.timeline || []).map((item: any, i: number) => (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg border">
                      <Badge variant="outline" className="text-[10px] shrink-0 mt-0.5">
                        {item.type}
                      </Badge>
                      <div>
                        <p className="text-sm font-medium">{item.title}</p>
                        <p className="text-xs text-muted-foreground">{item.date}</p>
                        {item.status && (
                          <Badge variant={item.status === "completed" ? "default" : "secondary"} className="text-[10px] mt-1">
                            {item.status}
                          </Badge>
                        )}
                      </div>
                    </div>
                  ))}
                  {(timeline?.timeline || []).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-8">
                      Nenhuma interacao registrada
                    </p>
                  )}
                </TabsContent>

                <TabsContent value="memories" className="space-y-2 mt-4">
                  {(memories?.memories || []).map((mem: any, i: number) => (
                    <Card key={i}>
                      <CardContent className="p-3">
                        <p className="text-sm">{mem.text || mem.content}</p>
                        <div className="flex gap-2 mt-2">
                          {mem.category && (
                            <Badge variant="outline" className="text-[10px]">{mem.category}</Badge>
                          )}
                          {mem.importance && (
                            <Badge variant="outline" className="text-[10px]">
                              imp: {(mem.importance * 100).toFixed(0)}%
                            </Badge>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                  {(memories?.memories || []).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-8">
                      Nenhuma memoria armazenada
                    </p>
                  )}
                </TabsContent>

                <TabsContent value="graph" className="mt-4">
                  <Card>
                    <CardContent className="p-8 text-center">
                      <Share2 className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                      <p className="text-sm text-muted-foreground">
                        Grafo de relacionamentos sera renderizado com @xyflow/react
                      </p>
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <User className="w-16 h-16 mx-auto text-muted-foreground mb-4" />
                <p className="text-muted-foreground">Selecione um contato para ver detalhes</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
