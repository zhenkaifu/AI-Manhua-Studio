from pathlib import Path

# backend/app/core/paths.py -> 项目根目录是向上第 4 级
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
PROJECTS_DIR = DATA_DIR / "projects"
TEMP_DIR = DATA_DIR / "temp"

for d in (DATA_DIR, DATABASE_DIR, PROJECTS_DIR, TEMP_DIR):
    d.mkdir(parents=True, exist_ok=True)
