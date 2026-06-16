# MyCRWL - AI Website Intelligence

MyCRWL is a zero-cost, local-first Chrome Extension and FastAPI backend for crawling, analyzing, and reporting on websites with Google Gemini.

## What It Does

- Detects the current Chrome tab URL.
- Crawls the homepage plus important internal pages.
- Extracts content, CTAs, emails, phones, social links, images, logo, favicon, theme colors, and technology clues.
- Uses Gemini to produce structured business, brand, SEO, UX, trust, and competitor intelligence.
- Generates a polished downloadable PDF report.

## Project Structure

```text
project/
  extension/
    src/
      popup/
      background/
      content/
      shared/
    public/
    assets/
    manifest.json
  backend/
    app/
      ai/
      crawler/
      pdf/
      routes/
      utils/
      main.py
```

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
copy env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Add at least one free-tier AI key to `backend/.env`:

```env
GEMINI_API_KEY=your_key_here
# Optional. Use a model returned by `python scripts/list_models.py`.
GEMINI_MODEL=gemini-2.0-flash

HUGGINGFACE_API_KEY=your_key_here
# Small instruct model that works better on free/shared inference.
HUGGINGFACE_MODEL=google/gemma-2-2b-it

# Keep this false if you want only high-confidence on-site owner/contact data.
ALLOW_EXTERNAL_CONTACT_ENRICHMENT=false
```

The extension now supports `Auto` mode, which tries Gemini first and then Hugging Face before falling back to deterministic local analysis. The response includes `ai_source` so you can verify whether AI was actually used.

## Extension Setup

```bash
cd extension
npm install
npm run build
```

Open Chrome:

1. Go to `chrome://extensions`.
2. Enable Developer Mode.
3. Click Load unpacked.
4. Select `extension/dist`.

The popup expects the backend at `http://127.0.0.1:8000`. You can change this in the popup settings field.

In the popup, leave `AI Model` on `Auto (Gemini → Hugging Face)` unless you want to force one provider.

## API

- `GET /health`
- `POST /analyze`
- `POST /generate-pdf`

Example:

```bash
curl -X POST http://127.0.0.1:8000/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://example.com\"}"
```

## Zero-Cost Notes

- Runs locally.
- Uses free/open-source packages.
- Uses Google Gemini API and Hugging Face Inference free-tier endpoints, with automatic provider fallback.
- PDF files and screenshots are stored in `backend/storage`.
