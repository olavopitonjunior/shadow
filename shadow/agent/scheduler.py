"""
Scheduler - Agendador de tarefas para Shadow MVP.

Versão 2.0: Integrado com CronService para agendamento robusto.
Mantém compatibilidade com lembretes do banco de dados.
Versão 2.1: Adicionado suporte a alertas programados locais.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import httpx

from config import load_config
from storage import Storage
from bus import OutboundMessage, get_message_bus
from cron_service import (
    CronService,
    CronJob,
    CronJobCreate,
    CronSchedule,
    schedule_daily_at,
    schedule_every_minutes,
)


async def send_message(client: httpx.AsyncClient, url: str, message: str) -> None:
    """Envia mensagem via MessageBus (preferred) ou gateway direto (fallback)."""
    try:
        bus = get_message_bus()
        bus.publish_outbound(OutboundMessage(
            channel="whatsapp",
            chat_id="owner",
            content=message,
        ))
    except Exception:
        # Fallback to direct HTTP if bus is not available
        await client.post(url, json={"text": message})


def build_daily_summary(storage: Storage) -> str:
    """Constrói resumo diário de tarefas e compromissos."""
    tasks = storage.list_tasks(20)
    appointments = storage.list_appointments(20)
    lines = ["Resumo do dia:"]
    if tasks:
        lines.append("Tarefas pendentes:")
        for task in tasks[:5]:
            suffix = f" (ate {task.due_at})" if task.due_at else ""
            lines.append(f"- {task.title}{suffix}")
    else:
        lines.append("Sem tarefas pendentes.")
    if appointments:
        lines.append("Compromissos:")
        for appt in appointments[:5]:
            lines.append(f"- {appt.title} ({appt.scheduled_at})")
    else:
        lines.append("Sem compromissos agendados.")
    return "\n".join(lines)


class ShadowScheduler:
    """
    Scheduler integrado com CronService.

    Gerencia:
    - Envio de lembretes pendentes
    - Resumo diário automático
    - Jobs customizados via CronService
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        poll_seconds: int = 30,
        daily_summary_hour: int = 9,
        daily_summary_tz: str = "America/Sao_Paulo",
    ) -> None:
        cfg = load_config()
        self.gateway_url = gateway_url or cfg.gateway_send_url
        self.poll_seconds = poll_seconds
        self.daily_summary_hour = daily_summary_hour
        self.daily_summary_tz = daily_summary_tz

        self.storage = Storage()
        self._http_client: httpx.AsyncClient | None = None
        self._running = False

        # Inicializa CronService
        self.cron_service = CronService(
            store_path="./data/cron_jobs.json",
            poll_interval_ms=poll_seconds * 1000,
            on_event=self._on_cron_event,
        )

        # Registra handlers de ação
        self._register_action_handlers()

    def _register_action_handlers(self) -> None:
        """Registra handlers para ações do CronService."""

        @self.cron_service.register_action("send_reminder")
        async def handle_send_reminder(job: CronJob) -> dict:
            """Envia um lembrete específico."""
            message = job.params.get("message", "")
            if message and self._http_client and self.gateway_url:
                try:
                    await send_message(self._http_client, self.gateway_url, message)
                    return {"status": "ok"}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
            return {"status": "skipped"}

        @self.cron_service.register_action("daily_summary")
        async def handle_daily_summary(job: CronJob) -> dict:
            """Envia resumo diário."""
            if self._http_client and self.gateway_url:
                try:
                    summary = build_daily_summary(self.storage)
                    await send_message(self._http_client, self.gateway_url, summary)
                    print("[scheduler] Daily summary sent via CronService")
                    return {"status": "ok"}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
            return {"status": "skipped"}

        @self.cron_service.register_action("check_reminders")
        async def handle_check_reminders(job: CronJob) -> dict:
            """Verifica e envia lembretes pendentes do banco."""
            if not self._http_client or not self.gateway_url:
                return {"status": "skipped"}

            now_iso = datetime.now(timezone.utc).isoformat()
            sent_count = 0
            error_count = 0

            for row in self.storage.pending_reminders(now_iso):
                reminder_id = row["id"]
                message = row["message"]
                try:
                    await send_message(self._http_client, self.gateway_url, message)
                    self.storage.mark_reminder_sent(reminder_id)
                    sent_count += 1
                    print(f"[scheduler] Reminder {reminder_id} sent")
                except Exception as exc:
                    error_count += 1
                    print(f"[scheduler] Reminder {reminder_id} failed: {exc}")

            if error_count > 0:
                return {"status": "error", "error": f"{error_count} reminders failed"}
            return {"status": "ok", "sent": sent_count}

        @self.cron_service.register_action("process_suggestions")
        async def handle_process_suggestions(job: CronJob) -> dict:
            """Processa entidades e envia sugestões proativas."""
            if not self._http_client or not self.gateway_url:
                return {"status": "skipped", "reason": "no_gateway"}

            try:
                from suggestions import SuggestionProcessor, SuggestionSender

                # Get owner_id from config or job params
                cfg = load_config()
                owner_id = job.params.get("owner_id") or cfg.owner_e164

                if not owner_id:
                    return {"status": "skipped", "reason": "no_owner_id"}

                # Process entities into suggestions
                processor = SuggestionProcessor(self.storage)
                new_suggestions = processor.process_pending_entities(owner_id)

                # Send pending suggestions
                sender = SuggestionSender(self.gateway_url, self.storage)
                sent_count = await sender.send_pending(owner_id)

                print(f"[scheduler] Suggestions: created={len(new_suggestions)}, sent={sent_count}")
                return {
                    "status": "ok",
                    "created": len(new_suggestions),
                    "sent": sent_count,
                }

            except ImportError as e:
                print(f"[scheduler] Suggestions module not available: {e}")
                return {"status": "skipped", "reason": "module_not_found"}
            except Exception as e:
                print(f"[scheduler] Error processing suggestions: {e}")
                return {"status": "error", "error": str(e)}

        @self.cron_service.register_action("check_scheduled_alerts")
        async def handle_check_scheduled_alerts(job: CronJob) -> dict:
            """Verifica e envia alertas programados."""
            if not self._http_client or not self.gateway_url:
                return {"status": "skipped", "reason": "no_gateway"}

            sent_count = 0
            error_count = 0

            # Get all active alerts
            all_alerts = self._get_all_active_alerts()

            for alert in all_alerts:
                try:
                    if self._should_send_alert(alert):
                        content = self._build_alert_content(alert)
                        await send_message(self._http_client, self.gateway_url, content)
                        # Record that alert was sent
                        self.storage.record_alert_sent(
                            alert_id=alert["id"],
                            owner_id=alert["owner_id"],
                            content=content,
                            success=True,
                        )
                        sent_count += 1
                        print(f"[scheduler] Alert {alert['id']} sent: {alert.get('name', 'unnamed')}")
                except Exception as e:
                    error_count += 1
                    print(f"[scheduler] Alert {alert['id']} failed: {e}")
                    try:
                        self.storage.record_alert_sent(
                            alert_id=alert["id"],
                            owner_id=alert["owner_id"],
                            content="",
                            success=False,
                            error=str(e),
                        )
                    except Exception:
                        pass

            if error_count > 0:
                return {"status": "partial", "sent": sent_count, "errors": error_count}
            return {"status": "ok", "sent": sent_count}

    def _get_all_active_alerts(self) -> list[dict]:
        """Get all active alerts from storage."""
        try:
            # For SQLite, get all active alerts (all owners)
            cur = self.storage._conn.cursor()
            cur.execute("SELECT * FROM shadow_scheduled_alerts WHERE is_active = 1")
            alerts = []
            for row in cur.fetchall():
                alert = dict(row)
                # Convert integers to booleans
                for field in ["include_tasks", "include_appointments", "include_reminders", "include_overdue", "is_active"]:
                    if field in alert:
                        alert[field] = bool(alert[field])
                # Convert days_of_week string to list
                if alert.get("days_of_week"):
                    alert["days_of_week"] = [int(d) for d in str(alert["days_of_week"]).split(",")]
                alerts.append(alert)
            return alerts
        except Exception as e:
            print(f"[scheduler] Error getting alerts: {e}")
            return []

    def _should_send_alert(self, alert: dict) -> bool:
        """Check if an alert should be sent now."""
        try:
            # Get current time in alert's timezone
            tz_name = alert.get("timezone", "America/Sao_Paulo")
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("America/Sao_Paulo")

            now = datetime.now(tz)
            current_time = now.strftime("%H:%M")
            current_day = now.isoweekday()  # 1=Monday, 7=Sunday

            # Check if time matches (within 1 minute tolerance)
            alert_time = alert.get("alert_time", "")
            if not alert_time:
                return False

            # Parse times for comparison
            try:
                alert_hour, alert_min = map(int, alert_time.split(":"))
                current_hour, current_min = now.hour, now.minute

                # Check if within 1 minute window
                time_diff = abs((current_hour * 60 + current_min) - (alert_hour * 60 + alert_min))
                if time_diff > 1:  # More than 1 minute difference
                    return False
            except ValueError:
                return False

            # Check recurrence pattern
            recurrence = alert.get("recurrence", "daily")
            days_of_week = alert.get("days_of_week", [1, 2, 3, 4, 5, 6, 7])

            if recurrence == "weekdays":
                days_of_week = [1, 2, 3, 4, 5]
            elif recurrence == "weekly":
                # Weekly: only on the first day specified
                if days_of_week:
                    days_of_week = [days_of_week[0]]
                else:
                    days_of_week = [1]  # Monday

            if current_day not in days_of_week:
                return False

            # Check if already sent today
            last_sent = alert.get("last_sent_at")
            if last_sent:
                try:
                    last_sent_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
                    last_sent_local = last_sent_dt.astimezone(tz)
                    if last_sent_local.date() == now.date():
                        return False  # Already sent today
                except Exception:
                    pass

            return True

        except Exception as e:
            print(f"[scheduler] Error checking alert {alert.get('id')}: {e}")
            return False

    def _build_alert_content(self, alert: dict) -> str:
        """Build the content for an alert."""
        alert_type = alert.get("alert_type", "summary")
        owner_id = alert.get("owner_id", "")

        if alert_type == "reminder":
            # Simple reminder with custom message
            return alert.get("custom_message", "⏰ Lembrete!")

        elif alert_type == "custom":
            # Custom message
            return alert.get("custom_message", "📢 Alerta personalizado")

        else:  # summary
            # Build daily summary
            lines = []
            name = alert.get("name", "Resumo")
            lines.append(f"📋 {name}")
            lines.append("")

            if alert.get("include_tasks", True):
                tasks = self.storage.list_tasks(10)
                if tasks:
                    lines.append("📝 TAREFAS:")
                    for task in tasks[:5]:
                        due = f" (até {task.due_at})" if task.due_at else ""
                        lines.append(f"  • {task.title}{due}")
                    lines.append("")

            if alert.get("include_appointments", True):
                appointments = self.storage.list_appointments(10)
                if appointments:
                    lines.append("📅 COMPROMISSOS:")
                    for appt in appointments[:5]:
                        lines.append(f"  • {appt.title} - {appt.scheduled_at}")
                    lines.append("")

            if alert.get("include_overdue", True):
                # Check for overdue tasks
                now_iso = datetime.now(timezone.utc).isoformat()
                overdue = [t for t in self.storage.list_tasks(20) if t.due_at and t.due_at < now_iso]
                if overdue:
                    lines.append("⚠️ ATRASADAS:")
                    for task in overdue[:3]:
                        lines.append(f"  • {task.title}")
                    lines.append("")

            if not any(line.strip() for line in lines[2:]):
                lines.append("✨ Nenhuma pendência para hoje!")

            return "\n".join(lines)

    def _on_cron_event(self, event) -> None:
        """Callback para eventos do CronService."""
        print(f"[scheduler] CronEvent: {event.action} for job {event.job_id}")

    async def _setup_default_jobs(self) -> None:
        """Configura jobs padrão se não existirem."""
        existing_jobs = await self.cron_service.list(include_disabled=True)
        existing_actions = {j.action for j in existing_jobs}

        # Job de verificação de lembretes (a cada 1 minuto)
        if "check_reminders" not in existing_actions:
            await self.cron_service.add(CronJobCreate(
                name="Verificar lembretes pendentes",
                schedule=schedule_every_minutes(1),
                action="check_reminders",
            ))
            print("[scheduler] Created 'check_reminders' job")

        # Job de resumo diário
        if "daily_summary" not in existing_actions:
            await self.cron_service.add(CronJobCreate(
                name="Resumo diário",
                schedule=schedule_daily_at(
                    hour=self.daily_summary_hour,
                    minute=0,
                    tz=self.daily_summary_tz,
                ),
                action="daily_summary",
            ))
            print("[scheduler] Created 'daily_summary' job")

        # Job de verificação de alertas programados (a cada 1 minuto)
        if "check_scheduled_alerts" not in existing_actions:
            await self.cron_service.add(CronJobCreate(
                name="Verificar alertas programados",
                schedule=schedule_every_minutes(1),
                action="check_scheduled_alerts",
            ))
            print("[scheduler] Created 'check_scheduled_alerts' job")

        # Job de processamento de sugestões proativas (a cada 5 minutos)
        if "process_suggestions" not in existing_actions:
            await self.cron_service.add(CronJobCreate(
                name="Processar sugestões proativas",
                schedule=schedule_every_minutes(5),
                action="process_suggestions",
            ))
            print("[scheduler] Created 'process_suggestions' job")

    async def start(self) -> None:
        """Inicia o scheduler."""
        if not self.gateway_url:
            print("[scheduler] SHADOW_GATEWAY_SEND_URL not set. Scheduler disabled.")
            return

        self._running = True
        self._http_client = httpx.AsyncClient(timeout=10)

        # Configura jobs padrão
        await self._setup_default_jobs()

        # Inicia CronService
        await self.cron_service.start()
        print("[scheduler] Started with CronService")

    async def stop(self) -> None:
        """Para o scheduler."""
        self._running = False
        await self.cron_service.stop()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        print("[scheduler] Stopped")

    async def schedule_reminder(
        self,
        message: str,
        remind_at_ms: int,
        delete_after: bool = True,
    ) -> str:
        """
        Agenda um lembrete para envio futuro.

        Returns:
            ID do job criado
        """
        job = await self.cron_service.add(CronJobCreate(
            name=f"Lembrete: {message[:30]}...",
            schedule=CronSchedule(kind="at", at_ms=remind_at_ms),
            action="send_reminder",
            params={"message": message},
            delete_after_run=delete_after,
        ))
        return job.id

    def status(self) -> dict:
        """Retorna status do scheduler."""
        cron_status = self.cron_service.status()
        return {
            "running": self._running,
            "gateway_url": self.gateway_url,
            "cron_service": cron_status,
        }


# === Função de compatibilidade com versão anterior ===

async def run_scheduler(poll_seconds: int = 30) -> None:
    """
    Executa o scheduler (compatível com versão anterior).

    Agora usa CronService internamente.
    """
    scheduler = ShadowScheduler(poll_seconds=poll_seconds)
    await scheduler.start()

    try:
        # Mantém rodando indefinidamente
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        pass
    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(run_scheduler())