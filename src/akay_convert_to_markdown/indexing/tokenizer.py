"""Explicit hash-verified cl100k_base assets; never downloads at job time."""

import base64
import hashlib
from pathlib import Path

import tiktoken
from pydantic import ConfigDict
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

from akay_convert_to_markdown.errors.exceptions import TransientError
from akay_convert_to_markdown.indexing.profiles import MAX_INPUT_TOKENS

CL100K_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
# Exact pattern and special-token IDs from tiktoken 0.12.0 openai_public.py.
_PATTERN = r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"


class Cl100kTokenizer(BaseTokenizer):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    encoding: tiktoken.Encoding

    @classmethod
    def from_file(cls, path: Path):
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != CL100K_SHA256:
                raise ValueError()
            ranks = {base64.b64decode(token): int(rank) for token, rank in (line.split() for line in raw.splitlines())}
            encoding = tiktoken.Encoding(name="cl100k_base", pat_str=_PATTERN, mergeable_ranks=ranks,
                                         special_tokens={"<|endoftext|>": 100257, "<|fim_prefix|>": 100258,
                                                         "<|fim_middle|>": 100259, "<|fim_suffix|>": 100260,
                                                         "<|endofprompt|>": 100276})
            return cls(encoding=encoding)
        except Exception:
            raise TransientError("The explicit local cl100k_base asset is missing or incompatible.") from None

    def count_tokens(self, text: str) -> int:
        # Literal special-looking strings in untrusted documents are ordinary
        # text, not control tokens. The embedding endpoint receives that text.
        return len(self.encoding.encode_ordinary(text))

    def get_max_tokens(self) -> int:
        return MAX_INPUT_TOKENS

    def get_tokenizer(self):
        return self.count_tokens
