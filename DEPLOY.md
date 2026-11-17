# Put Lumen online (free): Vercel + your PC

The website runs on **Vercel** (free). The AI work still runs on **your PC and its GPU**, reached
through a free **Cloudflare quick tunnel**. Visitors only get in with the share link, which holds an
access key. The site works only while your PC is on and `start_public.bat` is running.

## 1. Deploy the frontend to Vercel (once)

Option A - no Git needed (Node.js is already installed by setup.bat):

```bat
cd frontend
npx vercel login
npx vercel --prod
```

Accept the defaults (it detects Next.js). Note the address it prints, e.g. `https://lumen-abc.vercel.app`.

Option B - from GitHub: push this folder to a repository, then in Vercel choose
**Add New > Project**, import it and set **Root Directory** to `frontend`.

No environment variables are needed: the share link tells the site which server to use.

## 2. Start the public server (each time)

Double-click **`start_public.bat`**:

1. The first time, it offers to install `cloudflared` (via winget) and asks for your Vercel address.
   It writes `backend\.env.public` with a random access key and stricter limits.
2. It starts the API in public mode (separate window), opens the tunnel and prints a **share link**
   like `https://lumen-abc.vercel.app/#api=...&key=...`. The link is copied to the clipboard and
   saved in `logs\share_link.txt`.
3. Open or send that link. The site stores the server and key and removes them from the address bar.

The quick-tunnel address changes on every restart, so a new share link is made each time.
To go offline, close the two windows.

## Safety defaults (`backend\.env.public`)

| Setting | Public default |
|---|---|
| Access key | random, required on every request |
| Upload size / files per upload | 15 MB / 5 |
| Max input / output | 16 MP / 64 MP, 12,000 px per side |
| Per visitor per hour | 30 uploads, 20 enhancements |
| Queue | 3 jobs per visitor, 10 in total |
| Files kept | 2 hours (stored in `backend\data_public`) |
| API docs page | off |

To revoke all links, change `ENHANCER_ACCESS_KEY` and restart. Uploaded images pass through
Cloudflare and are stored on your PC until they expire - tell people that before they upload.

## Permanent address (optional)

With a domain on Cloudflare you can create a *named* tunnel (`cloudflared tunnel create lumen`) with
a fixed hostname. Add that hostname to `ENHANCER_ALLOWED_HOSTS`, then share
`https://your-site/#api=https://api.yourdomain.com&key=...` once.

## Troubleshooting

| Problem | Fix |
|---|---|
| Site says "Access key needed" | Open the full share link again, or paste the key in the dialog. |
| Site says it cannot reach the server | The PC, the API window or the tunnel window is closed, or the link is from an old session. |
| Browser console shows a CORS error | `LUMEN_SITE_URL` / `ENHANCER_ALLOWED_ORIGINS` in `backend\.env.public` must match the Vercel address exactly (https, no trailing slash). Restart afterwards. |
| "Invalid host header" | The tunnel host must match `ENHANCER_ALLOWED_HOSTS` (default allows `*.trycloudflare.com`). |
| Tunnel does not start | See `logs\tunnel.log`. |
| API window says the port is in use | Close the local app (`start.bat`) first; both use port 8000. |
