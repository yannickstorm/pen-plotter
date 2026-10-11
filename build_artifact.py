#!/usr/bin/env python3
"""Build the hosted (claude.ai Artifact) copy of Plot Studio from studio.html.

The hosted page is wrapped in its own <!doctype>/<html>/<head>/<body> skeleton, so those
tags are stripped; the Great Wave image is embedded as the example design.

Usage:  python3 build_artifact.py OUT.html [example-image]
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_EXAMPLE = HERE / "the-great-wave-zy8s4x93kmzqi9ei.webp"


def main():
    out = Path(sys.argv[1])
    example = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_EXAMPLE
    s = (HERE / "studio.html").read_text()
    s = re.sub(r"<!doctype html>\s*<html[^>]*>\s*<head>\s*", "", s, flags=re.I)
    s = re.sub(r'<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', "", s)
    s = re.sub(r"</head>\s*<body>\s*", "", s)
    s = re.sub(r"\s*</body>\s*</html>\s*$", "\n", s)
    if example.exists():
        mime = mimetypes.guess_type(example.name)[0] or "image/webp"
        uri = f"data:{mime};base64,{base64.b64encode(example.read_bytes()).decode()}"
        s = s.replace("const EXAMPLE_SRC = '';", f"const EXAMPLE_SRC = '{uri}';", 1)
    out.write_text(s)
    print(f"wrote {out} ({len(s) // 1024} KB)")


if __name__ == "__main__":
    main()
