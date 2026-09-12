import sys
from pathlib import Path

# The batch package lives under scripts/, which is not an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
