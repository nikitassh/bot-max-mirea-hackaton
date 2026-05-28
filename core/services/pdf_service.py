import io
import fitz  # pymupdf
from loguru import logger


def extract_text(file_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        parts = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"pdf extract_text error: {e}")
        return ""
