import os, requests, uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

PORT = int(os.getenv("PORT", 8000))
ANIME_URL = os.getenv("ANIME_SERVICE_URL", "http://anime-service:8001")
GAME_URL = os.getenv("GAME_SERVICE_URL", "http://game-service:8002")
HOST_RUNNER_URL = os.getenv("HOST_RUNNER_URL", "http://docker.internal")

app = FastAPI(title="RetroHub Stream Control")

os.makedirs("/media/covers", exist_ok=True)
app.mount("/covers", StaticFiles(directory="/media/covers"), name="covers")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return FileResponse("static/index.html")

@app.get("/api/library")
def get_full_library():
    anime = requests.get(f"{ANIME_URL}/anime").json()
    games = requests.get(f"{GAME_URL}/games").json()
    return {"anime": anime, "games": games}

@app.post("/api/scan")
def scan_all():
    a_res = requests.post(f"{ANIME_URL}/anime/scan").json()
    g_res = requests.post(f"{GAME_URL}/games/scan").json()
    return {"anime": a_res, "games": g_res}

@app.post("/api/favorite/{item_type}/{item_id}")
def toggle_fav(item_type: str, item_id: int):
    url = f"{ANIME_URL}/anime/{item_id}/favorite" if item_type == "anime" else f"{GAME_URL}/games/{item_id}/favorite"
    return requests.post(url).json()

@app.post("/api/cover/{item_type}/{item_id}")
def upload_cover(item_type: str, item_id: int, file: UploadFile = File(...)):
    url = f"{ANIME_URL}/anime/{item_id}/cover" if item_type == "anime" else f"{GAME_URL}/games/{item_id}/cover"
    files = {"file": (file.filename, file.file, file.content_type)}
    return requests.post(url, files=files).json()

@app.post("/stream/play-anime")
def play_anime(id: int):
    ep = requests.get(f"{ANIME_URL}/anime/episode/{id}").json()
    requests.put(f"{ANIME_URL}/anime/episode/{id}/progress", params={"position": ep["playback_position"]})
    try:
        res = requests.post(f"{HOST_RUNNER_URL}/run-anime", json={
            "episode_id": id,
            "container_path": ep["file_path"],
            "start_position": ep["playback_position"]
        }, timeout=3).json()
        return res
    except Exception as e:
        return {"status": "mock_launched", "detail": f"Host runner не запущен: {e}", "file": ep["file_path"]}

@app.post("/stream/play-game")
def play_game(id: int):
    game = requests.get(f"{GAME_URL}/games/{id}").json()
    try:
        res = requests.post(f"{HOST_RUNNER_URL}/run-game", json={
            "platform": game["platform"],
            "container_path": game["rom_file_path"]
        }, timeout=3).json()
        return res
    except Exception as e:
        return {"status": "mock_launched", "detail": f"Host runner не запущен: {e}", "file": game["rom_file_path"]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
