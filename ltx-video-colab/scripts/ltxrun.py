# -*- coding: utf-8 -*-
"""Local side of the ltx-video-colab skill: sends one batch of LTX-2.5 videos and voice/sound clips (tts) to a
Colab GPU, watches it, brings the files back and releases the GPU.

  python ltxrun.py check                          tools, login, compute units
  python ltxrun.py run job/manifest.json [--gpu L4] [--session NAME] [--max-minutes 120] [--confirmed]
  python ltxrun.py sessions                       runtimes still alive on your account (they cost units)
  python ltxrun.py keep --session NAME --minutes 60
  python ltxrun.py stop --session NAME            release one runtime
  python ltxrun.py stop --all                     release every runtime this skill started

The batch is run in the background on the VM (start.py) and polled with short `colab exec` calls (status.py):
a long-lived exec can drop its websocket; short ones do not. Results land in <manifest folder>/out/.

Security notes (this fork):
- every file the manifest names must stay inside the manifest's folder (no absolute paths, no ..)
- a file name reported back by the VM is accepted only if it is exactly "<job id>.mp4" (video) or "<job id>.wav"
  (tts) for a job in this batch,
  so a misbehaving VM cannot write anywhere else on this computer
- the OAuth token file is kept readable by this user only
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REMOTE = SKILL / "remote"
REMOTE_DIR = "/content/ltxjob"
GPUS = ("L4", "G4", "A100", "H100")   # colab-cli turns an unknown name into A100 without a word: only these pass
TYPES = ("video", "tts")
MODES = ("text", "image", "frames")
EXT = {"video": ".mp4", "tts": ".wav"}
RESOLUTIONS = ("480P", "720P", "1080P")
ASPECTS = ("16:9", "9:16")
PREFIX = "ltxskill-"
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,60}")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
TOKEN = Path.home() / ".config" / "colab-cli" / "token.json"


def colab_exe():
    for c in (shutil.which("colab"), Path.home() / ".local" / "bin" / "colab.exe", Path.home() / ".local" / "bin" / "colab"):
        if c and Path(c).exists():
            return str(c)
    sys.exit("找不到 colab 指令：請先執行安裝（install/install.ps1 或 install/install.sh）")


def colab(*args, timeout=600, check=True):
    """check=False: a call that hangs (colab-cli's websocket sometimes stalls) returns "" instead of raising."""
    try:
        # stdin closed: a backgrounded `colab exec` that inherits an open stdin can sit waiting on it
        p = subprocess.run([colab_exe(), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=ENV, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        if check:
            raise RuntimeError(f"colab {' '.join(map(str, args))} 超過 {timeout} 秒沒有回應")
        return ""
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        raise RuntimeError(f"colab {' '.join(map(str, args))} 失敗（{p.returncode}）：\n{out[-2000:]}")
    return out


def token_ok():
    if not TOKEN.is_file():
        return False
    if os.name != "nt" and TOKEN.stat().st_mode & 0o077:
        TOKEN.chmod(stat.S_IRUSR | stat.S_IWUSR)  # the refresh token: owner only
    return True


def usage():
    out = colab("usage", timeout=120, check=False)
    m = re.search(r"([\d.]+)\s*(?:compute units|運算單元|units)", out, re.I)
    return (float(m.group(1)) if m else None), out.strip()


def sessions():
    out = colab("sessions", timeout=120, check=False)
    return re.findall(rf"({PREFIX}[\w-]+)", out), out.strip()


# ---------------------------------------------------------------- keep-alive (the GPU waits for the next batch)
KEEP = Path.home() / ".config" / "ltxskill" / "keep"


def keep_file(session):
    return KEEP / f"{session}.json"


def set_keep(session, expires, pid=None):
    """expires = epoch seconds, or None while a batch is running (the watchdog never stops a busy GPU)."""
    KEEP.mkdir(parents=True, exist_ok=True)
    old = json.loads(keep_file(session).read_text(encoding="utf-8")) if keep_file(session).exists() else {}
    keep_file(session).write_text(json.dumps({"session": session, "expires": expires,
                                              "watchdog_pid": pid or old.get("watchdog_pid")}), encoding="utf-8")


def drop_keep(session):
    keep_file(session).unlink(missing_ok=True)


def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_watchdog(session):
    """A detached local process that releases the GPU when the keep time runs out, even after the agent's turn
    (or the whole chat) has ended. One per session."""
    info = json.loads(keep_file(session).read_text(encoding="utf-8"))
    if pid_alive(info.get("watchdog_pid")):
        return
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_watchdog", "--session", session], env=ENV, **kw)
    set_keep(session, info.get("expires"), p.pid)


def watchdog(session):
    log = KEEP / f"{session}.log"

    def say(msg):
        with log.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%m-%d %H:%M:%S ") + msg + "\n")

    say("watchdog started")
    while True:
        time.sleep(30)
        if not keep_file(session).exists():
            say("keep file removed (stopped by hand): exit")
            return
        info = json.loads(keep_file(session).read_text(encoding="utf-8"))
        if info.get("expires") is None or time.time() < info["expires"]:
            continue
        st = poll(session)
        if st and st.get("alive"):  # a batch started meanwhile: wait for it
            say("time is up but a batch is running: wait")
            continue
        say("time is up: releasing the GPU")
        colab("stop", "-s", session, timeout=300, check=False)
        drop_keep(session)
        say("released")
        return


# ---------------------------------------------------------------- manifest
FILE_KEYS = ("image", "first", "last", "extend")


def inside(base, rel):
    """True when rel (from the manifest) points at a file under base: no absolute paths, no .., no symlink escape."""
    rel = str(rel)
    if not rel or Path(rel).is_absolute() or re.match(r"^[A-Za-z]:", rel) or rel.startswith(("/", "\\")):
        return False
    p = (base / rel).resolve()
    return base.resolve() in p.parents


def load_manifest(path):
    path = Path(path).resolve()
    m = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    jobs, seen, problems = m.get("jobs") or [], {}, []
    if not jobs:
        problems.append("jobs 是空的")
    for j in jobs:
        jid = str(j.get("id", ""))
        if not SAFE_ID.fullmatch(jid):
            problems.append(f"id 只能用英數、- 和 _（1–60 字）：{jid!r}")
        if jid in seen:
            problems.append(f"id 重複：{jid}")
        typ = j.setdefault("type", "video")
        if typ not in TYPES:
            problems.append(f"{jid}：type 要是 {TYPES}（這個版本不能生圖）")
        if not str(j.get("prompt", "")).strip():
            problems.append(f"{jid}：沒有 prompt")
        try:
            if not 2 <= float(j.get("seconds", 5)) <= 20:
                problems.append(f"{jid}：seconds 要在 2–20 之間")
        except (TypeError, ValueError):
            problems.append(f"{jid}：seconds 要是數字")
        if typ == "tts":
            if any(j.get(k) for k in (*FILE_KEYS, "voices", "inputs")):
                problems.append(f"{jid}：tts 只吃文字，不能放檔案（不支援參考聲音）")
            seen[jid] = typ
            continue
        mode = j.setdefault("mode", "text")
        if mode not in MODES:
            problems.append(f"{jid}：mode 要是 {MODES}")
        if j.get("aspect", "16:9") not in ASPECTS:
            problems.append(f"{jid}：aspect 要是 {ASPECTS}")
        if j.get("resolution") and j["resolution"] not in RESOLUTIONS:
            problems.append(f"{jid}：resolution 要是 {RESOLUTIONS}")
        if j.get("extend") and str(j["extend"]) in seen:  # a bare id of an earlier job means its output
            j["extend"] = "@" + str(j["extend"])
        if mode == "image" and not j.get("image") and not j.get("extend"):
            problems.append(f"{jid}：mode image 要有 image（起始圖）")
        if mode == "frames" and not (j.get("first") or j.get("last")):
            problems.append(f"{jid}：mode frames 至少要有 first 或 last")
        if j.get("extend") and (j.get("first") or j.get("last") or j.get("image")):
            problems.append(f"{jid}：extend 不能和 image／first／last 一起用（延伸會自己拿上一段的最後一格）")
        for k in FILE_KEYS:
            f = j.get(k)
            if not f:
                continue
            f = str(f)
            if f.startswith("@"):
                if f[1:] not in seen:
                    problems.append(f"{jid}：{k} 的 {f} 要指向排在它前面的 job")
                elif seen[f[1:]] != "video" and k == "extend":
                    problems.append(f"{jid}：extend 只能接影片，{f} 是 {seen[f[1:]]}")
                elif seen[f[1:]] != "video":
                    problems.append(f"{jid}：{k} 要的是圖片或影片，{f} 是 {seen[f[1:]]}")
                continue
            if not inside(base, f):
                problems.append(f"{jid}：{k} 的路徑必須在 manifest 所在資料夾裡面（不能用絕對路徑或 ..）：{f}")
            elif not (base / f).is_file():
                problems.append(f"{jid}：找不到 {k} 檔案 {f}（路徑相對於 manifest 所在資料夾）")
        seen[jid] = typ
    if problems:
        sys.exit("manifest 有問題，沒有開機：\n- " + "\n- ".join(problems))
    return m, base


# ---------------------------------------------------------------- run
def remote_exec(session, code, timeout=120, tries=3):
    """A short `colab exec`; a stalled one is retried (the code is idempotent)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code.rstrip("\n") + "\nprint('LTXEXEC_OK')\n")  # proof it ran: some code prints nothing
    try:
        for k in range(tries):
            out = colab("exec", "-s", session, "-f", f.name, "--timeout", timeout, timeout=timeout + 30, check=False)
            if "LTXEXEC_OK" in out:
                return out.replace("LTXEXEC_OK", "").strip()
            print(f"…exec 沒有回應，重試（{k + 1}/{tries}）", flush=True)
        raise RuntimeError("colab exec 連續沒有回應")
    finally:
        os.unlink(f.name)


def poll(session):
    out = colab("exec", "-s", session, "-f", REMOTE / "status.py", "--timeout", 60, timeout=120, check=False)
    m = re.search(r"LTXSTATUS (\{.*\})", out)
    return json.loads(m.group(1)) if m else None


def safe_output_name(jid, name, job_types):
    """The VM tells us which file to fetch. Trust it only for '<one of our job ids>.<the extension of its type>'."""
    return jid in job_types and name == jid + EXT[job_types[jid]]


def skip_finished(m, base, force):
    """Resume: a job whose file is already in out/ is not made again; later jobs that point at it with @id
    get that local file instead (it is uploaded like any other input)."""
    if force:
        return m
    done = {j["id"]: f"out/{j['id']}{EXT[j['type']]}" for j in m["jobs"]
            if (base / "out" / f"{j['id']}{EXT[j['type']]}").is_file()}
    if not done:
        return m
    print(f"⏭️ 已經做好、這次跳過：{', '.join(done)}（要重做加 --force）", flush=True)
    jobs = []
    for j in m["jobs"]:
        if j["id"] in done:
            continue
        j = dict(j)
        for k in FILE_KEYS:
            v = j.get(k)
            if isinstance(v, str) and v.startswith("@") and v[1:] in done:
                j[k] = done[v[1:]]
        jobs.append(j)
    if not jobs:
        sys.exit("這一批全部都做好了（out/ 裡都有檔案）。要重做加 --force")
    return dict(m, jobs=jobs)


DEFAULT_RES = {"L4": "480P", "G4": "720P", "A100": "720P", "H100": "720P"}


def spec_summary(m, gpu):
    vids = [j for j in m["jobs"] if j["type"] == "video"]
    tts = [j for j in m["jobs"] if j["type"] == "tts"]
    secs = sum(float(j.get("seconds", 5)) for j in vids)
    shapes = sorted({j.get("aspect", "16:9") for j in vids})
    res = sorted({j.get("resolution") or "-" for j in vids})
    modes = {k: sum(1 for j in vids if j.get("mode") == k) for k in MODES}
    ext = sum(1 for j in vids if j.get("extend"))
    return (f"影片 {len(vids)} 段（文字 {modes['text']}、起始圖 {modes['image']}、首尾格 {modes['frames']}，其中延伸 {ext}），"
            f"共 {secs:g} 秒，解析度 {'/'.join(res)}，比例 {'/'.join(shapes)}；配音 {len(tts)} 段，GPU {gpu}"
            "（LTX-2.5 在這台 GPU 上的速度還沒實測，第一批請先試一段 5 秒）")


def run(args):
    m, base = load_manifest(args.manifest)
    m = skip_finished(m, base, args.force)
    gpu = (args.gpu or m.get("gpu") or "L4").upper()
    if gpu not in GPUS:
        sys.exit(f"GPU 只接受 {GPUS}（打錯字 colab 會默默開成 A100）")
    for j in m["jobs"]:  # resolution not given: the GPU's default (L4 480P, G4 720P)
        if j["type"] == "video":
            j["resolution"] = j.get("resolution") or DEFAULT_RES[gpu]
            j.setdefault("aspect", "16:9")
    job_types = {j["id"]: j["type"] for j in m["jobs"]}
    if sum(1 for j in m["jobs"] if j["type"] == "video") >= 2 and not args.confirmed:
        print("📋 這批：" + spec_summary(m, gpu))
        sys.exit("兩段以上的影片要先跟使用者確認規格（解析度、直式或橫式、秒數），確認後再加 --confirmed 送出。")
    print("📋 這批：" + spec_summary(m, gpu), flush=True)
    if not token_ok():
        sys.exit("還沒登入 Colab：先跑 python colab_login.py url，照指示登入")
    units, _ = usage()
    print(f"💳 剩餘運算單元：{units if units is not None else '（讀不到，請看 colab usage）'}", flush=True)
    if units is not None and units < 5:
        sys.exit("運算單元不到 5，先不開機（G4 每小時約 11、L4 約 1.5）")
    out_dir = base / "out"
    out_dir.mkdir(exist_ok=True)
    session, created = args.session, False
    alive, _ = sessions()
    if not session or session not in alive:
        session = session or f"{PREFIX}{time.strftime('%m%d-%H%M%S')}"
        print(f"🚀 開一台 {gpu}：{session}", flush=True)
        colab("new", "-s", session, "--gpu", gpu, timeout=900)
        created = True
    else:
        print(f"♻️ 沿用還開著的 {session}（模型已經在上面，可以省下安裝和下載）", flush=True)
    t0 = time.time()
    results = {"session": session, "gpu": gpu, "jobs": {}}
    set_keep(session, None)  # busy: an earlier batch's watchdog must not stop this one
    finished = False
    try:
        remote_exec(session, f"import os\nos.makedirs('{REMOTE_DIR}/inputs', exist_ok=True)\nprint('ok')")
        for f in ("remote_job.py", "ltx_graph.py"):
            colab("upload", "-s", session, REMOTE / f, f"{REMOTE_DIR}/{f}")
        manifest_tmp = Path(tempfile.gettempdir()) / f"{session}_manifest.json"
        manifest_tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        colab("upload", "-s", session, manifest_tmp, f"{REMOTE_DIR}/manifest.json")
        manifest_tmp.unlink(missing_ok=True)
        files = {str(j[k]) for j in m["jobs"] for k in FILE_KEYS if j.get(k) and not str(j[k]).startswith("@")}
        for f in files:  # checked by load_manifest already; checked again because skip_finished adds out/ paths
            if not inside(base, f):
                raise RuntimeError(f"拒絕上傳 manifest 資料夾以外的檔案：{f}")
        dirs = sorted({str(Path(f).parent).replace("\\", "/") for f in files} - {"."})
        if dirs:
            remote_exec(session, "import os\n" + "".join(
                f"os.makedirs({REMOTE_DIR + '/inputs/' + d!r}, exist_ok=True)\n" for d in dirs))
        for f in sorted(files):
            print(f"⬆️ {f}", flush=True)
            colab("upload", "-s", session, base / f, f"{REMOTE_DIR}/inputs/" + f.replace("\\", "/"), timeout=900)
        print(remote_exec(session, (REMOTE / "start.py").read_text(encoding="utf-8")).strip()[-300:], flush=True)
        got, last_line, misses = set(), "", 0
        while True:
            time.sleep(30)
            if time.time() - t0 > args.max_minutes * 60:
                raise RuntimeError(f"超過 {args.max_minutes} 分鐘上限，先停下來保護點數")
            st = poll(session)
            if not st:
                misses += 1
                print(f"…（這次沒讀到進度，下一輪再看；連續 {misses} 次）", flush=True)
                if misses >= 10:
                    raise RuntimeError("連續 10 次讀不到遠端進度（約半小時），先停下來保護點數")
                continue
            misses = 0
            line = f"[{(time.time() - t0) / 60:4.1f} 分] {st.get('stage')} · " + " ".join(
                f"{k}:{v['status']}" for k, v in st.get("jobs", {}).items())
            if line != last_line:
                print(line, flush=True)
                for l in st.get("log", [])[-2:]:
                    print("    " + l, flush=True)
                last_line = line
            for jid, v in st.get("jobs", {}).items():
                if v.get("status") == "done" and jid not in got:
                    if not safe_output_name(jid, v.get("file"), job_types):
                        print(f"⚠️ 遠端回報了不合規的檔名，不下載：{jid} → {v.get('file')!r}", flush=True)
                        got.add(jid)
                        results["jobs"][jid] = dict(v, status="error", error="unexpected file name from the VM")
                        continue
                    dst = out_dir / v["file"]
                    colab("download", "-s", session, f"{REMOTE_DIR}/out/{v['file']}", dst, timeout=1200, check=False)
                    if dst.is_file() and dst.stat().st_size == v.get("bytes", dst.stat().st_size):
                        got.add(jid)
                        print(f"⬇️ {dst}", flush=True)
                    else:
                        print(f"…{jid} 下載沒成功，下一輪再抓", flush=True)
                rejected = results["jobs"].get(jid, {}).get("error") == "unexpected file name from the VM"
                if jid in job_types and not rejected:
                    results["jobs"][jid] = dict(v, local=str(out_dir / (jid + EXT[job_types[jid]])) if v.get("file") else None)
            if st.get("done"):
                for _ in range(3):  # anything whose download failed during the run gets two more tries
                    missing = [k for k, v in st.get("jobs", {}).items()
                               if v.get("status") == "done" and k not in got and safe_output_name(k, v.get("file"), job_types)]
                    for jid in missing:
                        f = st["jobs"][jid]["file"]
                        colab("download", "-s", session, f"{REMOTE_DIR}/out/{f}", out_dir / f, timeout=1200, check=False)
                        if (out_dir / f).is_file():
                            got.add(jid)
                            print(f"⬇️ {out_dir / f}", flush=True)
                    if not missing:
                        break
                results.update(stage=st.get("stage"), error=st.get("error"))
                finished = True
                break
    finally:
        results["minutes"] = round((time.time() - t0) / 60, 1)
        (out_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.stop_after or not finished or args.idle_minutes <= 0:
            # an interrupted run is never left running: nobody knows what state that GPU is in
            print(f"🛑 釋放 GPU：{session}", flush=True)
            colab("stop", "-s", session, timeout=300, check=False)
            drop_keep(session)
        else:
            set_keep(session, time.time() + args.idle_minutes * 60)
            start_watchdog(session)
            print(f"⏸️ GPU 先留著：{session}（模型都在上面，下一批不用重新下載）", flush=True)
            print(f"   👉 請問使用者要不要保留。沒有回答的話 {args.idle_minutes:g} 分鐘後自動關閉"
                  f"（L4 一小時約 1.5 點，G4 約 11 點）。", flush=True)
            print(f"   接著做：python ltxrun.py run <manifest> --session {session}", flush=True)
            print(f"   多留一下：python ltxrun.py keep --session {session} --minutes 60", flush=True)
            print(f"   現在關掉：python ltxrun.py stop --session {session}", flush=True)
        left = [n for n in sessions()[0] if not keep_file(n).exists()]
        if left:
            print(f"⚠️ 帳號上還有其他開著的 runtime：{left}（會持續扣點，不用就 python ltxrun.py stop --all）", flush=True)
    bad = {k: v for k, v in results["jobs"].items() if v.get("status") != "done"}
    print(f"✅ 完成 {len(results['jobs']) - len(bad)}/{len(m['jobs'])}，共 {results['minutes']} 分鐘 → {out_dir}", flush=True)
    if bad or results.get("error"):
        print("❌ " + json.dumps({k: v.get("error") for k, v in bad.items()} or results.get("error"), ensure_ascii=False)[:1500])
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    r = sub.add_parser("run")
    r.add_argument("manifest")
    r.add_argument("--gpu")
    r.add_argument("--session")
    r.add_argument("--idle-minutes", type=float, default=15,
                   help="做完先留著 GPU 等下一批，幾分鐘沒有新工作就自動關（預設 15；0＝做完馬上關）")
    r.add_argument("--stop-after", action="store_true", help="做完馬上釋放 GPU")
    r.add_argument("--max-minutes", type=float, default=120)
    r.add_argument("--force", action="store_true", help="out/ 裡已經有的也重做")
    r.add_argument("--confirmed", action="store_true", help="使用者已經確認過規格（兩段以上影片必填）")
    sub.add_parser("sessions")
    k = sub.add_parser("keep")
    k.add_argument("--session", required=True)
    k.add_argument("--minutes", type=float, required=True)
    w = sub.add_parser("_watchdog")
    w.add_argument("--session", required=True)
    s = sub.add_parser("stop")
    s.add_argument("--session")
    s.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.cmd == "check":
        print("colab：", colab_exe())
        print("登入：", "✅ 已登入" if token_ok() else "❌ 還沒登入（python colab_login.py url）")
        if token_ok():
            units, raw = usage()
            print("運算單元：", units if units is not None else raw[-400:])
            alive, _ = sessions()
            print("開著的 runtime：", alive or "沒有")
    elif a.cmd == "run":
        run(a)
    elif a.cmd == "sessions":
        print(sessions()[1])
        for f in sorted(KEEP.glob("*.json")) if KEEP.exists() else []:
            info = json.loads(f.read_text(encoding="utf-8"))
            left = "跑批次中" if info.get("expires") is None else f"{max(0, info['expires'] - time.time()) / 60:.0f} 分鐘後自動關閉"
            print(f"⏸️ {info['session']}：{left}")
    elif a.cmd == "keep":
        minutes = min(a.minutes, 240)  # at most 4 hours: a forgotten GPU still stops by itself
        set_keep(a.session, time.time() + minutes * 60)
        start_watchdog(a.session)
        print(f"⏸️ {a.session} 再留 {minutes:g} 分鐘，之後沒有新工作就自動關閉")
    elif a.cmd == "_watchdog":
        watchdog(a.session)
    elif a.cmd == "stop":
        names = sessions()[0] if a.all else [a.session]
        if not names or names == [None]:
            sys.exit("要指定 --session NAME 或 --all")
        for n in names:
            print(n, colab("stop", "-s", n, timeout=300, check=False).strip()[-200:])
            drop_keep(n)


if __name__ == "__main__":
    main()
