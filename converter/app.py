"""NoLimit Docs converter: exact Office conversions with LibreOffice, any format to any format.

Pairs LibreOffice saves directly (Word to PDF, PowerPoint to PPTX, Excel to CSV...) go straight through it.
Every other pair goes through PDF first, which LibreOffice renders exactly, then:
  PDF -> Word         pdf2docx rebuilds text, layout, images and tables as an editable document
  PDF -> PowerPoint   one slide per page, each the exact page image
  PDF -> Excel / CSV  tables found on each page (text lines when a page has no table)
  PDF -> text         the text layer
  PDF -> PNG / JPG    each page as an image (a ZIP when there is more than one page)
Files live only in a per-request temp directory that is deleted when the response is sent.
"""
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import fitz  # PyMuPDF
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from unoserver.client import UnoClient

app = FastAPI()
KEY = os.environ.get("NL_KEY", "")
MAX_BYTES = 30 * 1024 * 1024

FAMILY = {
    **{e: "text" for e in ["doc", "docx", "odt", "rtf", "txt", "html", "htm"]},
    **{e: "slides" for e in ["ppt", "pptx", "odp"]},
    **{e: "sheet" for e in ["xls", "xlsx", "ods", "csv"]},
    **{e: "image" for e in ["png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff", "svg"]},
    "pdf": "pdf",
}
# What LibreOffice saves directly, per input family, with the filter to use.
DIRECT = {
    "text": {"pdf": "pdf", "docx": "docx", "doc": "doc", "odt": "odt", "rtf": "rtf",
             "txt": "txt:Text (encoded):UTF8", "html": "html"},
    "slides": {"pdf": "pdf", "pptx": "pptx", "ppt": "ppt", "odp": "odp", "html": "html"},
    "sheet": {"pdf": "pdf", "xlsx": "xlsx", "xls": "xls", "ods": "ods",
              "csv": "csv:Text - txt - csv (StarCalc):44,34,76,1", "html": "html"},
    "image": {"pdf": "pdf"},
}
TARGETS = {"pdf", "docx", "doc", "odt", "rtf", "txt", "html", "pptx", "ppt", "odp",
           "xlsx", "xls", "ods", "csv", "png", "jpg"}
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword", "odt": "application/vnd.oasis.opendocument.text",
    "rtf": "application/rtf", "txt": "text/plain; charset=utf-8", "html": "text/html; charset=utf-8",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint", "odp": "application/vnd.oasis.opendocument.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel", "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "csv": "text/csv; charset=utf-8", "png": "image/png", "jpg": "image/jpeg", "zip": "application/zip",
}


_uno = None
_uno_lock = threading.Lock()


def _uno_server():
    """Start one LibreOffice listener and keep it running, so conversions skip the office start-up."""
    global _uno
    if _uno is None or _uno.poll() is not None:
        _uno = subprocess.Popen(["python3", "-m", "unoserver.server", "--interface", "127.0.0.1", "--port", "2003"],
                                stdout=sys.stderr, stderr=sys.stderr)
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", 2003), timeout=1).close()
                break
            except OSError:
                time.sleep(0.5)


def soffice(src: str, filt: str, outdir: str) -> str:
    """Convert src into outdir with the running LibreOffice. filt is "ext" or "ext:Filter Name:options"."""
    parts = filt.split(":", 2)
    ext = parts[0]
    out = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + "." + ext)
    kw = {}
    if len(parts) > 1:
        kw["filtername"] = parts[1]
    if len(parts) > 2:
        kw["filter_options"] = [parts[2]]
    with _uno_lock:
        for attempt in (0, 1):
            try:
                _uno_server()
                UnoClient(server="127.0.0.1", port="2003").convert(inpath=src, outpath=out, convert_to=ext, **kw)
                break
            except Exception:
                if _uno is not None:
                    _uno.kill()
                if attempt:
                    raise HTTPException(422, "The file could not be converted. It may be damaged or password-protected.")
    if not os.path.exists(out):
        raise HTTPException(422, "The file could not be converted. It may be damaged or password-protected.")
    return out


@app.on_event("startup")
def _warm():
    def go():
        with _uno_lock:  # never start two offices at once: that exceeds a 512 MB host
            _uno_server()
    threading.Thread(target=go, daemon=True).start()


def pdf_to_docx(pdf: str, out: str) -> None:
    """Rebuild a PDF as Word in a child process, so its memory (OpenCV, NumPy) is returned afterwards."""
    code = ("import sys\nfrom pdf2docx import Converter\ncv = Converter(sys.argv[1])\n"
            "cv.convert(sys.argv[2], multi_processing=False)\ncv.close()\n")
    r = subprocess.run(["python3", "-c", code, pdf, out], capture_output=True, timeout=240)
    if r.returncode != 0 or not os.path.exists(out):
        raise HTTPException(422, "This PDF could not be rebuilt as an editable document.")


