import io
import os
import zipfile
from typing import Iterable


def build_zip(paths: Iterable[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            archive.write(path, arcname=os.path.basename(path))
    buffer.seek(0)
    return buffer.read()
