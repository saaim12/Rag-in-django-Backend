# documents/tasks.py
#
# Celery task definitions for async ingestion.
#
# WHY CELERY?
#   Embedding hundreds of CSV rows involves many sequential Gemini API calls.
#   Doing this synchronously inside an HTTP request blocks the Gunicorn worker
#   for potentially minutes, starving other requests.  Moving ingestion to a
#   background Celery task lets the API return immediately with a job ID while
#   the worker processes the file.
#
# HOW TO ENABLE:
#   1. Install Redis (or any AMQP broker):
#         docker run -p 6379:6379 redis
#   2. Install packages:
#         pip install celery redis
#   3. Uncomment the Celery settings block in core/settings.py.
#   4. Create core/celery.py (boilerplate shown below).
#   5. Start a worker alongside Django:
#         celery -A core worker --loglevel=info
#
# CORE CELERY APP BOILERPLATE (core/celery.py):
# -----------------------------------------------
#   import os
#   from celery import Celery
#
#   os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
#   app = Celery("core")
#   app.config_from_object("django.conf:settings", namespace="CELERY")
#   app.autodiscover_tasks()
# -----------------------------------------------
# Then add to core/__init__.py:
#   from .celery import app as celery_app
#   __all__ = ("celery_app",)
# -----------------------------------------------
#
# The management command (python manage.py ingest_csv <path>) remains fully
# functional and does NOT require Celery — it's the synchronous fallback.

# Uncomment everything below once Celery is installed and configured.

# from celery import shared_task
# from documents.services.ingestion import ingest_csv as _ingest_csv
# import logging
#
# logger = logging.getLogger(__name__)
#
#
# @shared_task(bind=True, max_retries=3, default_retry_delay=30)
# def ingest_csv_task(self, file_path: str, source_name: str | None = None) -> dict:
#     """
#     Async Celery task that wraps ingest_csv.
#
#     Args:
#         file_path:   Absolute path to the CSV file (must be accessible by
#                      the worker process).
#         source_name: Optional override for the source label; see ingest_csv.
#
#     Returns:
#         {"source": str, "ingested": int, "skipped": int}
#
#     The task auto-retries up to 3 times on RuntimeError (Gemini quota
#     failures).  Other exceptions bubble up immediately.
#     """
#     try:
#         return _ingest_csv(file_path, source_name=source_name)
#     except RuntimeError as exc:
#         logger.warning("Ingestion task failed, retrying: %s", exc)
#         raise self.retry(exc=exc)