def pdf_to_pptx(pdf: str, out: str) -> None:
    from pptx import Presentation
    from pptx.util import Emu
    doc = fitz.open(pdf)
    prs = Presentation()
    first = doc[0].rect
    prs.slide_width, prs.slide_height = Emu(int(first.width * 12700)), Emu(int(first.height * 12700))
    blank = prs.slide_layouts[6]
    for page in doc:
        png = page.get_pixmap(dpi=150).tobytes("png")
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(io.BytesIO(png), 0, 0, prs.slide_width, prs.slide_height)
    prs.save(out)


def pdf_to_xlsx(pdf: str, out: str) -> None:
    from openpyxl import Workbook
    doc = fitz.open(pdf)
    wb = Workbook()
    wb.remove(wb.active)
    for i, page in enumerate(doc, 1):
        ws = wb.create_sheet(f"Page {i}")
        tables = page.find_tables().tables
        if tables:
            for t in tables:
                for row in t.extract():
                    ws.append([("" if c is None else str(c)) for c in row])
                ws.append([])
        else:
            for line in page.get_text().splitlines():
                ws.append([line])
    if not wb.sheetnames:
        wb.create_sheet("Page 1")
    wb.save(out)


def pdf_to_images(pdf: str, fmt: str, work: str):
    doc = fitz.open(pdf)
    imgs = [page.get_pixmap(dpi=150).tobytes("jpeg" if fmt == "jpg" else "png") for page in doc]
    if len(imgs) == 1:
        return imgs[0], fmt
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in enumerate(imgs, 1):
            z.writestr(f"page-{n:03d}.{fmt}", b)
    return buf.getvalue(), "zip"


def convert(src: str, target: str, work: str):
    ext = os.path.splitext(src)[1].lstrip(".").lower()
    fam = FAMILY.get(ext)
    if not fam:
        raise HTTPException(415, "This file type is not supported.")
    direct = DIRECT.get(fam, {})
    if target in direct and target not in ("png", "jpg"):
        if fam == "text" and ext == target:
            return open(src, "rb").read(), target
        return open(soffice(src, direct[target], work), "rb").read(), target
    # Everything else goes through an exact PDF first.
    pdf = src if fam == "pdf" else soffice(src, "pdf", work)
    if target == "pdf":
        return open(pdf, "rb").read(), "pdf"
    if target in ("png", "jpg"):
        return pdf_to_images(pdf, target, work)
    if target == "txt":
        doc = fitz.open(pdf)
        return "\n\n".join(p.get_text() for p in doc).encode("utf-8"), "txt"
    if target in ("docx", "doc", "odt", "rtf", "html"):
        docx = os.path.join(work, "rebuilt.docx")
        pdf_to_docx(pdf, docx)
        if target == "docx":
            return open(docx, "rb").read(), "docx"
        return open(soffice(docx, DIRECT["text"][target], work), "rb").read(), target
    if target in ("pptx", "ppt", "odp"):
        pptx = os.path.join(work, "slides.pptx")
        pdf_to_pptx(pdf, pptx)
        if target == "pptx":
            return open(pptx, "rb").read(), "pptx"
        return open(soffice(pptx, target, work), "rb").read(), target
    if target in ("xlsx", "xls", "ods", "csv"):
        xlsx = os.path.join(work, "tables.xlsx")
        pdf_to_xlsx(pdf, xlsx)
        if target == "xlsx":
            return open(xlsx, "rb").read(), "xlsx"
        return open(soffice(xlsx, DIRECT["sheet"][target], work), "rb").read(), target
    raise HTTPException(400, "Unsupported output format.")


@app.get("/healthz")
def healthz():
    def mb(name):
        try:
            return round(int(open("/sys/fs/cgroup/" + name).read()) / 1048576)
        except Exception:
            return None
    return {"ok": True, "mem_mb": mb("memory.current") or mb("memory/memory.usage_in_bytes"),
            "peak_mb": mb("memory.peak") or mb("memory/memory.max_usage_in_bytes")}


@app.post("/convert")
async def convert_endpoint(request: Request, to: str, name: str,
                           x_nl_key: str = Header(default="")):
    if not KEY or x_nl_key != KEY:
        raise HTTPException(403, "forbidden")
    to = to.lower()
    if to not in TARGETS:
        raise HTTPException(400, "Unsupported output format.")
    base = os.path.basename(name).strip() or "document"
    ext = os.path.splitext(base)[1].lstrip(".").lower()
    if ext not in FAMILY:
        raise HTTPException(415, "This file type is not supported.")
    body = await request.body()
    if not body or len(body) > MAX_BYTES:
        raise HTTPException(413, "The file is empty or larger than 30 MB.")
    work = tempfile.mkdtemp(prefix="job-")
    try:
        src = os.path.join(work, "input." + ext)
        with open(src, "wb") as f:
            f.write(body)
        data, out_ext = await run_in_threadpool(convert, src, to, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return Response(content=data, media_type=MIME[out_ext],
                    headers={"X-Out-Ext": out_ext, "Cache-Control": "no-store"})
