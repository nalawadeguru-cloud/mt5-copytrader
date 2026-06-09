from fastapi.templating import Jinja2Templates
from pathlib import Path

# टेम्पलेट फोल्डरचा पाथ
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
