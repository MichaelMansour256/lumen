# Project status

Last update: 2026-11-17

## Phases
- [x] 1 Architecture
- [x] 2 Frontend workspace (upload, queue, settings, compare viewer, downloads)
- [x] 3 Backend (FastAPI, validation, storage, SQLite, job queue)
- [x] 4 AI upscaling (Real-ESRGAN via spandrel, tiled, staged 8x/16x)
- [x] 5 Restoration (GFPGAN/CodeFormer faces, classical clean-up and colour)
- [x] 6 Comparison editor, manual controls, batch + ZIP
- [x] 7 GPU memory management (one model on GPU, FP16, OOM tile back-off, CPU fallback)
- [ ] 8 Verification on the Windows machine  <-- NEXT

## Verified on the Windows PC (2026-11-17, run_tests.bat)
- setup.bat completed; models installed (SwinIR / CodeFormer optional, not downloaded)
- 47 backend tests pass: real Real-ESRGAN general / x4plus / anime at 2x and 4x, denoise blending,
  staged tiled 8x, CPU fallback, HTTP API, pipeline
- Frontend `next build` succeeds (Next.js 15.5.29)

## Open issues
- setup.bat missed the NVIDIA GPU (nvidia-smi not on PATH) and installed CPU PyTorch. Fixed:
  detection now also uses Win32_VideoController and replaces a CPU build. Re-run setup.bat.
- GPU path (CUDA, FP16, VRAM tiles) not yet verified
- Face restoration test skipped: needs backend/tests/assets/face.jpg
- UI not yet checked in a browser

## Public deployment (added 2026-11-17, not yet run on Windows)
- Backend: optional access key (X-Access-Key), per-visitor rate limits, queue caps, docs off,
  CORS for the Vercel site, *.trycloudflare.com host; settings in backend/.env.public
- Frontend: server URL + key set at runtime (Connect dialog, share link #api=&key=),
  images loaded with the key
- start_public.bat + backend/scripts/tunnel.ps1 (cloudflared quick tunnel), DEPLOY.md
- Tested: 35 backend tests here incl. public-mode API test (runs on Windows via run_tests.bat)

## Findings 2026-11-17 15:10
- This PC has NO NVIDIA GPU: setup log lists "Radeon(TM) R7 M465" + "Intel(R) HD Graphics 620".
  CPU PyTorch is correct here; enhancements take ~3 min each on CPU.
- Vercel project "lumen" deployed. Opening it without a share link fell back to 127.0.0.1:8000
  and showed "backend offline". Fixed: online copy now asks for the share link (needs redeploy).

## Next task
Re-run setup.bat, then run_tests.bat; confirm logs/environment.txt says `cuda True`.

## Commands
- Install: `setup.bat`   Start: `start.bat`   Tests: `run_tests.bat`
- Backend tests only: `cd backend && .venv\Scripts\python.exe -m pytest tests -v -s`
