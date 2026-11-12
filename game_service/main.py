import os, shutil
from datetime import datetime
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@db:5432/app")
PORT = int(os.getenv("PORT", 8002))
MEDIA_ROOT = "/media"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class RetroGame(Base):
    __tablename__ = "retro_games"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    rom_file_path = Column(String, unique=True, nullable=False)
    cover_url = Column(String, default="")
    is_favorite = Column(Boolean, default=False)
    last_played_at = Column(DateTime, nullable=True)

Base.metadata.create_all(bind=engine)
app = FastAPI(title="RetroHub RetroGame Service")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.post("/games/scan")
def scan_games(db: Session = Depends(get_db)):
    roms_dir = os.path.join(MEDIA_ROOT, "roms")
    added = 0
    for platform in ("sega", "nes", "ps1"):
        p_dir = os.path.join(roms_dir, platform)
        if not os.path.exists(p_dir): continue
        for fname in sorted(os.listdir(p_dir)):
            fpath = os.path.join(p_dir, fname)
            if not os.path.isfile(fpath): continue
            if not db.query(RetroGame).filter(RetroGame.rom_file_path == fpath).first():
                title, _ = os.path.splitext(fname)
                db.add(RetroGame(title=title, platform=platform.upper(), rom_file_path=fpath))
                added += 1
    db.commit()
    return {"status": "ok", "added_games": added}

@app.get("/games")
def list_games(db: Session = Depends(get_db)):
    return list({
        "id": g.id, "title": g.title, "platform": g.platform, "rom_file_path": g.rom_file_path,
        "cover_url": g.cover_url, "is_favorite": g.is_favorite,
        "last_played_at": g.last_played_at.isoformat() if g.last_played_at else None
    } for g in db.query(RetroGame).all())

@app.get("/games/{game_id}")
def get_game(game_id: int, db: Session = Depends(get_db)):
    g = db.query(RetroGame).filter(RetroGame.id == game_id).first()
    if not g: raise HTTPException(404, "Игра не найдена")
    g.last_played_at = datetime.utcnow()
    db.commit()
    return {"id": g.id, "title": g.title, "platform": g.platform, "rom_file_path": g.rom_file_path}

@app.post("/games/{game_id}/favorite")
def toggle_favorite(game_id: int, db: Session = Depends(get_db)):
    g = db.query(RetroGame).filter(RetroGame.id == game_id).first()
    if not g: raise HTTPException(404, "Игра не найдена")
    g.is_favorite = not g.is_favorite
    db.commit()
    return {"is_favorite": g.is_favorite}

@app.post("/games/{game_id}/cover")
def upload_cover(game_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    g = db.query(RetroGame).filter(RetroGame.id == game_id).first()
    if not g: raise HTTPException(404, "Игра не найдена")
    os.makedirs(os.path.join(MEDIA_ROOT, "covers"), exist_ok=True)
    _, ext = os.path.splitext(file.filename)
    filename = f"game_{game_id}{ext}"
    with open(os.path.join(MEDIA_ROOT, "covers", filename), "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    g.cover_url = f"/covers/{filename}"
    db.commit()
    return {"cover_url": g.cover_url}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
