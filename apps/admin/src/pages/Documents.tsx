import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageLayout } from "@/components/layout/PageLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { documentsApi } from "@/api/client";
import { FileText, Download, Eye, Code } from "lucide-react";

export default function Documents() {
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);

  const { data: docsData } = useQuery({
    queryKey: ["documents", "list"],
    queryFn: () => documentsApi.list(),
    refetchInterval: 30000,
  });

  const { data: docDetail } = useQuery({
    queryKey: ["documents", "detail", selectedDoc],
    queryFn: () => documentsApi.get(selectedDoc!),
    enabled: !!selectedDoc,
  });

  const { data: templatesData } = useQuery({
    queryKey: ["documents", "templates"],
    queryFn: documentsApi.listTemplates,
    refetchInterval: 60000,
  });

  const documents = docsData?.documents || [];
  const templates = templatesData?.templates || [];

  return (
    <PageLayout title="Documentos">
      <Tabs defaultValue="generated">
        <TabsList>
          <TabsTrigger value="generated">Gerados ({documents.length})</TabsTrigger>
          <TabsTrigger value="templates">Templates ({templates.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="generated" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Document List */}
            <div className="space-y-2">
              {documents.map((doc: any) => (
                <button
                  key={doc.id}
                  onClick={() => setSelectedDoc(doc.id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedDoc === doc.id ? "bg-accent" : "hover:bg-muted"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <FileText className="w-8 h-8 text-muted-foreground shrink-0" />
                    <div className="overflow-hidden">
                      <p className="text-sm font-medium truncate">{doc.filename}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-[10px]">{doc.type}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {doc.size_bytes ? `${(doc.size_bytes / 1024).toFixed(1)} KB` : ""}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              ))}
              {documents.length === 0 && (
                <Card>
                  <CardContent className="p-8 text-center">
                    <FileText className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-sm text-muted-foreground">
                      Nenhum documento gerado ainda.
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Peca ao Shadow para "gerar uma proposta" via WhatsApp.
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Document Preview */}
            <div className="lg:col-span-2">
              {selectedDoc && docDetail ? (
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between">
                    <CardTitle className="text-base">{docDetail.filename || docDetail.id}</CardTitle>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => window.open(documentsApi.getDownloadUrl(selectedDoc), "_blank")}
                      >
                        <Download className="w-4 h-4 mr-1" /> Download
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {docDetail.content ? (
                      <div
                        className="prose prose-sm max-w-none border rounded-lg p-4 bg-white"
                        dangerouslySetInnerHTML={{ __html: docDetail.content }}
                      />
                    ) : (
                      <div className="text-center py-8">
                        <Eye className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                        <p className="text-sm text-muted-foreground">
                          Preview nao disponivel para arquivos PDF.
                        </p>
                        <Button
                          className="mt-4"
                          onClick={() => window.open(documentsApi.getDownloadUrl(selectedDoc), "_blank")}
                        >
                          <Download className="w-4 h-4 mr-2" /> Baixar PDF
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="p-12 text-center">
                    <FileText className="w-16 h-16 mx-auto text-muted-foreground mb-4" />
                    <p className="text-muted-foreground">Selecione um documento para visualizar</p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="templates" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((t: any) => (
              <Card key={t.path}>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Code className="w-4 h-4" />
                    {t.name}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <Badge>{t.category}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {(t.size_bytes / 1024).toFixed(1)} KB
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2 font-mono">{t.path}</p>
                </CardContent>
              </Card>
            ))}
            {templates.length === 0 && (
              <Card className="col-span-full">
                <CardContent className="p-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    Templates Jinja2 serao carregados de shadow/agent/templates/
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
