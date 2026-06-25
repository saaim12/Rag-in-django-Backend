# documents/views.py
#
# DRF API views for the RAG backend.
#
# Endpoints:
#   POST /api/documents/query/   – run a RAG query
#   POST /api/documents/ingest/  – upload and ingest a CSV file
#   GET  /api/documents/health/  – liveness / readiness probe

import os
import logging
import tempfile

from django.db import connection, OperationalError
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

# TODO: Uncomment the line below and add `permission_classes = [IsAuthenticated]`
# to each view class before deploying to production.
# from rest_framework.permissions import IsAuthenticated

from .models import DocumentChunk
from .services.rag import rag_query
from .services.ingestion import ingest_csv

logger = logging.getLogger(__name__)


class QueryView(APIView):
    """
    POST /api/documents/query/

    Run a RAG query: embed the question, retrieve relevant chunks, generate
    a grounded answer via Gemini.

    Request body (JSON):
        {
            "query":    "How does COVID-19 spread?",   # required
            "category": "Transmission"                 # optional — scopes retrieval
        }

    Response (200):
        {
            "answer":       "...",
            "context":      ["Q: ... A: ...", ...],
            "source_count": 3
        }
    """
    # permission_classes = [IsAuthenticated]  # TODO: enable for production
    parser_classes = [JSONParser]

    def post(self, request):
        query = request.data.get("query", "").strip()
        if not query:
            return Response(
                {"error": "query is required and must not be blank."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        category = request.data.get("category") or None

        try:
            result = rag_query(query, category=category)
            return Response(result, status=status.HTTP_200_OK)

        except RuntimeError as exc:
            logger.error("RAG query failed: %s", exc)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("Unexpected error in QueryView")
            return Response(
                {"error": "An unexpected error occurred. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class IngestView(APIView):
    """
    POST /api/documents/ingest/

    Upload a CSV file and ingest it into the vector store.  Accepts
    multipart/form-data with a single field named `file`.

    The upload is synchronous — large files will block the request worker.
    See documents/tasks.py for the async Celery alternative.

    Request: multipart/form-data
        file: <CSV file>   # required; must have columns name,category,question,answer

    Response (200):
        {
            "source":   "CDC-COVID-FAQ.csv",
            "ingested": 142,
            "skipped":  3
        }
    """
    # permission_classes = [IsAuthenticated]  # TODO: enable for production
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        csv_file = request.FILES.get("file")

        if not csv_file:
            return Response(
                {"error": "A CSV file is required. Send it as multipart/form-data with key 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not csv_file.name.lower().endswith(".csv"):
            return Response(
                {"error": "Only CSV files are accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Write the upload to a temp file so the service layer can open it
        # as a normal file path.  We keep the original filename so the
        # idempotency guard in ingest_csv uses the right source label.
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".csv", delete=False
            ) as tmp:
                for chunk in csv_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            result = ingest_csv(tmp_path, source_name=csv_file.name)
            return Response(result, status=status.HTTP_200_OK)

        except ValueError as exc:
            # Raised by ingest_csv for missing columns / empty file.
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RuntimeError as exc:
            logger.error("Ingestion failed: %s", exc)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("Unexpected error in IngestView")
            return Response(
                {"error": "An unexpected error occurred during ingestion."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


class HealthView(APIView):
    """
    GET /api/documents/health/

    Lightweight liveness / readiness check.  Verifies database connectivity
    and returns the total number of stored chunks.  Useful as a deploy smoke
    test or a load-balancer health probe.

    Response (200):
        {"status": "ok", "chunk_count": 142}

    Response (503):
        {"status": "error", "detail": "..."}
    """

    def get(self, request):
        try:
            # Cheapest possible DB round-trip — just confirm the connection works.
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            chunk_count = DocumentChunk.objects.count()
            return Response(
                {"status": "ok", "chunk_count": chunk_count},
                status=status.HTTP_200_OK,
            )
        except OperationalError as exc:
            logger.error("Health check DB error: %s", exc)
            return Response(
                {"status": "error", "detail": "Database connection failed."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("Health check unexpected error")
            return Response(
                {"status": "error", "detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
