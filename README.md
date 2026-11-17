# Lumen - AI Image Enhancer

A local, free AI image enhancer: Real-ESRGAN upscaling (1x-16x and custom sizes), GFPGAN face
restoration, clean-up and colour tools, batch processing and a before/after comparison editor.
Everything runs on your own computer - images are never sent anywhere.

- **Frontend:** Next.js 15, React 19, TypeScript, Tailwind CSS, shadcn-style components (Radix), Lucide
- **Backend:** Python, FastAPI, Pydantic, SQLite, local file storage
- **AI:** PyTorch + [spandrel](https://github.com/chaiNNer-org/spandrel) model loader, OpenCV, Pillow

## Install (Windows 11)

Requirements: **Python 3.10-3.13**, **Node.js LTS**, and for GPU speed an NVIDIA driver.
About 6 GB of free disk space (PyTorch with CUDA is ~2.5 GB, models ~425 MB).

1. Double-click **`setup.bat`**. It creates `backend\.venv`, installs PyTorch (CUDA build when
   `nvidia-smi` works, otherwise CPU), installs the backend and frontend packages and downloads
   the models. Progress is written to `logs\setup.log`.
2. Double-click **`start.bat`**. It opens the API (port 8000), the UI (port 3000) and your browser
   at <http://localhost:3000>.
3. Optional: **`run_tests.bat`** runs the backend tests (including real model inference on tiny
   images) and a production build of the frontend. Results go to `logs\`.

To put it online for free (frontend on Vercel, AI on your PC through a Cloudflare tunnel, protected
by an access key), see **[DEPLOY.md](DEPLOY.md)** and use **`start_public.bat`**.

Manual start, if you prefer two terminals:

```bat
cd backend  && .venv\Scripts\python.exe run.py
cd frontend && npm run dev
```

## Using it

Drop, browse or paste (Ctrl+V) one or more JPG / PNG / WebP / TIFF images. Each image is analysed
on upload. With **Auto enhance** on, the app chooses the model and corrections per image and shows
why; change any control (or pick a **Mode**) to take over manually. Choose a size (1x-16x, or
custom width x height / percentage with aspect lock), press **Enhance** (or **All** for the whole
queue), compare with the slider (wheel = zoom, drag = pan, double-click = 100%), then download as
PNG / JPG / WebP or everything as a ZIP.

## Models

Downloaded by `setup.bat` from the official release pages only (`backend\app\ai\registry.py`):

| Model | Used for | Size | Licence |
|---|---|---|---|
| Real-ESRGAN General x4 v3 (+ weak-denoise weights) | default fast upscaler, adjustable denoise | 2 x 5 MB | BSD-3-Clause |
| Real-ESRGAN x4plus | higher-quality photo upscaling | 64 MB | BSD-3-Clause |
| Real-ESRGAN x4plus Anime 6B | anime / illustration | 17 MB | BSD-3-Clause |
| GFPGAN v1.4 | face restoration | 332 MB | Apache-2.0 |
| YuNet (OpenCV Zoo) | face + landmark detection | 0.2 MB | MIT |
| SwinIR-M x4 real-world *(optional)* | slow transformer upscaler | 64 MB | Apache-2.0 |
| CodeFormer *(optional)* | alternative face restoration | 360 MB | S-Lab 1.0, **non-commercial** |

```bat
cd backend
.venv\Scripts\python.exe scripts\download_models.py --list      :: status
.venv\Scripts\python.exe scripts\download_models.py --only swinir-real
.venv\Scripts\python.exe scripts\download_models.py --verify    :: re-check SHA-256
:: CodeFormer also needs its architecture package:
.venv\Scripts\pip install -r requirements-optional.txt
.venv\Scripts\python.exe scripts\download_models.py --only codeformer
```

Weights are loaded through spandrel / `torch.load(weights_only=True)`, which refuse to unpickle
arbitrary code. A SHA-256 of each file is recorded at download time (`models\checksums.json`).

## How it works

```
frontend/   app/ (single workspace page)  components/  hooks/use-enhancer.ts  lib/api.ts
backend/
  app/routes/      thin FastAPI endpoints (/api/images, /api/plan, /api/jobs, /api/download/zip, /api/system)
  app/services/    storage abstraction, SQLite metadata, safe image decode/encode, job queue
  app/pipeline/    settings validation, scaling engine, analysis, presets, classical ops, enhance.py
  app/ai/          device detection, model registry + downloader, model manager, upscaler, face restore, tiling
  tests/           test_pipeline.py (no torch needed), test_api.py, test_models.py (real models)
```

- **Jobs** run on one background worker thread (`services/jobs.py`), so the API never blocks.
  The queue sits behind a small interface, so Redis/RQ can replace it later without touching routes.
- **Scaling engine** (`pipeline/scaling.py`): resolves the requested size, enforces limits and plans
  staged 4x passes (8x and 16x use two). Requests above the limits are refused with a concrete
  smaller alternative - the app never silently returns a smaller image.
- **Tiled inference** (`ai/tiling.py`): padded tiles, only the centre of each is kept, written straight
  into one uint8 buffer. Tile size follows free VRAM and halves automatically on out-of-memory.
- **Model manager**: one model on the GPU at a time, FP16 where supported (automatic FP32 fallback),
  up to two models parked in RAM, CPU fallback when CUDA is unavailable.
- **API docs:** <http://127.0.0.1:8000/docs> while the backend runs.

Settings live in `backend\.env` (copy `backend\.env.example`): limits, tile size, device, file TTL.
Uploads and results are stored in `backend\data\files` and deleted after 24 hours, when you remove
an image, or when you press Clear.

## What is and is not AI

- AI: upscaling (Real-ESRGAN / SwinIR), face restoration (GFPGAN / CodeFormer), face detection (YuNet).
- Classical image processing (OpenCV): non-local-means denoise for models without built-in denoise,
  JPEG artifact reduction, Richardson-Lucy deblur (mild focus blur only), colour / tone controls,
  low-light (gamma + CLAHE), fade correction, local contrast and sharpening.
- The analyser measures sharpness, noise, JPEG blocking, exposure, contrast and colour cast, and
  estimates a category (photo / portrait / plain-background subject / illustration) from colour
  statistics and detected faces. It does **not** recognise scenes: Landscape, Product and Anime are
  manual modes. Illustration and Anime use the same model with different settings.
- Not included: colourising black-and-white photos, scratch/tear inpainting, strong motion deblur.

## Limits on an RTX 3050 (4 GB) / 16 GB RAM

Default caps: 40 MP input, 150 MP or 16,384 px per side output, 50 MB per upload. A 16x upscale is
therefore only possible for small sources (about 760 x 760 or less); larger sources are offered the
biggest size that fits. WebP downloads are limited to 16,383 px per side by the format. Faces larger
than 512 px in the output are restored at 512 px and scaled up, so they can look softer than the
surroundings at very high output sizes - lower the face strength in that case.

## Troubleshooting

| Problem | Fix |
|---|---|
| Header shows "CPU mode" although you have an NVIDIA GPU | Update the NVIDIA driver, then delete `backend\.venv` and run `setup.bat` again. Check `logs\environment.txt` - it must say `cuda True`. |
| "Backend offline" in the UI | The API window was closed or crashed; run `start.bat`. Errors are in `backend\data\logs\backend.log`. |
| "AI model unavailable" | A model file is missing: run `setup.bat` again or `download_models.py --list`. |
| "Not enough GPU memory" | Close other GPU apps, use the fast General model or a smaller size, set `ENHANCER_TILE_SIZE=128` in `backend\.env`, or use "Retry on CPU". |
| A model fails to load | Delete that file in `backend\models` and download it again (`--verify` shows mismatches). |
| `setup.bat` cannot find Python | Install Python 3.12 from python.org with "Add python.exe to PATH". |
| Port 3000 or 8000 already in use | Close the other program, or change `ENHANCER_PORT` and `NEXT_PUBLIC_API_URL` (see the `.env.example` files). |
| `npm install` fails | Install Node.js LTS (20 or newer) and run `setup.bat` again. |
