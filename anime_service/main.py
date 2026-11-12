import os, re, shutil
from datetime import datetime
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@db:5432/app")
PORT = int(os.getenv("PORT", 8001))
MEDIA_ROOT = "/media"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AnimeSeries(Base):
    __tablename__ = "anime_series"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True, nullable=False)
    folder_path = Column(String, nullable=False)
    cover_url = Column(String, default="")
    is_favorite = Column(Boolean, default=False)
    last_watched_at = Column(DateTime, nullable=True)
    episodes = relationship("AnimeEpisode", back_populates="series", cascade="all, delete-orphan")

class AnimeEpisode(Base):
    __tablename__ = "anime_episodes"
    id = Column(Integer, primary_key=True, index=True)
    series_id = Column(Integer, ForeignKey("anime_series.id"))
    episode_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    file_path = Column(String, unique=True, nullable=False)
    is_watched = Column(Boolean, default=False)
    playback_position = Column(Integer, default=0)
    series = relationship("AnimeSeries", back_populates="episodes")

Base.metadata.create_all(bind=engine)
app = FastAPI(title="RetroHub Anime Service")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.post("/anime/scan")
def scan_anime_library(db: Session = Depends(get_db)):
    anime_dir = os.path.join(MEDIA_ROOT, "anime")
    if not os.path.exists(anime_dir): return {"added_series": 0, "added_episodes": 0}
    added_s, added_e = 0, 0
    video_exts = (".mkv", ".mp4", ".avi", ".webm")
    for folder_name in sorted(os.listdir(anime_dir)):
        full_folder = os.path.join(anime_dir, folder_name)
        if not os.path.isdir(full_folder): continue
        series = db.query(AnimeSeries).filter(AnimeSeries.title == folder_name).first()
        if not series:
            series = AnimeSeries(title=folder_name, folder_path=full_folder)
            db.add(series); db.commit(); db.refresh(series)
            added_s += 1
        files = sorted(f for f in os.listdir(full_folder) if f.lower().endswith(video_exts))
        for idx, fname in enumerate(files, start=1):
            fpath = os.path.join(full_folder, fname)
            ep = db.query(AnimeEpisode).filter(AnimeEpisode.file_path == fpath).first()
            if not ep:
                nums = re.findall(r'\d+', re.sub(r'\[.*?\]', '', fname))
                ep_num = int(nums.pop()) if nums else idx
                db.add(AnimeEpisode(series_id=series.id, episode_number=ep_num, title=fname, file_path=fpath))
                added_e += 1
    db.commit()
    return {"status": "ok", "added_series": added_s, "added_episodes": added_e}

@app.get("/anime")
def list_anime(db: Session = Depends(get_db)):
    result = list()
    for s in db.query(AnimeSeries).all():
        eps = sorted(s.episodes, key=lambda x: x.episode_number)
        result.append({
            "id": s.id, "title": s.title, "cover_url": s.cover_url, "is_favorite": s.is_favorite,
            "last_watched_at": s.last_watched_at.isoformat() if s.last_watched_at else None,
            "episodes": list({"id": e.id, "episode_number": e.episode_number, "title": e.title, "file_path": e.file_path, "is_watched": e.is_watched, "playback_position": e.playback_position} for e in eps)
        })
    return result

@app.get("/anime/episode/{ep_id}")
def get_episode(ep_id: int, db: Session = Depends(get_db)):
    ep = db.query(AnimeEpisode).filter(AnimeEpisode.id == ep_id).first()
    if not ep: raise HTTPException(404, "Серия не найдена")
    return {"id": ep.id, "file_path": ep.file_path, "playback_position": ep.playback_position, "series_id": ep.series_id}

@app.put("/anime/episode/{ep_id}/progress")
def update_progress(ep_id: int, position: int, watched: bool = False, db: Session = Depends(get_db)):
    ep = db.query(AnimeEpisode).filter(AnimeEpisode.id == ep_id).first()
    if not ep: raise HTTPException(404, "Серия не найдена")
    ep.playback_position = position
    if watched: ep.is_watched = True
    ep.series.last_watched_at = datetime.utcnow()
    db.commit()
    return {"status": "updated"}

@app.post("/anime/{series_id}/favorite")
def toggle_favorite(series_id: int, db: Session = Depends(get_db)):
    s = db.query(AnimeSeries).filter(AnimeSeries.id == series_id).first()
    if not s: raise HTTPException(404, "Тайтл не найден")
    s.is_favorite = not s.is_favorite
    db.commit()
    return {"is_favorite": s.is_favorite}

@app.post("/anime/{series_id}/cover")
def upload_cover(series_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    s = db.query(AnimeSeries).filter(AnimeSeries.id == series_id).first()
    if not s: raise HTTPException(404, "Тайтл не найден")
    os.makedirs(os.path.join(MEDIA_ROOT, "covers"), exist_ok=True)
    _, ext = os.path.splitext(file.filename)
    filename = f"anime_{series_id}{ext}"
    with open(os.path.join(MEDIA_ROOT, "covers", filename), "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    s.cover_url = f"/covers/{filename}"
    db.commit()
    return {"cover_url": s.cover_url}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
