from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkResult:
    chunk_text: str
    source_span_start: int
    source_span_end: int


class TextChunker:
    def __init__(self, target_chars: int = 1000, overlap_chars: int = 150) -> None:
        if target_chars <= 0:
            raise ValueError('target_chars must be positive')
        if overlap_chars < 0:
            raise ValueError('overlap_chars must be non-negative')
        if overlap_chars >= target_chars:
            raise ValueError('overlap_chars must be smaller than target_chars')
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars

    def chunk(self, text: str) -> list[ChunkResult]:
        normalized = text.replace('\r\n', '\n').strip()
        if not normalized:
            return []

        paragraphs = self._split_paragraphs(normalized)
        chunks: list[ChunkResult] = []
        current_text = ''
        current_start: int | None = None
        current_end = 0

        for paragraph_text, paragraph_start, paragraph_end in paragraphs:
            if not paragraph_text.strip():
                continue

            if len(paragraph_text) > self.target_chars:
                if current_text:
                    chunks.append(self._finalize_chunk(current_text, current_start, current_end, normalized))
                    current_text = ''
                    current_start = None
                    current_end = 0
                chunks.extend(self._split_long_paragraph(paragraph_text, paragraph_start, normalized))
                continue

            if not current_text:
                current_text = normalized[paragraph_start:paragraph_end]
                current_start = paragraph_start
                current_end = paragraph_end
                continue

            candidate = normalized[current_start:paragraph_end]
            if len(candidate) <= self.target_chars:
                current_text = candidate
                current_end = paragraph_end
            else:
                chunks.append(self._finalize_chunk(current_text, current_start, current_end, normalized))
                current_text = normalized[paragraph_start:paragraph_end]
                current_start = paragraph_start
                current_end = paragraph_end

        if current_text:
            chunks.append(self._finalize_chunk(current_text, current_start, current_end, normalized))

        return chunks

    def _split_paragraphs(self, text: str) -> list[tuple[str, int, int]]:
        paragraphs: list[tuple[str, int, int]] = []
        cursor = 0
        length = len(text)
        while cursor < length:
            while cursor < length and text[cursor] == '\n':
                cursor += 1
            if cursor >= length:
                break
            end = text.find('\n\n', cursor)
            if end == -1:
                end = length
            paragraph_raw = text[cursor:end]
            paragraph = paragraph_raw.strip()
            if paragraph:
                leading = len(paragraph_raw) - len(paragraph_raw.lstrip())
                trimmed_start = cursor + leading
                trimmed_end = trimmed_start + len(paragraph)
                paragraphs.append((paragraph, trimmed_start, trimmed_end))
            cursor = end + 2
        return paragraphs

    def _split_long_paragraph(self, paragraph_text: str, paragraph_start: int, normalized_content: str) -> list[ChunkResult]:
        results: list[ChunkResult] = []
        cursor = 0
        length = len(paragraph_text)
        step = self.target_chars - self.overlap_chars
        if step <= 0:
            raise ValueError('invalid chunker step size')

        while cursor < length:
            end = min(cursor + self.target_chars, length)
            chunk_text = paragraph_text[cursor:end]
            if not chunk_text:
                break
            while chunk_text and chunk_text[-1].isspace() and (cursor + len(chunk_text)) < length:
                chunk_text = chunk_text[:-1]
            if not chunk_text:
                break
            source_start = paragraph_start + cursor
            source_end = source_start + len(chunk_text)
            if source_end <= source_start:
                raise ValueError('invalid chunk span produced by chunker')
            if source_end > len(normalized_content):
                raise ValueError('chunk span out of bounds')
            if normalized_content[source_start:source_end] != chunk_text:
                raise ValueError('chunk text does not match normalized content span')
            results.append(ChunkResult(chunk_text=chunk_text, source_span_start=source_start, source_span_end=source_end))
            if end >= length:
                break
            next_cursor = cursor + step
            if next_cursor <= cursor:
                next_cursor = cursor + 1
            cursor = next_cursor
        return results

    def _finalize_chunk(self, chunk_text: str, source_span_start: int | None, source_span_end: int, normalized_content: str) -> ChunkResult:
        if source_span_start is None:
            source_span_start = 0
        if not chunk_text:
            raise ValueError('empty chunk produced')
        if source_span_end <= source_span_start:
            raise ValueError('invalid chunk span produced')
        if source_span_end > len(normalized_content):
            raise ValueError('chunk span out of bounds')
        if normalized_content[source_span_start:source_span_end] != chunk_text:
            raise ValueError('chunk text does not match normalized content span')
        return ChunkResult(chunk_text=chunk_text, source_span_start=source_span_start, source_span_end=source_span_end)


def _run_text_chunker_assertions() -> None:
    def verify(text: str) -> list[ChunkResult]:
        chunker = TextChunker(target_chars=1000, overlap_chars=150)
        normalized = text.replace('\r\n', '\n').strip()
        chunks = chunker.chunk(text)
        assert chunks, 'expected chunks'
        prev_start = -1
        for idx, chunk in enumerate(chunks):
            assert chunk.chunk_text, f'empty chunk {idx}'
            assert chunk.source_span_start >= 0, f'negative start {idx}'
            assert chunk.source_span_end > chunk.source_span_start, f'invalid span {idx}'
            assert chunk.source_span_end <= len(normalized), f'out of bounds {idx}'
            assert normalized[chunk.source_span_start:chunk.source_span_end] == chunk.chunk_text, f'span mismatch {idx}'
            assert chunk.source_span_start > prev_start, f'non-monotonic start {idx}'
            prev_start = chunk.source_span_start
        return chunks

    verify('First paragraph\n\nSecond paragraph')
    verify('First paragraph\n\n\nSecond paragraph')
    verify('First paragraph\n\n\n\n\nSecond paragraph')
    verify('First paragraph\nSecond paragraph')
    long_paragraph = 'A' * 2500
    chunks = verify(long_paragraph)
    assert len(chunks) == 3
    assert [chunk.source_span_start for chunk in chunks] == [0, 850, 1700]
    assert [chunk.source_span_end for chunk in chunks] == [1000, 1850, 2500]
    assert all(len(chunk.chunk_text) <= 1000 for chunk in chunks)
    normalized = long_paragraph.strip()
    assert all(normalized[chunk.source_span_start:chunk.source_span_end] == chunk.chunk_text for chunk in chunks)


if __name__ == '__main__':
    _run_text_chunker_assertions()
    print('TextChunker assertions passed')
