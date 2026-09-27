# 📸 PixFold - PDF ⇄ Images Converter

> **A fast, privacy-first media converter that runs 100% locally in your browser. Convert PDFs to crisp images, or bundle image collections into custom PDFs without server uploads.**

---

## ⚡ Quick Start

1. **Download** the `index.html` file.
2. **Double-click** `index.html` to open it in any modern web browser.
3. **Start converting!** No installation, database, or sign-ups required.

> **Local Server Note:** If external CDN scripts fail to load over the `file://` protocol, serve the project using Python:
> ```bash
> python -m http.server 8000
> 
> ```
> 
> 
> Then navigate to `http://localhost:8000`.

---

## 🚀 Key Features

### 📄 PDF → Images

* 🎯 **Adjustable Resolution:** Choose standard DPI presets to balance quality and file size:
* **72 DPI** - Drafts & quick screen reading
* **150 DPI** - General purpose *(Default)*
* **300 DPI** - High-quality print output
* **400 DPI** - Archival & detailed document scans


* 🎨 **Flexible Export Formats:** Export to **WebP** *(smallest size)*, **JPEG** *(universal compatibility)*, or **PNG** *(lossless)*.
* 🎚️ **Quality Control:** Granular encoding quality slider ($0.40$ – $1.00$) for WebP and JPEG exports.
* 📦 **Automatic Archiving:** Multi-page PDFs automatically convert and download as an ordered `.zip` file.

---

### 🖼️ Images → PDF

* 📂 **Universal Input:** Accepts any browser-supported image format (JPEG, PNG, WebP, AVIF, GIF, BMP, TIFF, SVG).
* 🔢 **Smart Natural Sorting:** Automatically handles mixed patterns like `1.png`, `2.png`, `10.png` seamlessly.
* 🔀 **6 Sorting Modes:**
* **Smart (Natural):** Intuitive numerical sorting.
* **Filename A → Z:** Strict alphabetical order.
* **Date Modified:** Sort by oldest or newest first.
* **File Size:** Order by smallest file size.
* **Upload Order:** Keep the selection sequence.
* **Manual:** Interactive drag-and-drop page ordering.


* 📐 **Page Layout Controls:** Match original image dimensions or fit to standard **A4** or **Letter** sizes with configurable margin padding (in points).
* 🧼 **Transparency Flattening:** Optional white-background canvas flattening to reduce file sizes on transparent PNGs/WebPs.

---

### 🛡️ Privacy & Security

* 🔒 **100% Local Execution:** All processing happens in-memory inside your browser client. Your files are **never** uploaded to an external server.
* 🚫 **Zero Tracking:** No analytics, telemetry, trackers, or cookies.

---

## 🧠 Natural Sorting Engine

Standard alphabetical sorting often misorders numbered files. PixFold parses filenames into alternating digit and string chunks to preserve human-intended numeric order:

| Source Files | Standard Alphabetical Order | PixFold Natural Order |
| --- | --- | --- |
| `1.png`, `2.png`, `10.png`, `20.png` | `1.png`, **`10.png`**, `2.png`, `20.png` ❌ | `1.png`, `2.png`, **`10.png`**, `20.png` ✅ |
| `scan_001.png`, `scan_010.png` | `scan_010.png`, `scan_001.png` ❌ | `scan_001.png`, `scan_010.png` ✅ |
| `ch1-p1.png`, `ch1-p10.png`, `ch2-p1.png` | `ch1-p10.png`, `ch1-p1.png`, `ch2-p1.png` ❌ | `ch1-p1.png`, `ch1-p10.png`, `ch2-p1.png` ✅ |

---

## 🛠️ Deployment Options

### Single-File Client (Default)

Deploy to any static web host by serving `index.html`:

* **GitHub Pages:** Push `index.html` to a repository $\rightarrow$ Settings $\rightarrow$ Pages $\rightarrow$ Deploy from Branch.
* **Netlify / Cloudflare Pages / Vercel:** Drag and drop the single folder or connect your web repository.

### Optional FastAPI Server Variant

For backend processing or containerized setups:

```
├── index.html        # Frontend client interface
├── app.py            # FastAPI processing API
├── requirements.txt  # Python environment dependencies
└── Dockerfile        # Container specification for deployment

```

---

## 🛠️ Technical Specifications & Limits

* **Browser Compatibility:** Chrome/Edge 90+, Firefox 90+, Safari 15+.
* **Memory Management:** Operates smoothly with standard client RAM. For large workloads (200+ PDF pages at high DPI), lower the resolution settings to avoid browser memory boundaries.
* **Encrypted Documents:** Password-protected PDFs must be decrypted prior to processing.
* **Dependencies:** Uses public CDN distributions of **PDF.js**, **pdf-lib**, and **JSZip**. For offline environments, host these libraries locally and update script tags accordingly.

---

## 📄 License

Distributed under the **MIT License**.

Third-party core libraries retain their respective open-source licenses:

* **PDF.js** (Apache 2.0)
* **pdf-lib** (MIT)
* **JSZip** (MIT / GPLv3)