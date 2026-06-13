#!/usr/bin/env python3
"""Emit a synthetic regulatory seed corpus as JSONL (stdlib-only).

Produces documents in the exact shape `scripts/ingest.py` consumes
(``{"id", "source_id", "text"}``), using the REAL source_ids the regdoc-qa
golden dataset cites (atlas-prompts/evals/datasets/regdoc-qa/1.0.0.jsonl) plus
a spread of generated entries — so after ingestion the doc_search MCP returns
plausible hits AND the citations MCP can verify the golden dataset's ids.

Usage (writes JSONL to stdout):
    python scripts/make_seed_corpus.py --docs 40 > /tmp/corpus.jsonl
    ATLAS_GATEWAY_URL=http://gateway:8000 ATLAS_GATEWAY_API_KEY=dev-key \\
        ATLAS_EMBED_MODEL=mock python scripts/ingest.py --source /tmp/corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys

#: source_ids cited by the golden dataset — always included so citation
#: verification against the seeded corpus succeeds.
GOLDEN_SOURCE_IDS = [
    "EUR-BattReg-2023-1542-Art1",
    "EUR-CLP-1272-2008-Art17",
    "EUR-CLP-1272-2008-Art19",
    "EUR-REACH-Annex-XIV-Consolidated",
    "EUR-REACH-Annex-XVII-Entry-27",
    "EUR-REACH-Annex-XVII-Entry-51",
]

_SUBJECTS = [
    "substances of very high concern",
    "hazard classification and labelling",
    "safety data sheets",
    "restricted substances in consumer articles",
    "authorisation for continued use",
    "treated articles and biocidal claims",
    "battery carbon-footprint declarations",
    "downstream user obligations",
]
_OBLIGATIONS = [
    "manufacturers shall notify the competent authority within 30 days",
    "suppliers must provide an updated safety data sheet upon request",
    "placing on the market is prohibited above the concentration limit",
    "importers shall retain records for a period of ten years",
    "labels must state the hazard pictograms set out in Annex V",
    "an application for authorisation shall include a substitution plan",
    "economic operators shall draw up a declaration of conformity",
]
_SCOPES = [
    "This requirement applies to mixtures placed on the Union market.",
    "Articles intended for consumer use fall within the scope of this entry.",
    "Exemptions apply to scientific research and development under 1 tonne per year.",
    "Member States may impose additional national reporting duties.",
    "The restriction does not apply to second-hand articles first supplied "
    "before entry into force.",
]


def _paragraph(rng: random.Random, source_id: str, idx: int) -> str:
    return (
        f"{source_id} — provision {idx + 1}. Concerning {rng.choice(_SUBJECTS)}, "
        f"{rng.choice(_OBLIGATIONS)}. {rng.choice(_SCOPES)} "
        f"Concerning {rng.choice(_SUBJECTS)}, {rng.choice(_OBLIGATIONS)}."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a synthetic regulatory corpus (JSONL)")
    parser.add_argument(
        "--docs", type=int, default=30, help="total documents (>= the 6 golden ones)"
    )
    parser.add_argument("--paragraphs", type=int, default=6, help="paragraphs per document")
    parser.add_argument("--seed", type=int, default=42, help="rng seed (deterministic output)")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    source_ids = list(GOLDEN_SOURCE_IDS)
    for i in range(max(0, args.docs - len(source_ids))):
        source_ids.append(f"EUR-SYN-{2026}-{i + 1:03d}")

    for source_id in source_ids:
        text = " ".join(_paragraph(rng, source_id, p) for p in range(args.paragraphs))
        sys.stdout.write(json.dumps({"id": source_id, "source_id": source_id, "text": text}) + "\n")
    print(f"wrote {len(source_ids)} documents", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
