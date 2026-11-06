# -*- coding: utf-8 -*-
"""Runs ON the Colab VM. Started in the background by start.py; progress goes to /content/ltxjob/status.json.

One batch = /content/ltxjob/manifest.json (written by the local ltxrun.py). Steps:
  1 install (skipped when the marker exists): ComfyUI at a pinned commit; Lightricks' own ComfyUI-LTXVideo node
    pack at a pinned commit (only the text-to-audio job uses it; videos run on core ComfyUI nodes).
  2 models: LTX-2.5 (Lightricks) at a pinned Hugging Face revision
  3 start ComfyUI on 127.0.0.1:8188 (private to the VM)
  4 every job in order -> /content/ltxjob/out/<id>.mp4 (video) or <id>.wav (tts), graphs from ltx_graph.py
    sent straight to /prompt
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ltx_graph  # noqa: E402

JOB = Path("/content/ltxjob")
OUT = JOB / "out"
STATUS = JOB / "status.json"
COMFY = Path("/content/ComfyUI")
COMFY_URL = "http://127.0.0.1:8188"
MARK = Path("/content/.ltxskill_setup_v2")
STATE = {"stage": "starting", "log": [], "jobs": {}, "done": False, "error": None, "started": time.time()}

# Pinned on 2026-11-06. Change these only on purpose, after reading what changed upstream.
COMFY_REPO = "https://github.com/Comfy-Org/ComfyUI.git"
COMFY_COMMIT = "63e5bf594339f676b4b15e072529873e3448409e"
LTXNODES_REPO = "https://github.com/Lightricks/ComfyUI-LTXVideo.git"
LTXNODES_COMMIT = "220e1d45aa0469f518e982102fca4dca92a61862"
LTXNODES = COMFY / "custom_nodes" / "ComfyUI-LTXVideo"
LTX_REPO = "Lightricks/LTX-2.5"
LTX_REVISION = "49b093a39c19169a8a81721dcc541e07e945232f"
MODELS = [  # (file in the LTX-2.5 repo, ComfyUI models/ subfolder)
    ("diffusion_models/" + ltx_graph.MODELS["unet"], "diffusion_models"),
    ("text_encoders/" + ltx_graph.MODELS["clip"], "text_encoders"),
    ("vae/" + ltx_graph.MODELS["vae"], "vae"),
    ("vae/" + ltx_graph.MODELS["audio_vae"], "vae"),
    ("latent_upscale_models/" + ltx_graph.MODELS["upscaler"], "latent_upscale_models"),
]
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,60}")


# ---------------------------------------------------------------- status
def save():
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATUS)


def log(msg, stage=None):
    if stage:
        STATE["stage"] = stage
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    STATE["log"] = (STATE["log"] + [line])[-60:]
    save()


def sh(args, **kw):
    subprocess.run(args, check=True, **kw)


# ---------------------------------------------------------------- 1 install
def fetch_commit(repo, commit, dest):
    """Fetch exactly one commit, never a moving branch, and check it."""
    if not dest.exists():
        sh(["git", "init", "-q", str(dest)])
        sh(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", repo, commit])
        sh(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"])
    head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != commit:
        raise RuntimeError(f"{dest.name} is at {head}, expected {commit}")


def install():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("no GPU on this runtime")
    cap = torch.cuda.get_device_capability(0)
    if cap < (8, 0):
        raise RuntimeError(f"GPU capability {cap} cannot run the int8 LTX-2.5 weights (T4 is too old); use L4 or G4")
    if MARK.exists():
        log("install: already done on this runtime")
        return
    log(f"install: GPU {torch.cuda.get_device_name(0)}, capability {cap}", "install")
    fetch_commit(COMFY_REPO, COMFY_COMMIT, COMFY)
    fetch_commit(LTXNODES_REPO, LTXNODES_COMMIT, LTXNODES)
    if not (torch.version.cuda or "").startswith("13"):
        log("install: CUDA 13 PyTorch (the int8 ConvRot weights need it)")
        sh([sys.executable, "-m", "pip", "install", "-q", "torch", "torchvision", "torchaudio",
            "--index-url", "https://download.pytorch.org/whl/cu130"])
    sh([sys.executable, "-m", "pip", "install", "-q", "-r", str(COMFY / "requirements.txt"),
        "-r", str(LTXNODES / "requirements.txt"), "huggingface_hub", "hf_xet"])
    MARK.write_text(time.ctime())
    log("install: done")


# ---------------------------------------------------------------- 2 models
def download():
    from huggingface_hub import hf_hub_download
    for name, folder in MODELS:
        target = COMFY / "models" / folder / Path(name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            got = Path(hf_hub_download(repo_id=LTX_REPO, filename=name, revision=LTX_REVISION, local_dir="/content/hf"))
            shutil.move(str(got), str(target))
        log(f"model ready: {target.name} ({target.stat().st_size / 2**30:.1f} GiB)")


# ---------------------------------------------------------------- 3 server
def start_comfy():
    try:
        urllib.request.urlopen(COMFY_URL + "/system_stats", timeout=2)
        log("ComfyUI already running")
        return
    except Exception:
        pass
    subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188"], cwd=str(COMFY),
                     stdout=open("/content/comfyui.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(180):
        try:
            urllib.request.urlopen(COMFY_URL + "/system_stats", timeout=2)
            log("ComfyUI started")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("ComfyUI did not start:\n" + Path("/content/comfyui.log").read_text(errors="ignore")[-2000:])


# ---------------------------------------------------------------- 4 jobs
def call(path, body=None, timeout=120):
    req = urllib.request.Request(COMFY_URL + path, headers={"Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path} -> {e.code}: {e.read().decode('utf-8', 'replace')[:1500]}")
    return json.loads(raw) if raw.strip() else {}


def inside(base, rel):
    """A path from the manifest, kept inside base (no absolute paths, no ..)."""
    p = (base / rel).resolve()
    if base.resolve() not in p.parents:
        raise RuntimeError(f"path outside the job folder: {rel}")
    return p


def source_file(ref):
    """'@id' = an earlier job's output in this batch; anything else = a file under inputs/."""
    if ref.startswith("@"):
        st = STATE["jobs"].get(ref[1:], {})
        if st.get("status") != "done":
            raise RuntimeError(f"{ref}: that job has not produced a file (it must come earlier and succeed)")
        return OUT / st["file"]
    p = inside(JOB / "inputs", ref)
    if not p.is_file():
        raise RuntimeError(f"input not found: {ref}")
    return p


