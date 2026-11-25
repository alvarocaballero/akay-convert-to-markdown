"""Core-only section identity/serialization shared by export and saved-JSON chunking."""

import json
from uuid import UUID, uuid5

from pydantic import Field
from docling_core.transforms.serializer.markdown import MarkdownTextSerializer
from docling_core.types.doc import SectionHeaderItem, TitleItem

from akay_convert_to_markdown.contracts.artifacts import Section


SECTION_NAMESPACE = UUID("bdac804b-e605-5299-872e-42443fecc0c9")


def section_id(content_key: str, docling_item_ref: str) -> UUID:
    """N0's exact Unicode/compact-JSON identity; no title or request-ID dependency."""
    name = json.dumps(["section-v1", content_key, docling_item_ref], ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)
    return uuid5(SECTION_NAMESPACE, name)


class SectionTextSerializer(MarkdownTextSerializer):
    """Attach identity while Core renders real headings, never by matching text."""

    content_key: str | None = None
    sections: list[Section] = Field(default_factory=list)

    def _format_heading(self, text: str, item: TitleItem | SectionHeaderItem,
                        in_table_cell: bool = False) -> str:
        heading = super()._format_heading(text, item, in_table_cell=in_table_cell)
        if self.content_key is None or in_table_cell or not text.strip():
            return heading
        level = 1 if isinstance(item, TitleItem) else item.level + 1
        parent = next((s for s in reversed(self.sections) if s.level < level), None)
        section = Section(id=section_id(self.content_key, item.self_ref),
                          parent_id=parent.id if parent else None, title=item.text or text,
                          level=level, order=len(self.sections), docling_item_ref=item.self_ref,
                          page_number=item.prov[0].page_no if item.prov else None)
        self.sections.append(section)
        return f'<!-- akay-section:start id="{section.id}" -->\n{heading}'
