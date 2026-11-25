"""Inventory existing structured formula occurrences without inference or text parsing."""

from docling_core.types.doc import DoclingDocument, FormulaItem

from akay_convert_to_markdown.contracts.artifacts import ReviewFormula, Section


def collect_formulas(document: DoclingDocument, sections: list[Section]) -> list[ReviewFormula]:
    by_ref = {section.docling_item_ref: section.id for section in sections}
    current_section = None
    section_by_ref = {}
    # Core defaults to the body layer, matching section serialization. Map by
    # reading order, not text-array indices (which can differ after insertion).
    for item, _ in document.iterate_items(traverse_pictures=True):
        if item.self_ref in by_ref:
            current_section = by_ref[item.self_ref]
        if isinstance(item, FormulaItem):
            section_by_ref[item.self_ref] = current_section
    formulas = []
    for item in document.texts:
        if not isinstance(item, FormulaItem):
            continue
        # Pinned Core 2.99 / Docling 2.141: orig retains source text; text is
        # the decoded math representation (empty for undecoded PDF formulas).
        # Availability is not a guarantee of syntactic or mathematical validity.
        formulas.append(ReviewFormula(id=f"formula-{len(formulas) + 1:03d}",
                                      docling_item_ref=item.self_ref,
                                      section_id=section_by_ref.get(item.self_ref),
                                      text=item.orig or item.text,
                                      latex=item.text if item.text.strip() else None,
                                      page_number=item.prov[0].page_no if item.prov else None))
    return formulas
