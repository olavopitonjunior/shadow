import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../../lib/supabase';
import { useAuth } from '../../hooks/useAuth';
import type { ShadowConfig, ShadowMetrics } from '../../types';

export function ShadowAdmin() {
  const navigate = useNavigate();
  const { accessCode } = useAuth();
  const [config, setConfig] = useState<ShadowConfig | null>(null);
  const [metrics, setMetrics] = useState<ShadowMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    if (!accessCode?.code) return;
    setLoading(true);
    setError(null);
    try {
      const { data: configData, error: configError } = await supabase.functions.invoke(
        'shadow-admin',
        { body: { action: 'get_config', access_code: accessCode.code } }
      );
      if (configError) throw configError;
      setConfig(configData.config as ShadowConfig);

      const { data: metricsData, error: metricsError } = await supabase.functions.invoke(
        'shadow-admin',
        { body: { action: 'get_metrics', access_code: accessCode.code } }
      );
      if (metricsError) throw metricsError;
      setMetrics(metricsData.metrics as ShadowMetrics);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [accessCode?.code]);

  const handleSave = async () => {
    if (!accessCode?.code || !config) return;
    setSaving(true);
    setError(null);
    try {
      const { data, error: updateError } = await supabase.functions.invoke(
        'shadow-admin',
        {
          body: {
            action: 'update_config',
            access_code: accessCode.code,
            data: {
              owner_phone: config.owner_phone,
              ignore_groups: config.ignore_groups,
              store_relevant_only: config.store_relevant_only,
              enable_shadow_replies: config.enable_shadow_replies,
              evolution_api_url: config.evolution_api_url,
              evolution_api_key: config.evolution_api_key,
              evolution_instance_id: config.evolution_instance_id,
            },
          },
        }
      );
      if (updateError) throw updateError;
      setConfig(data.config as ShadowConfig);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar configuracao');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 sticky top-0 z-10 bg-white">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <button
              onClick={() => navigate('/home')}
              className="text-sm text-gray-600 hover:text-black"
            >
              ← Voltar
            </button>
            <h1 className="text-xl font-bold text-black mt-2">Shadow Admin</h1>
            <p className="text-sm text-gray-500">
              Configuracao e metricas do modulo Shadow
            </p>
          </div>
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300
                       rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Atualizar
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        <section className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-black mb-4">Configuracao</h2>
          {loading && !config ? (
            <p className="text-sm text-gray-500">Carregando...</p>
          ) : (
            config && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Numero do dono (Shadow responde apenas aqui)
                  </label>
                  <input
                    value={config.owner_phone ?? ''}
                    onChange={(e) =>
                      setConfig({ ...config, owner_phone: e.target.value })
                    }
                    placeholder="Ex: 5511999999999"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Evolution API URL
                    </label>
                    <input
                      value={config.evolution_api_url ?? ''}
                      onChange={(e) =>
                        setConfig({ ...config, evolution_api_url: e.target.value })
                      }
                      placeholder="http://localhost:8080"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Evolution Instance ID
                    </label>
                    <input
                      value={config.evolution_instance_id ?? ''}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          evolution_instance_id: e.target.value,
                        })
                      }
                      placeholder="default"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Evolution API Key
                  </label>
                  <input
                    type="password"
                    value={config.evolution_api_key ?? ''}
                    onChange={(e) =>
                      setConfig({ ...config, evolution_api_key: e.target.value })
                    }
                    placeholder="apikey"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Se vazio, usa a chave configurada nas env vars do Supabase.
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={config.ignore_groups}
                    onChange={(e) =>
                      setConfig({ ...config, ignore_groups: e.target.checked })
                    }
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-700">Ignorar grupos</span>
                </div>

                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={config.store_relevant_only}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        store_relevant_only: e.target.checked,
                      })
                    }
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-700">
                    Salvar apenas mensagens relevantes
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={config.enable_shadow_replies}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        enable_shadow_replies: e.target.checked,
                      })
                    }
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-700">
                    Permitir respostas do Shadow (somente para o dono)
                  </span>
                </div>

                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-white bg-black rounded-lg
                             hover:bg-gray-900 disabled:opacity-50"
                >
                  {saving ? 'Salvando...' : 'Salvar configuracao'}
                </button>
              </div>
            )
          )}
        </section>

        <section className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-black mb-4">Metricas</h2>
          {!metrics ? (
            <p className="text-sm text-gray-500">Nenhuma metrica encontrada.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MetricCard label="Contatos" value={metrics.contacts} />
              <MetricCard label="Conversas" value={metrics.conversations} />
              <MetricCard label="Mensagens" value={metrics.messages} />
              <MetricCard label="Tarefas pendentes" value={metrics.tasks_pending} />
              <MetricCard label="Tarefas concluidas" value={metrics.tasks_done} />
              <MetricCard label="Compromissos" value={metrics.appointments} />
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-2xl font-bold text-black mt-2">{value}</p>
    </div>
  );
}
