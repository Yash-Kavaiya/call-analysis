"""Celery application configuration for background task processing."""

from __future__ import annotations

import logging
from celery import Celery, Task
from celery.signals import task_failure, task_retry, task_success, worker_ready, worker_shutdown
from kombu import Queue

from call_analysis.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

# Celery app
celery_app = Celery("call_analysis")

# Configuration
celery_app.conf.update(
    broker_url=settings.celery.broker_url,
    result_backend=settings.celery.result_backend,
    task_serializer=settings.celery.task_serializer,
    result_serializer=settings.celery.result_serializer,
    accept_content=settings.celery.accept_content,
    timezone=settings.celery.timezone,
    enable_utc=settings.celery.enable_utc,
    task_track_started=settings.celery.task_track_started,
    task_time_limit=settings.celery.task_time_limit,
    task_soft_time_limit=settings.celery.task_soft_time_limit,
    worker_prefetch_multiplier=settings.celery.worker_prefetch_multiplier,
    worker_max_tasks_per_child=settings.celery.worker_max_tasks_per_child,
    result_expires=settings.celery.result_expires,
    beat_schedule_filename=settings.celery.beat_schedule_filename,
    # Task routing
    task_routes={
        "call_analysis.tasks.process_call": {"queue": "analysis"},
        "call_analysis.tasks.analyze_batch": {"queue": "batch"},
        "call_analysis.tasks.webhook_delivery": {"queue": "webhooks"},
        "call_analysis.tasks.cleanup": {"queue": "maintenance"},
    },
    task_default_queue="default",
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("analysis", routing_key="analysis"),
        Queue("batch", routing_key="batch"),
        Queue("webhooks", routing_key="webhooks"),
        Queue("maintenance", routing_key="maintenance"),
    ),
    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=3,
    # Result backend
    result_extended=True,
    result_compression="gzip",
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Custom task base class with error handling
class BaseTask(Task):
    """Base task class with common functionality."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}", exc_info=einfo)
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f"Task {task_id} retry: {exc}")
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Task {task_id} succeeded")
        super().on_success(retval, task_id, args, kwargs)


celery_app.Task = BaseTask


# Signal handlers
@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    logger.info(f"Worker {sender.hostname} ready")


@worker_shutdown.connect
def on_worker_shutdown(sender=None, **kwargs):
    logger.info(f"Worker {sender.hostname} shutting down")


@task_success.connect
def on_task_success(sender=None, result=None, **kwargs):
    logger.debug(f"Task {sender.name} succeeded")


@task_failure.connect
def on_task_failure(sender=None, exception=None, **kwargs):
    logger.error(f"Task {sender.name} failed: {exception}")


@task_retry.connect
def on_task_retry(sender=None, reason=None, **kwargs):
    logger.warning(f"Task {sender.name} retry: {reason}")


# Import tasks to register them
def register_tasks() -> None:
    """Import task modules to register them with Celery."""
    from call_analysis import tasks  # noqa: F401


# Auto-register on import
register_tasks()


# Health check
async def check_celery_health() -> dict[str, Any]:
    """Check Celery worker health."""
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        active = inspect.active()
        registered = inspect.registered()

        if stats is None:
            return {"healthy": False, "error": "No workers responding"}

        return {
            "healthy": True,
            "workers": list(stats.keys()),
            "active_tasks": sum(len(tasks) for tasks in (active or {}).values()),
            "registered_tasks": list(set().union(*(registered or {}).values())),
        }
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {"healthy": False, "error": str(e)}


# Periodic tasks (Celery Beat)
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "cleanup-old-jobs": {
        "task": "call_analysis.tasks.cleanup_old_jobs",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    "cleanup-old-events": {
        "task": "call_analysis.tasks.cleanup_old_events",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
    },
    "system-metrics-collection": {
        "task": "call_analysis.tasks.collect_system_metrics",
        "schedule": 60.0,  # Every minute
    },
}