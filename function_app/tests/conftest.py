import sys
from pathlib import Path

# repo root (for tfl_status.py) and function_app/ itself (for function_app.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
