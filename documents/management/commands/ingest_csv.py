# documents/management/commands/ingest_csv.py
#
# Django management command wrapper around the ingest_csv service.
# Run with:
#   python manage.py ingest_csv Files/CDC-COVID-FAQ.csv
#
# The command is intentionally thin — all real logic lives in
# documents/services/ingestion.py so it can also be called from the
# IngestView API endpoint and the Celery task.

import os
from django.core.management.base import BaseCommand, CommandError
from documents.services.ingestion import ingest_csv


class Command(BaseCommand):
    help = "Ingest a CSV file (columns: category, question, answer; name is optional) into the vector store."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            type=str,
            help="Path to the CSV file to ingest.",
        )

    def handle(self, *args, **kwargs):
        file_path = kwargs["file_path"]

        if not os.path.isfile(file_path):
            raise CommandError(f"File not found: {file_path}")

        self.stdout.write(f"Ingesting '{file_path}' …")

        try:
            result = ingest_csv(file_path)
        except ValueError as exc:
            # Column validation error from ingest_csv
            raise CommandError(str(exc)) from exc
        except RuntimeError as exc:
            # Gemini API failure after retries
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Done.  source='{result['source']}'  "
                f"ingested={result['ingested']}  skipped={result['skipped']}"
            )
        )
