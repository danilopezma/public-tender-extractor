"""Extract the concurrency from a tender meeting record PDF and write the deliverables."""

import argparse
from pathlib import Path

from tender_extractor.export.writers import (
    CONCURRENCIA_FILE, INCIDENCIAS_FILE, XLSX_FILE, write_concurrencia, write_incidencias,
    write_xlsx,
)
from tender_extractor.extraction.extractor import extract_concurrency

DEFAULT_PDF = "data/acta_3_mesa_iinf_tecnico_prop_adj_am_pa_sum_42-20255_dais_censurada.pdf (5).pdf"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path, default=Path(DEFAULT_PDF))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    # 1. Extract --------------------------------------------------------------
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = extract_concurrency(args.pdf)

    # 2. Write the deliverables -----------------------------------------------
    write_concurrencia(args.output_dir / CONCURRENCIA_FILE, result.tender, result.offers)
    write_incidencias(args.output_dir / INCIDENCIAS_FILE, result.issues)
    write_xlsx(args.output_dir / XLSX_FILE, result.tender, result.offers)
    print(f"offers={len(result.offers)} issues={len(result.issues)} -> {args.output_dir}")
