#!/usr/bin/env python3
"""Build the hosted (claude.ai Artifact) copy of Plot Studio from studio.html.

The hosted page is wrapped in its own <!doctype>/<html>/<head>/<body> skeleton, so those
tags are stripped; the Great Wave image is embedded as the example design.

Usage:  python3 build_artifact.py OUT.html [example-image] [--standalone]

--standalone gives the page back the doctype, charset and viewport that the hosted skeleton normally provides, for
serving it on its own (GitHub Pages, the offline plot-studio.html). Without the viewport a phone lays the page out
at about 980 px and shrinks it, which looks like the desktop version.
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_EXAMPLE = HERE / "tests" / "great-wave.webp"


STANDALONE_HEAD = '<!doctype html>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    standalone = "--standalone" in sys.argv
    out = Path(args[0])
    example = Path(args[1]) if len(args) > 1 else DEFAULT_EXAMPLE
    s = (HERE / "studio.html").read_text()
    s = re.sub(r"<!doctype html>\s*<html[^>]*>\s*<head>\s*", "", s, flags=re.I)
    s = re.sub(r'<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', "", s)
    s = re.sub(r"</head>\s*<body>\s*", "", s)
    s = re.sub(r"\s*</body>\s*</html>\s*$", "\n", s)
    if example.exists():
        mime = mimetypes.guess_type(example.name)[0] or "image/webp"
        uri = f"data:{mime};base64,{base64.b64encode(example.read_bytes()).decode()}"
        s = s.replace("const EXAMPLE_SRC = '';", f"const EXAMPLE_SRC = '{uri}';", 1)
    out.write_text((STANDALONE_HEAD if standalone else "") + s)
    print(f"wrote {out} ({len(s) // 1024} KB)")


if __name__ == "__main__":
    main()
