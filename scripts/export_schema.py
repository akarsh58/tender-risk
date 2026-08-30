"""Write the exact TenderRisk output schema to a file for client integration."""

import json
from pathlib import Path

from tenderrisk.output_schema import tender_analysis_schema

Path("docs/tender-analysis-output-schema.json").write_text(
    json.dumps(tender_analysis_schema(), indent=2), encoding="utf-8"
)

