"""Keep the English and Spanish integration examples executable as wire contracts."""

import json
from pathlib import Path
import re

import pytest

from akay_convert_to_markdown.contracts.events import parse_event
from akay_convert_to_markdown.contracts.requests import IndexProfile, parse_request
from akay_convert_to_markdown.models.conversion_request import parse_conversion_request


@pytest.mark.parametrize("filename", ["README.md", "README-es.md"])
def test_readme_json_examples_match_the_runtime_contracts(filename):
    text = (Path(__file__).parents[2] / filename).read_text(encoding="utf-8")
    requests, events, rebuilds = 0, 0, 0
    for block in re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL):
        data = json.loads(block)
        if isinstance(data, list):
            for profile in data:
                IndexProfile.model_validate_json(json.dumps(profile))
        elif "eventType" in data:
            parse_event(block)
            events += 1
        elif "requestId" in data:
            if "schemaVersion" not in data:
                parse_conversion_request(block)
                continue
            worker = ("index" if data.get("operation") in {"index", "delete"} else
                      "document" if data["contentType"] == "document" else "media")
            job = parse_request(block, worker=worker, callbacks={data["callback"]})
            requests += 1
            if getattr(job, "operation", None) == "rebuildFromMarkdown":
                assert "destinationBlobName" not in data and "extractionReviewBlobName" not in data
                rebuilds += 1
    assert requests > 0 and events > 0 and rebuilds == 2
