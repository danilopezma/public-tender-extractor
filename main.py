from pathlib import Path

from tender_extractor.extraction.extractor import extract_document

if __name__ == "__main__":
    input_path: Path = Path("data/acta_3_mesa_iinf_tecnico_prop_adj_am_pa_sum_42-20255_dais_censurada.pdf (5).pdf")
    output_path: Path = Path("output")
    report = extract_document(input_path, output_path)
    print(f"status={report['status']} errors={len(report['errors'])} -> {output_path}")
