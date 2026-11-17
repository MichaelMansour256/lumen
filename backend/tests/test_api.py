"""HTTP API tests (need FastAPI + httpx). Use the fake model manager, so they
verify routing, validation, jobs, downloads and error handling - not AI quality."""
from __future__ import annotations

import io
import time
import zipfile

import pytest
from PIL import Image

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

from .conftest import FakeModels, image_bytes  # noqa: E402

MANUAL = {"auto": False, "model": "realesr-general"}


@pytest.fixture
def public_client(settings):
    from dataclasses import replace
    cfg = replace(settings, public=True, access_key="s3cret-key", rate_uploads_per_hour=3,
                  rate_jobs_per_hour=2, max_queued_per_client=5,
                  allowed_origins=("https://lumen.vercel.app",),
                  allowed_hosts=("testserver", "*.trycloudflare.com"))
    with TestClient(create_app(cfg, models=FakeModels())) as c:
        yield c


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, models=FakeModels())) as c:
        yield c


def upload(client, *files):
    return client.post("/api/images", files=[("files", f) for f in files])


def wait(client, job_id):
    for _ in range(600):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_health_and_system(client):
    assert client.get("/api/health").json() == {"status": "ok", "auth": False}
    system = client.get("/api/system").json()
    assert system["device"]["device"] == "cpu" and system["limits"]["max_factor"] == 16
    assert {p["id"] for p in system["presets"]} >= {"portrait", "anime", "old_photo"}
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_upload_validation(client):
    res = upload(client, ("ok.png", image_bytes("PNG"), "image/png"),
                 ("bad.png", b"<script>alert(1)</script>", "image/png"),
                 ("anim.gif", image_bytes("GIF"), "image/gif"),
                 ("../../evil.tiff", image_bytes("TIFF"), "image/tiff")).json()
    assert [i["name"] for i in res["images"]] == ["ok.png", "evil.tiff"]
    assert [e["error"]["code"] for e in res["errors"]] == ["invalid_image", "unsupported_format"]
    image = res["images"][0]
    assert (image["width"], image["height"], image["format"]) == (96, 64, "png")
    assert image["analysis"]["category"] and image["recommendation"]["reasons"]
    original = client.get(image["url"])
    assert original.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(original.content)).size == (96, 64)
    assert client.get("/api/images/" + "0" * 32).status_code == 404
    assert client.get("/api/images/..%2f..%2fetc").status_code in (404, 422)


