from cead_pipeline.core import run_pipeline
from cead_pipeline.documents import refresh_document_catalog
from cead_pipeline.enrichment import build_enrichment_outputs

if __name__ == "__main__":
    core = run_pipeline()
    documents = refresh_document_catalog()
    enrichment = build_enrichment_outputs()
    print({"core": core, "documents": documents, "enrichment": enrichment})
