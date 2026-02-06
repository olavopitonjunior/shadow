"""
CronService - Serviço de agendamento robusto para Shadow MVP.

Baseado nos padrões do Moltbot, suporta:
- Agendamento único (at): executa em timestamp específico
- Intervalo fixo (every): executa a cada N milissegundos
- Expressão cron (cron): executa conforme expressão cron com timezone
"""

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Literal

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore


class ScheduleKind(str, Enum):
    AT = "at"
    EVERY = "every"
    CRON = "cron"


@dataclass
class CronSchedule:
    """Define quando um job deve executar."""
    kind: Literal["at", "every", "cron"]
    at_ms: int | None = None          # Timestamp Unix em ms (para kind="at")
    every_ms: int | None = None       # Intervalo em ms (para kind="every")
    anchor_ms: int | None = None      # Âncora para intervalo (para kind="every")
    expr: str | None = None           # Expressão cron (para kind="cron")
    tz: str = "America/Sao_Paulo"     # Timezone para expressão cron

    def next_run_ms(self, now_ms: int | None = None) -> int | None:
        """Calcula próximo horário de execução em ms."""
        if now_ms is None:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        if self.kind == "at":
            if self.at_ms and self.at_ms > now_ms:
                return self.at_ms
            return None

        elif self.kind == "every":
            if not self.every_ms:
                return None
            anchor = self.anchor_ms or now_ms
            elapsed = now_ms - anchor
            intervals = (elapsed // self.every_ms) + 1
            return anchor + (intervals * self.every_ms)

        elif self.kind == "cron":
            if not HAS_CRONITER or not self.expr:
                return None
            try:
                tz = ZoneInfo(self.tz)
                now_dt = datetime.fromtimestamp(now_ms / 1000, tz=tz)
                cron = croniter(self.expr, now_dt)
                next_dt = cron.get_next(datetime)
                return int(next_dt.timestamp() * 1000)
            except Exception:
                return None

        return None


@dataclass
class CronJobState:
    """Estado de execução de um job."""
    next_run_at_ms: int | None = None
    running_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None


@dataclass
class CronJob:
    """Representa um job agendado."""
    id: str
    name: str
    schedule: CronSchedule
    action: str  # "send_reminder", "daily_summary", "custom"
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    delete_after_run: bool = False
    created_at_ms: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    state: CronJobState = field(default_factory=CronJobState)

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário (para serialização)."""
        return {
            "id": self.id,
            "name": self.name,
            "schedule": {
                "kind": self.schedule.kind,
                "at_ms": self.schedule.at_ms,
                "every_ms": self.schedule.every_ms,
                "anchor_ms": self.schedule.anchor_ms,
                "expr": self.schedule.expr,
                "tz": self.schedule.tz,
            },
            "action": self.action,
            "params": self.params,
            "enabled": self.enabled,
            "delete_after_run": self.delete_after_run,
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "state": {
                "next_run_at_ms": self.state.next_run_at_ms,
                "running_at_ms": self.state.running_at_ms,
                "last_run_at_ms": self.state.last_run_at_ms,
                "last_status": self.state.last_status,
                "last_error": self.state.last_error,
                "last_duration_ms": self.state.last_duration_ms,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CronJob":
        """Cria job a partir de dicionário."""
        schedule_data = data.get("schedule", {})
        state_data = data.get("state", {})

        schedule = CronSchedule(
            kind=schedule_data.get("kind", "at"),
            at_ms=schedule_data.get("at_ms"),
            every_ms=schedule_data.get("every_ms"),
            anchor_ms=schedule_data.get("anchor_ms"),
            expr=schedule_data.get("expr"),
            tz=schedule_data.get("tz", "America/Sao_Paulo"),
        )

        state = CronJobState(
            next_run_at_ms=state_data.get("next_run_at_ms"),
            running_at_ms=state_data.get("running_at_ms"),
            last_run_at_ms=state_data.get("last_run_at_ms"),
            last_status=state_data.get("last_status"),
            last_error=state_data.get("last_error"),
            last_duration_ms=state_data.get("last_duration_ms"),
        )

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "Unnamed Job"),
            schedule=schedule,
            action=data.get("action", "custom"),
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
            delete_after_run=data.get("delete_after_run", False),
            created_at_ms=data.get("created_at_ms", int(datetime.now(timezone.utc).timestamp() * 1000)),
            updated_at_ms=data.get("updated_at_ms", int(datetime.now(timezone.utc).timestamp() * 1000)),
            state=state,
        )


@dataclass
class CronJobCreate:
    """Dados para criar um novo job."""
    name: str
    schedule: CronSchedule
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    delete_after_run: bool = False


@dataclass
class CronEvent:
    """Evento emitido pelo CronService."""
    job_id: str
    action: Literal["added", "updated", "removed", "started", "finished"]
    run_at_ms: int | None = None
    duration_ms: int | None = None
    status: Literal["ok", "error", "skipped"] | None = None
    error: str | None = None
    next_run_at_ms: int | None = None


# Tipo para handlers de ação
ActionHandler = Callable[[CronJob], Coroutine[Any, Any, dict[str, Any]]]


class CronStore:
    """Persistência de jobs em arquivo JSON."""

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, CronJob] = {}
        self._load()

    def _load(self) -> None:
        """Carrega jobs do arquivo."""
        if not self.store_path.exists():
            self._cache = {}
            return

        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            jobs_data = data.get("jobs", [])
            self._cache = {
                job_data["id"]: CronJob.from_dict(job_data)
                for job_data in jobs_data
            }
        except Exception as e:
            print(f"[cron_store] Erro ao carregar jobs: {e}")
            self._cache = {}

    def _save(self) -> None:
        """Salva jobs no arquivo (atomic write)."""
        data = {
            "version": 1,
            "jobs": [job.to_dict() for job in self._cache.values()],
        }

        # Atomic write: escreve em temp, depois renomeia
        temp_path = self.store_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Backup do arquivo atual
            if self.store_path.exists():
                backup_path = self.store_path.with_suffix(".bak")
                self.store_path.replace(backup_path)

            temp_path.replace(self.store_path)
        except Exception as e:
            print(f"[cron_store] Erro ao salvar jobs: {e}")
            if temp_path.exists():
                temp_path.unlink()

    def list(self, include_disabled: bool = False) -> list[CronJob]:
        """Lista todos os jobs."""
        jobs = list(self._cache.values())
        if not include_disabled:
            jobs = [j for j in jobs if j.enabled]
        return jobs

    def get(self, job_id: str) -> CronJob | None:
        """Obtém um job por ID."""
        return self._cache.get(job_id)

    def add(self, job: CronJob) -> None:
        """Adiciona um job."""
        self._cache[job.id] = job
        self._save()

    def update(self, job: CronJob) -> None:
        """Atualiza um job."""
        job.updated_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self._cache[job.id] = job
        self._save()

    def remove(self, job_id: str) -> bool:
        """Remove um job."""
        if job_id in self._cache:
            del self._cache[job_id]
            self._save()
            return True
        return False


class CronService:
    """
    Serviço de agendamento robusto.

    Exemplo de uso:
    ```python
    service = CronService(store_path="./data/cron_jobs.json")

    # Registrar handler para ação
    @service.register_action("send_reminder")
    async def handle_reminder(job: CronJob) -> dict:
        # Enviar lembrete
        return {"status": "ok"}

    # Criar job
    await service.add(CronJobCreate(
        name="Lembrete diário",
        schedule=CronSchedule(kind="cron", expr="0 9 * * *"),
        action="send_reminder",
        params={"message": "Bom dia!"},
    ))

    # Iniciar serviço
    await service.start()
    ```
    """

    def __init__(
        self,
        store_path: str | Path | None = None,
        poll_interval_ms: int = 10_000,  # 10 segundos
        on_event: Callable[[CronEvent], None] | None = None,
    ) -> None:
        if store_path is None:
            store_path = Path("./data/cron_jobs.json")

        self.store = CronStore(store_path)
        self.poll_interval_ms = poll_interval_ms
        self.on_event = on_event

        self._running = False
        self._task: asyncio.Task | None = None
        self._action_handlers: dict[str, ActionHandler] = {}

        # Registrar handlers padrão
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Registra handlers padrão para ações comuns."""
        # Os handlers serão registrados externamente via register_action
        pass

    def register_action(self, action_name: str) -> Callable[[ActionHandler], ActionHandler]:
        """Decorator para registrar handler de ação."""
        def decorator(handler: ActionHandler) -> ActionHandler:
            self._action_handlers[action_name] = handler
            return handler
        return decorator

    def _emit_event(self, event: CronEvent) -> None:
        """Emite evento para callback externo."""
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                print(f"[cron_service] Erro ao emitir evento: {e}")

    async def start(self) -> None:
        """Inicia o serviço de agendamento."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        print("[cron_service] Iniciado")

    async def stop(self) -> None:
        """Para o serviço de agendamento."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        print("[cron_service] Parado")

    async def _run_loop(self) -> None:
        """Loop principal de verificação de jobs."""
        while self._running:
            try:
                await self._check_and_run_due_jobs()
            except Exception as e:
                print(f"[cron_service] Erro no loop: {e}")

            await asyncio.sleep(self.poll_interval_ms / 1000)

    async def _check_and_run_due_jobs(self) -> None:
        """Verifica e executa jobs pendentes."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        for job in self.store.list():
            if not job.enabled:
                continue

            # Calcula próximo horário se não definido
            if job.state.next_run_at_ms is None:
                job.state.next_run_at_ms = job.schedule.next_run_ms(now_ms)
                self.store.update(job)

            # Verifica se é hora de executar
            if job.state.next_run_at_ms and job.state.next_run_at_ms <= now_ms:
                if job.state.running_at_ms is None:  # Não está rodando
                    await self._run_job(job)

    async def _run_job(self, job: CronJob) -> None:
        """Executa um job."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # Marca como em execução
        job.state.running_at_ms = now_ms
        self.store.update(job)

        self._emit_event(CronEvent(
            job_id=job.id,
            action="started",
            run_at_ms=now_ms,
        ))

        start_ms = now_ms
        status: Literal["ok", "error", "skipped"] = "ok"
        error_msg: str | None = None

        try:
            handler = self._action_handlers.get(job.action)
            if handler:
                result = await handler(job)
                status = result.get("status", "ok")
                error_msg = result.get("error")
            else:
                print(f"[cron_service] Handler não encontrado para ação: {job.action}")
                status = "skipped"
        except Exception as e:
            status = "error"
            error_msg = str(e)
            print(f"[cron_service] Erro ao executar job {job.id}: {e}")

        # Atualiza estado
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        job.state.running_at_ms = None
        job.state.last_run_at_ms = start_ms
        job.state.last_status = status
        job.state.last_error = error_msg
        job.state.last_duration_ms = end_ms - start_ms

        # Calcula próxima execução
        if job.delete_after_run or job.schedule.kind == "at":
            job.state.next_run_at_ms = None
            if job.delete_after_run:
                self.store.remove(job.id)
                self._emit_event(CronEvent(
                    job_id=job.id,
                    action="removed",
                ))
                return
        else:
            job.state.next_run_at_ms = job.schedule.next_run_ms(end_ms)

        self.store.update(job)

        self._emit_event(CronEvent(
            job_id=job.id,
            action="finished",
            duration_ms=job.state.last_duration_ms,
            status=status,
            error=error_msg,
            next_run_at_ms=job.state.next_run_at_ms,
        ))

    # === API Pública ===

    async def add(self, create: CronJobCreate) -> CronJob:
        """Adiciona um novo job."""
        job_id = str(uuid.uuid4())
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        job = CronJob(
            id=job_id,
            name=create.name,
            schedule=create.schedule,
            action=create.action,
            params=create.params,
            enabled=create.enabled,
            delete_after_run=create.delete_after_run,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
            state=CronJobState(
                next_run_at_ms=create.schedule.next_run_ms(now_ms),
            ),
        )

        self.store.add(job)

        self._emit_event(CronEvent(
            job_id=job.id,
            action="added",
            next_run_at_ms=job.state.next_run_at_ms,
        ))

        return job

    async def update(self, job_id: str, patch: dict[str, Any]) -> CronJob | None:
        """Atualiza um job existente."""
        job = self.store.get(job_id)
        if not job:
            return None

        # Aplica patch
        if "name" in patch:
            job.name = patch["name"]
        if "enabled" in patch:
            job.enabled = patch["enabled"]
        if "params" in patch:
            job.params.update(patch["params"])
        if "schedule" in patch:
            schedule_patch = patch["schedule"]
            if "kind" in schedule_patch:
                job.schedule.kind = schedule_patch["kind"]
            if "at_ms" in schedule_patch:
                job.schedule.at_ms = schedule_patch["at_ms"]
            if "every_ms" in schedule_patch:
                job.schedule.every_ms = schedule_patch["every_ms"]
            if "expr" in schedule_patch:
                job.schedule.expr = schedule_patch["expr"]
            if "tz" in schedule_patch:
                job.schedule.tz = schedule_patch["tz"]
            # Recalcula próxima execução
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            job.state.next_run_at_ms = job.schedule.next_run_ms(now_ms)

        self.store.update(job)

        self._emit_event(CronEvent(
            job_id=job.id,
            action="updated",
            next_run_at_ms=job.state.next_run_at_ms,
        ))

        return job

    async def remove(self, job_id: str) -> bool:
        """Remove um job."""
        success = self.store.remove(job_id)
        if success:
            self._emit_event(CronEvent(
                job_id=job_id,
                action="removed",
            ))
        return success

    async def list(self, include_disabled: bool = False) -> list[CronJob]:
        """Lista todos os jobs."""
        return self.store.list(include_disabled)

    async def get(self, job_id: str) -> CronJob | None:
        """Obtém um job por ID."""
        return self.store.get(job_id)

    async def run_now(self, job_id: str) -> dict[str, Any]:
        """Executa um job imediatamente (força execução)."""
        job = self.store.get(job_id)
        if not job:
            return {"status": "error", "error": "Job não encontrado"}

        await self._run_job(job)
        return {"status": job.state.last_status, "error": job.state.last_error}

    def status(self) -> dict[str, Any]:
        """Retorna status do serviço."""
        jobs = self.store.list(include_disabled=True)
        enabled = [j for j in jobs if j.enabled]

        return {
            "running": self._running,
            "total_jobs": len(jobs),
            "enabled_jobs": len(enabled),
            "poll_interval_ms": self.poll_interval_ms,
            "registered_actions": list(self._action_handlers.keys()),
        }


# === Helpers para criar schedules comuns ===

def schedule_at(timestamp_ms: int) -> CronSchedule:
    """Cria schedule para execução única em timestamp específico."""
    return CronSchedule(kind="at", at_ms=timestamp_ms)


def schedule_at_datetime(dt: datetime) -> CronSchedule:
    """Cria schedule para execução única em datetime específico."""
    return CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))


