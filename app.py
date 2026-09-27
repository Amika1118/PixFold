"""
PixFold — FastAPI backend for the custom index.html UI.
Serves the HTML and exposes two API endpoints:

    POST /api/pdf-to-images    (PDF  -> WebP/JPEG/PNG, zipped if multi-page)
    POST /api/images-to-pdf    (images/zip -> PDF, zipped if batching)

All work happens server-side via PIL + PyMuPDF so it's consistent
across browsers and doesn't hit browser memory limits.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image
from starlette.background import BackgroundTask

try:
    import fitz  # PyMuPDF
    HAVE_FITZ = True
except ImportError:                                    # pragma: no cover
    HAVE_FITZ = False

Image.MAX_IMAGE_PIXELS = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(BASE_DIR, "index.html")

VALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
    ".tiff", ".tif", ".ppm", ".pgm",
)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB per file

app = FastAPI(title="PixFold", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ────────────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────────────

def natural_sort_key(s: str):
    """img2 < img10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _extract_zip(zip_path: str, dest: str):
    """Safe zip extraction (no path traversal). Returns image paths."""
    os.makedirs(dest, exist_ok=True)
    found = []
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            norm = os.path.normpath(member)
            if norm.startswith("..") or os.path.isabs(norm):
                continue
            target = os.path.join(dest, norm)
            if member.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
            with z.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if member.lower().endswith(VALID_EXTS):
                found.append(target)
    return found


