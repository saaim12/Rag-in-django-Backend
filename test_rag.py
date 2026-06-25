import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from documents.services.rag import rag_query

result = rag_query("How does COVID-19 spread?")
print("ANSWER:", result["answer"])
print("---")
print("CONTEXT:", result["context"])