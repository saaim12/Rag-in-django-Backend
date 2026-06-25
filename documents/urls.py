# documents/urls.py
from django.urls import path
from .views import HealthView, IngestView, QueryView

urlpatterns = [
    path("query/", QueryView.as_view(), name="rag-query"),
    path("ingest/", IngestView.as_view(), name="rag-ingest"),
    path("health/", HealthView.as_view(), name="rag-health"),
]