def to_comfy_input(src, name):
    dst = COMFY / "input" / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):  # a video: take its last frame
        dst = dst.with_suffix(".png")
        sh(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", str(src), "-update", "1", "-frames:v", "1", str(dst)])
    else:
        shutil.copy(str(src), str(dst))
    return dst.name


def run_graph(graph, timeout):
    pid = call("/prompt", {"prompt": graph, "client_id": "ltxskill"})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = call(f"/history/{pid}").get(pid)
        if h and h.get("status", {}).get("completed") is not None:
            if h["status"].get("status_str") == "error":
                msgs = [m[1] for m in h["status"].get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(f"ComfyUI: {msgs[0].get('exception_message', '')[:600] if msgs else 'error'}")
            for out in h.get("outputs", {}).values():
                for items in out.values():
                    for it in items if isinstance(items, list) else []:
                        if isinstance(it, dict) and str(it.get("filename", "")).endswith(".mp4"):
                            return COMFY / "output" / it.get("subfolder", "") / it["filename"]
            raise RuntimeError("ComfyUI finished but returned no video")
        time.sleep(3)
    raise RuntimeError(f"no result after {timeout} s")


def join(first, second, dest):
    """second continues first: drop second's opening frame (it repeats first's last) and join with sound."""
    sh(["ffmpeg", "-v", "error", "-y", "-i", str(first), "-i", str(second), "-filter_complex",
        f"[1:v]trim=start_frame=1,setpts=PTS-STARTPTS[v1];[1:a]atrim=start={1 / ltx_graph.FPS},asetpts=PTS-STARTPTS[a1];"
        "[0:v][0:a][v1][a1]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "17", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest)])


def run_video(j):
    jid = j["id"]
    mode = j.get("mode", "text")
    first = last = None
    extend_src = None
    if j.get("extend"):
        extend_src = source_file(j["extend"])
        first, mode = to_comfy_input(extend_src, f"ltxskill_{jid}_extend.png"), "image"
    elif mode == "image":
        first = to_comfy_input(source_file(j["image"]), f"ltxskill_{jid}_image{Path(j['image']).suffix}")
    elif mode == "frames":
        if j.get("first"):
            first = to_comfy_input(source_file(j["first"]), f"ltxskill_{jid}_first{Path(j['first']).suffix}")
        if j.get("last"):
            last = to_comfy_input(source_file(j["last"]), f"ltxskill_{jid}_last{Path(j['last']).suffix}")
    seed = int(j["seed"]) if j.get("seed") is not None else int.from_bytes(os.urandom(6), "big")
    graph = ltx_graph.build(mode, j["prompt"], j.get("seconds", 5), j["resolution"], j.get("aspect", "16:9"), seed,
                            first=first, last=last, negative=j.get("negative"), prefix=f"ltxskill/{jid}")
    clip = run_graph(graph, int(j.get("timeout", 2400)))
    if extend_src is not None:
        joined = JOB / "work" / f"{jid}_joined.mp4"
        joined.parent.mkdir(exist_ok=True)
        join(extend_src, clip, joined)
        clip = joined
    return clip, {"seed": seed, "mode": mode}


def run_tts(j):
    """Text to audio with LTX-2.5 in audio-only mode: speech, sound effects or ambience. No voice reference."""
    seed = int(j["seed"]) if j.get("seed") is not None else int.from_bytes(os.urandom(6), "big")
    graph = ltx_graph.build_tts(j["prompt"], j.get("seconds", 5), seed, negative=j.get("negative"),
                                prefix=f"ltxskill/{j['id']}")
    pid = call("/prompt", {"prompt": graph, "client_id": "ltxskill"})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < int(j.get("timeout", 900)):
        h = call(f"/history/{pid}").get(pid)
        if h and h.get("status", {}).get("completed") is not None:
            if h["status"].get("status_str") == "error":
                msgs = [m[1] for m in h["status"].get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(f"ComfyUI: {msgs[0].get('exception_message', '')[:600] if msgs else 'error'}")
            a = next((it for out in h.get("outputs", {}).values() for it in out.get("audio", [])), None)
            if not a:
                raise RuntimeError("ComfyUI finished but returned no audio")
            flac = COMFY / "output" / a.get("subfolder", "") / a["filename"]
            wav = JOB / "work" / f"{j['id']}.wav"
            wav.parent.mkdir(exist_ok=True)
            sh(["ffmpeg", "-v", "error", "-y", "-i", str(flac), str(wav)])
            return wav, {"seed": seed}
        time.sleep(2)
    raise RuntimeError("TTS: no result in time")


RUNNERS = {"video": run_video, "tts": run_tts}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((JOB / "manifest.json").read_text(encoding="utf-8"))
    jobs = manifest["jobs"]
    for j in jobs:
        if not SAFE_ID.fullmatch(str(j.get("id", ""))):
            raise RuntimeError(f"bad job id: {j.get('id')!r}")
        STATE["jobs"][j["id"]] = {"type": j["type"], "status": "queued"}
    save()
    install()
    log("models: downloading what is missing", "models")
    download()
    start_comfy()
    STATE["stage"] = "generating"
    for j in jobs:
        st = STATE["jobs"][j["id"]]
        st.update(status="running", started=time.time())
        save()
        try:
            src, info = RUNNERS[j["type"]](j)
            dst = OUT / f"{j['id']}{'.wav' if j['type'] == 'tts' else '.mp4'}"
            shutil.copy(str(src), str(dst))
            st.update(status="done", file=dst.name, bytes=dst.stat().st_size,
                      seconds_used=round(time.time() - st["started"], 1), **info)
            log(f"{j['id']}: done in {st['seconds_used']} s -> {dst.name}")
        except Exception as e:
            st.update(status="error", error=str(e)[:1500])
            log(f"{j['id']}: ERROR {e}")
            if manifest.get("stop_on_error"):
                break
        save()
    STATE.update(done=True, stage="finished", finished=time.time())
    save()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        STATE.update(done=True, stage="failed", error=f"{e}\n{traceback.format_exc()[-1500:]}")
        save()
        raise