def schedule_every(interval_ms: int) -> CronSchedule:
    """Cria schedule para execução a cada N milissegundos."""
    return CronSchedule(kind="every", every_ms=interval_ms)


def schedule_every_minutes(minutes: int) -> CronSchedule:
    """Cria schedule para execução a cada N minutos."""
    return CronSchedule(kind="every", every_ms=minutes * 60 * 1000)


def schedule_every_hours(hours: int) -> CronSchedule:
    """Cria schedule para execução a cada N horas."""
    return CronSchedule(kind="every", every_ms=hours * 60 * 60 * 1000)


def schedule_cron(expr: str, tz: str = "America/Sao_Paulo") -> CronSchedule:
    """Cria schedule com expressão cron."""
    return CronSchedule(kind="cron", expr=expr, tz=tz)


def schedule_daily_at(hour: int, minute: int = 0, tz: str = "America/Sao_Paulo") -> CronSchedule:
    """Cria schedule para execução diária em horário específico."""
    return CronSchedule(kind="cron", expr=f"{minute} {hour} * * *", tz=tz)


# === Exemplo de uso ===

if __name__ == "__main__":
    async def main():
        # Criar serviço
        service = CronService(store_path="./data/cron_jobs.json")

        # Registrar handler
        @service.register_action("test")
        async def handle_test(job: CronJob) -> dict:
            print(f"Executando job: {job.name}")
            return {"status": "ok"}

        # Criar job de teste
        job = await service.add(CronJobCreate(
            name="Teste a cada 5 segundos",
            schedule=schedule_every(5000),
            action="test",
        ))
        print(f"Job criado: {job.id}")

        # Iniciar serviço
        await service.start()

        # Rodar por 30 segundos
        await asyncio.sleep(30)

        # Parar serviço
        await service.stop()

    asyncio.run(main())
