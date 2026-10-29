"""Document assistant: validate uploads, extract text per page, and retrieve relevant
passages with BM25 (pure Python - no vector database or external service needed)."""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter

from . import config

_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_STOP = set("the a an and or of to in on for is are be by with as at from that this it its was were can "
            "will shall may not no which what how when where who".split())
CHUNK_CHARS = 1200


class UploadError(ValueError):
    pass


def validate_upload(filename: str, data: bytes) -> None:
    name = filename.lower()
    if not name.endswith(config.ALLOWED_UPLOAD_EXTENSIONS):
        raise UploadError(f"Unsupported file type. Allowed: {', '.join(config.ALLOWED_UPLOAD_EXTENSIONS)}")
    if len(data) == 0:
        raise UploadError("The file is empty.")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadError(f"File exceeds the {config.MAX_UPLOAD_MB:g} MB limit.")
    if name.endswith(".pdf") and not data.startswith(b"%PDF"):
        raise UploadError("File has a .pdf extension but is not a PDF.")


def extract_pages(filename: str, data: bytes) -> list[tuple[int, str]]:
    validate_upload(filename, data)
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise UploadError("Encrypted PDFs are not supported.")
            pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
        except PdfReadError as e:
            raise UploadError(f"Could not read PDF: {e}") from None
    else:
        text = data.decode("utf-8", errors="replace")
        pages = [(1, text)]
    pages = [(n, t) for n, t in pages if t]
    if not pages:
        raise UploadError("No extractable text found (scanned PDFs need OCR, which is not yet supported).")
    return pages


def chunk_pages(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    out = []
    for n, text in pages:
        text = re.sub(r"\s+", " ", text)
        for i in range(0, len(text), CHUNK_CHARS):
            out.append((n, text[max(0, i - 150): i + CHUNK_CHARS]))
    return out


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


def search(chunks: list[dict], query: str, k: int = 5, k1: float = 1.5, b: float = 0.75) -> list[dict]:
    """BM25 ranking. Returns chunks (with 'score') that share at least one term with the query."""
    q = tokenize(query)
    if not q or not chunks:
        return []
    docs = [Counter(tokenize(c["text"])) for c in chunks]
    lens = [sum(d.values()) for d in docs]
    avg = sum(lens) / len(lens) or 1
    n = len(docs)
    df = Counter(t for d in docs for t in set(d))
    scored = []
    for c, d, ln in zip(chunks, docs, lens):
        s = 0.0
        for t in q:
            if t in d:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * d[t] * (k1 + 1) / (d[t] + k1 * (1 - b + b * ln / avg))
        if s > 0:
            scored.append({**c, "score": round(s, 3)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:k]
