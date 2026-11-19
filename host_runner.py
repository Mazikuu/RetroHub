import os, time, json, socket, threading, subprocess, requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import evdev

app = FastAPI()
BASE_DIR = os.path.expanduser("~/RetroHub")
MEDIA_HOST_PATH = os.path.join(BASE_DIR, "RetroHubMedia")
PLATFORMS_FILE = os.path.join(BASE_DIR, "platforms.json")
ANIME_API = "http://localhost:8001"
active_mpv_proc = None

class AnimeRunReq(BaseModel):
    episode_id: int
    container_path: str
    start_position: int

class GameRunReq(BaseModel):
    platform: str
    container_path: str

def to_host_path(container_path: str) -> str:
    return container_path.replace("/media", MEDIA_HOST_PATH, 1)

def find_core(core_name: str) -> str:
    sys_cores = f"/usr/lib/libretro/{core_name}"
    steam_cores = os.path.expanduser(f"~/.local/share/Steam/steamapps/common/RetroArch/cores/{core_name}")
    return sys_cores if os.path.exists(sys_cores) else steam_cores

def track_mpv_progress(ep_id: int, proc: subprocess.Popen):
    sock_path = "/tmp/mpvsocket"
    time.sleep(1.5)
    while proc.poll() is None:
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(sock_path)
            client.sendall(b'{"command": ["get_property", "time-pos"]}\n')
            resp = json.loads(client.recv(1024).decode())
            client.close()
            if "data" in resp and resp.get("data") is not None:
                pos = int(resp.get("data"))
                requests.put(f"{ANIME_API}/anime/episode/{ep_id}/progress", params={"position": pos})
        except Exception: pass
        time.sleep(5)

@app.post("/run-anime")
def run_anime(req: AnimeRunReq):
    global active_mpv_proc
    real_path = to_host_path(req.container_path)
    cmd = list(("mpv", real_path, f"--start={req.start_position}", "--video-aspect-override=4:3", "--fs", "--fs-screen=current", "--sid=no", "--input-ipc-server=/tmp/mpvsocket"))
    active_mpv_proc = subprocess.Popen(cmd)
    threading.Thread(target=track_mpv_progress, args=(req.episode_id, active_mpv_proc), daemon=True).start()
    return {"status": "started", "cmd": " ".join(cmd)}

@app.post("/run-game")
def run_game(req: GameRunReq):
    real_path = to_host_path(req.container_path)
    plat_key = req.platform.lower()
    
    with open(PLATFORMS_FILE, "r", encoding="utf-8") as f:
        platforms = json.load(f)
        
    cfg = platforms.get(plat_key)
    if not cfg:
        raise HTTPException(400, f"Платформа {plat_key} не описана в platforms.json")

    if cfg.get("type") == "command":
        cmd = list(part.replace("{rom}", real_path) for part in cfg.get("cmd", ()))
    else:
        core_path = find_core(cfg.get("core", "genesis_plus_gx_libretro.so"))
        cmd = list(("retroarch", "-f", "-L", core_path, real_path))

    print("Запуск игры:", " ".join(cmd))
    subprocess.Popen(cmd)
    return {"status": "started", "cmd": " ".join(cmd)}

def gamepad_watcher():
    global active_mpv_proc
    while True:
        devices = list(evdev.InputDevice(path) for path in evdev.list_devices())
        gamepads = list(d for d in devices if evdev.ecodes.EV_KEY in d.capabilities() and evdev.ecodes.BTN_START in d.capabilities().get(evdev.ecodes.EV_KEY, ()))
        if not gamepads: time.sleep(3); continue
        gp = gamepads.pop(0)
        pressed = set()
        try:
            for event in gp.read_loop():
                if event.type == evdev.ecodes.EV_KEY:
                    if event.value == 1: pressed.add(event.code)
                    elif event.value == 0: pressed.discard(event.code)
                    if evdev.ecodes.BTN_SELECT in pressed and evdev.ecodes.BTN_START in pressed:
                        if active_mpv_proc and active_mpv_proc.poll() is None: active_mpv_proc.terminate()
        except Exception: time.sleep(2)

threading.Thread(target=gamepad_watcher, daemon=True).start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9099)
