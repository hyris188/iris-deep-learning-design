"""Update the report TOC and export PDF/DOC using LibreOffice's UNO bridge.

Run with a system Python providing python3-uno, e.g. /usr/bin/python3.
"""
from pathlib import Path
import socket
import subprocess
import tempfile
import time

import uno
from com.sun.star.beans import PropertyValue

ROOT = Path(__file__).resolve().parents[1]


def prop(name, value):
    p = PropertyValue(); p.Name = name; p.Value = value
    return p


def main():
    docs = sorted((ROOT/"report").glob("*_综合设计报告.docx"))
    if len(docs) != 1:
        raise RuntimeError("Expected exactly one generated report DOCX")
    path = docs[0]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="iris-report-office-") as temp:
        proc = subprocess.Popen(["soffice", "-env:UserInstallation="+Path(temp).as_uri(),
            "--headless", f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext",
            "--norestore", "--nodefault", "--nofirststartwizard"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            local = uno.getComponentContext()
            resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
            ctx = None
            for _ in range(100):
                try:
                    ctx = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
                    break
                except Exception:
                    time.sleep(.1)
            if ctx is None:
                raise RuntimeError("Could not connect to LibreOffice")
            desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
            doc = desktop.loadComponentFromURL(path.as_uri(), "_blank", 0, (prop("Hidden", True),))
            indexes = doc.getDocumentIndexes()
            if indexes.Count != 1:
                raise RuntimeError(f"Expected one table of contents, found {indexes.Count}")
            toc = indexes.getByIndex(0)
            toc.Level = 2
            # Standardize Contents paragraph fonts without changing heading sizes.
            styles = doc.StyleFamilies.getByName("ParagraphStyles")
            for name in ["Contents 1", "Contents 2", "Contents Heading"]:
                if styles.hasByName(name):
                    style = styles.getByName(name)
                    style.CharFontName = "Times New Roman"
                    style.CharFontNameAsian = "宋体"
                    style.CharHeight = 12.0
                    style.CharHeightAsian = 12.0
                    style.ParaTopMargin = 0
                    style.ParaBottomMargin = 0
                    spacing = uno.createUnoStruct("com.sun.star.style.LineSpacing")
                    spacing.Mode = 0
                    spacing.Height = 110
                    style.ParaLineSpacing = spacing
            for _ in range(2):
                toc.update(); doc.refresh()
            doc.storeAsURL(path.as_uri(), (prop("FilterName", "Office Open XML Text"), prop("Overwrite", True)))
            for suffix, filter_name in [(".pdf", "writer_pdf_Export"), (".doc", "MS Word 97")]:
                target = path.with_suffix(suffix)
                doc.storeToURL(target.as_uri(), (prop("FilterName", filter_name), prop("Overwrite", True)))
                print(target)
            doc.close(True)
            desktop.terminate()
        finally:
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=10)


if __name__ == "__main__":
    main()