def test_enhance_download_and_batch(client):
    images = upload(client, ("a.jpg", image_bytes("JPEG"), "image/jpeg"),
                    ("b.webp", image_bytes("WEBP", 80, 80), "image/webp")).json()["images"]
    ids = [i["id"] for i in images]
    plan = client.post("/api/plan", json={"image_id": ids[0], "settings": {**MANUAL, "factor": 8},
                                          "format": "jpg", "quality": 80}).json()
    assert (plan["out_w"], plan["out_h"], plan["passes"]) == (768, 512, 2) and plan["est_file_bytes"] > 0
    res = client.post("/api/jobs", json={"image_ids": ids, "settings": {**MANUAL, "factor": 2}}).json()
    assert len(res["jobs"]) == 2 and not res["errors"]
    jobs = [wait(client, j["id"]) for j in res["jobs"]]
    assert all(j["status"] == "completed" for j in jobs)
    assert (jobs[0]["result"]["width"], jobs[0]["result"]["height"]) == (192, 128)
    listed = client.get("/api/jobs", params={"ids": ",".join(j["id"] for j in jobs)}).json()["jobs"]
    assert len(listed) == 2
    for fmt, mime in (("png", "image/png"), ("jpg", "image/jpeg"), ("webp", "image/webp")):
        r = client.get(jobs[0]["result_url"], params={"format": fmt, "quality": 80, "download": True})
        assert r.status_code == 200 and r.headers["content-type"] == mime
        assert f'a_enhanced.{fmt}' in r.headers["content-disposition"]
        assert Image.open(io.BytesIO(r.content)).size == (192, 128)
    prev = client.get(f"/api/jobs/{jobs[0]['id']}/preview")
    assert prev.headers["content-type"] == "image/webp"
    part = client.get(jobs[0]["result_url"], headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    z = client.post("/api/download/zip", json={"job_ids": [j["id"] for j in jobs], "format": "jpg"})
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert names == ["a_enhanced.jpg", "b_enhanced.jpg"]
    assert client.delete(f"/api/images/{ids[0]}").json() == {"deleted": ids[0]}
    assert client.get(jobs[0]["result_url"] or f"/api/jobs/{jobs[0]['id']}/result").status_code == 404


def test_error_responses(client):
    image = upload(client, ("a.png", image_bytes("PNG"), "image/png")).json()["images"][0]
    body = {"image_ids": [image["id"]], "settings": {**MANUAL, "scale_mode": "dimensions",
                                                     "width": 30000, "height": 30000}}
    err = client.post("/api/jobs", json=body).json()["errors"][0]["error"]
    assert err["code"] == "invalid_scale" and err["details"]["suggested_factor"] == 16
    r = client.post("/api/jobs", json={"image_ids": [image["id"]], "settings": {"sharpness": 9}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_settings"
    r = client.post("/api/jobs", json={"image_ids": [image["id"]],
                                       "settings": {"auto": False, "model": "gfpgan"}})
    assert r.json()["errors"][0]["error"]["code"] == "invalid_settings"
    r = client.post("/api/jobs", json={"image_ids": [image["id"]],
                                       "settings": {"auto": False, "model": "realesrgan-x4plus"}})
    assert r.json()["errors"][0]["error"]["code"] == "model_unavailable"
    assert client.post("/api/jobs", json={"image_ids": ["nope"]}).status_code == 400
    assert client.get("/api/jobs/" + "f" * 32).status_code == 404
    assert client.get("/api/jobs/" + "f" * 32 + "/result").status_code == 404
    assert client.post("/api/jobs/" + "f" * 32 + "/retry").status_code == 404
    assert client.post("/api/plan", json={"image_id": "x"}).status_code == 422


def test_public_mode(public_client):
    c = public_client
    key = {"X-Access-Key": "s3cret-key"}
    assert c.get("/api/health").json() == {"status": "ok", "auth": True}      # open
    r = c.get("/api/system")
    assert r.status_code == 401 and r.json()["error"]["code"] == "auth_required"
    assert c.get("/api/system", headers={"X-Access-Key": "wrong"}).status_code == 401
    assert c.get("/api/system", headers=key).json()["public"] is True
    assert c.get("/docs").status_code == 404                                  # docs hidden
    assert c.get("/api/health", headers={"host": "abc-def.trycloudflare.com"}).status_code == 200
    pre = c.options("/api/system", headers={"Origin": "https://lumen.vercel.app",
                                            "Access-Control-Request-Method": "GET",
                                            "Access-Control-Request-Headers": "x-access-key"})
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "https://lumen.vercel.app"
    bad = c.options("/api/system", headers={"Origin": "https://evil.example",
                                            "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    # rate limits are per visitor (CF-Connecting-IP)
    alice = {**key, "CF-Connecting-IP": "203.0.113.5"}
    files = [("files", ("a.png", image_bytes("PNG"), "image/png"))] * 2
    ids = [i["id"] for i in c.post("/api/images", files=files, headers=alice).json()["images"]]
    r = c.post("/api/images", files=files, headers=alice)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    bob = {**key, "CF-Connecting-IP": "198.51.100.7"}
    assert c.post("/api/images", files=files, headers=bob).status_code == 200
    body = {"image_ids": ids, "settings": {**MANUAL, "factor": 2}}
    assert len(c.post("/api/jobs", json=body, headers=alice).json()["jobs"]) == 2
    errs = c.post("/api/jobs", json=body, headers=alice).json()["errors"]
    assert errs[0]["error"]["code"] == "rate_limited"