async def _save_upload(upload: UploadFile, dest_dir: str) -> str:
    """Stream an UploadFile to disk, returning the saved path."""
    name = os.path.basename(upload.filename or "") or "upload.bin"
    base, ext = os.path.splitext(name)
    path = os.path.join(dest_dir, name)
    i = 1
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"{base}_{i}{ext}")
        i += 1

    total = 0
    with open(path, "wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                out.close()
                try: os.remove(path)
                except OSError: pass
                raise HTTPException(413, f"File too large: {name}")
            out.write(chunk)
    return path


def _convert_webp(src: str, dst: str, quality: int):
    """Image → WebP. Returns (ok, error_message)."""
    try:
        with Image.open(src) as img:
            img.verify()
        with Image.open(src) as img:
            if img.mode in ("RGBA", "LA"):
                img = img.convert("RGBA")
            elif img.mode == "P":
                img = img.convert("RGBA" if "transparency" in img.info else "RGB")
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.save(dst, "WEBP", quality=int(quality), method=6)
        return True, None
    except Exception as e:
        if os.path.exists(dst):
            try: os.remove(dst)
            except OSError: pass
        return False, str(e)


def _build_pdf(webp_paths, out_pdf: str):
    """Save a list of images as a single PDF."""
    imgs = []
    try:
        for p in webp_paths:
            try:
                im = Image.open(p)
                if im.mode == "RGBA":
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
                imgs.append(im)
            except Exception:
                continue
        if not imgs:
            return False, "No valid images in batch"
        imgs[0].save(out_pdf, save_all=True, append_images=imgs[1:], optimize=True)
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        for im in imgs:
            try: im.close()
            except Exception: pass


# ────────────────────────────────────────────────────────────────────────
# routes
# ────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    if not os.path.exists(INDEX_HTML):
        return HTMLResponse("<h1>index.html not found next to app.py</h1>", status_code=500)
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/healthz")
async def healthz():
    return {"ok": True, "pdf2img": HAVE_FITZ}


@app.post("/api/pdf-to-images")
async def pdf_to_images(
    file: UploadFile = File(...),
    dpi: int = Form(150),
    fmt: str = Form("webp"),
    quality: float = Form(0.85),
):
    if not HAVE_FITZ:
        raise HTTPException(500, "PyMuPDF not available on the server")

    dpi = max(36, min(600, int(dpi)))
    quality = max(0.1, min(1.0, float(quality)))
    fmt = (fmt or "webp").lower()
    ext = {"webp": "webp", "jpeg": "jpg", "jpg": "jpg", "png": "png"}.get(fmt, "webp")
    media = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png"}[ext]
    q = int(quality * 100)

    work = tempfile.mkdtemp(prefix="pdf2img_")
    ok = False
    try:
        pdf_path = await _save_upload(file, work)
        base = os.path.splitext(os.path.basename(pdf_path))[0]

        doc = fitz.open(pdf_path)
        if doc.needs_pass:
            doc.close()
            raise HTTPException(400, "PDF is password-protected")

        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        outputs = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            out = os.path.join(work, f"{base}-p{i + 1:03d}.{ext}")
            if ext == "webp":
                im.save(out, "WEBP", quality=q, method=6)
            elif ext == "jpg":
                im.save(out, "JPEG", quality=q, optimize=True, progressive=True)
            else:
                im.save(out, "PNG", optimize=True)
            im.close()
            outputs.append(out)
        doc.close()

        if not outputs:
            raise HTTPException(400, "PDF has no pages")

        # Single page → single file
        if len(outputs) == 1:
            ok = True
            return FileResponse(
                outputs[0],
                media_type=media,
                filename=os.path.basename(outputs[0]),
                background=BackgroundTask(shutil.rmtree, work, True),
            )

        # Multiple pages → zip
        zip_path = os.path.join(work, f"{base}-images.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
            for o in outputs:
                z.write(o, os.path.basename(o))

        ok = True
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{base}-images.zip",
            background=BackgroundTask(shutil.rmtree, work, True),
        )
    finally:
        if not ok:
            shutil.rmtree(work, ignore_errors=True)


@app.post("/api/images-to-pdf")
async def images_to_pdf(
    files: list[UploadFile] = File(...),
    batch_size: int = Form(500),
    num_threads: int = Form(5),
    quality: float = Form(0.95),
    split: bool = Form(True),
    include_webp_zip: bool = Form(False),
):
    if not files:
        raise HTTPException(400, "No files uploaded")

    batch_size  = max(1, min(5000, int(batch_size)))
    num_threads = max(1, min(16, int(num_threads)))
    quality     = max(0.1, min(1.0, float(quality)))
    q = int(quality * 100)

    work = tempfile.mkdtemp(prefix="img2pdf_")
    ok = False
    try:
        upload_dir = os.path.join(work, "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        img_paths = []
        for uf in files:
            p = await _save_upload(uf, upload_dir)
            low = p.lower()
            if low.endswith(".zip"):
                img_paths.extend(_extract_zip(p, os.path.join(work, "unzipped")))
            elif low.endswith(VALID_EXTS):
                img_paths.append(p)

        if not img_paths:
            raise HTTPException(400, "No valid images in the upload")

        # NOTE: order is preserved from the upload — the frontend already
        # sorted them and posted in that exact order.
        webp_dir = os.path.join(work, "webp")
        os.makedirs(webp_dir, exist_ok=True)

        tasks, seen = [], set()
        for src in img_paths:
            base = os.path.splitext(os.path.basename(src))[0]
            cand = os.path.join(webp_dir, base + ".webp")
            i = 1
            while cand in seen or os.path.exists(cand):
                cand = os.path.join(webp_dir, f"{base}_{i}.webp")
                i += 1
            seen.add(cand)
            tasks.append((src, cand))

        results = [None] * len(tasks)
        with ThreadPoolExecutor(max_workers=num_threads) as ex:
            futs = {ex.submit(_convert_webp, s, d, q): i
                    for i, (s, d) in enumerate(tasks)}
            for fut in as_completed(futs):
                idx = futs[fut]
                good, _ = fut.result()
                if good:
                    results[idx] = tasks[idx][1]

        webp_paths = [r for r in results if r]
        if not webp_paths:
            raise HTTPException(400, "All images failed to convert")

        if split:
            chunks = [webp_paths[i:i + batch_size]
                      for i in range(0, len(webp_paths), batch_size)]
        else:
            chunks = [webp_paths]

        pdf_paths = []
        for i, chunk in enumerate(chunks):
            name = f"part_{i + 1:03d}.pdf" if len(chunks) > 1 else "images.pdf"
            out = os.path.join(work, name)
            good, _ = _build_pdf(chunk, out)
            if good:
                pdf_paths.append(out)

        if not pdf_paths:
            raise HTTPException(500, "Could not build any PDF")

        # Single PDF, no webp copies → direct download
        if len(pdf_paths) == 1 and not include_webp_zip:
            ok = True
            return FileResponse(
                pdf_paths[0],
                media_type="application/pdf",
                filename="images.pdf",
                background=BackgroundTask(shutil.rmtree, work, True),
            )

        # Otherwise bundle everything
        zip_path = os.path.join(work, "images-pdfs.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in pdf_paths:
                z.write(p, os.path.basename(p))
            if include_webp_zip:
                for p in webp_paths:
                    z.write(p, "webp/" + os.path.basename(p))

        ok = True
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="images-pdfs.zip",
            background=BackgroundTask(shutil.rmtree, work, True),
        )
    finally:
        if not ok:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7860, log_level="info")