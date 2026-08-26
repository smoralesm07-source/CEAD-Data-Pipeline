from cead_pipeline.core import run_pipeline
from cead_pipeline.enrichment import build_enrichment_outputs

if __name__ == "__main__":
    core = run_pipeline()
    enrichment = build_enrichment_outputs()
    print({"core": core, "enrichment": enrichment})
