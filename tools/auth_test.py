"""Verify login gate renders unauthenticated, and user role hides delete controls."""
import os, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT))
os.environ["DB_MODE"] = "local"

from streamlit.testing.v1 import AppTest

# 1) no user -> login form, app body stopped
at = AppTest.from_file("app.py", default_timeout=120).run()
print("unauth exceptions:", [str(e.value)[:120] for e in at.exception])
print("unauth has login button:", any("Sign in" in (b.label or "") for b in at.button))
print("unauth tabs (should be 0):", len(at.tabs))

# 2) normal user -> no 'Clear existing data' checkbox (delete restricted)
at2 = AppTest.from_file("app.py", default_timeout=120)
at2.session_state["auth_user"] = {"username": "user", "role": "user"}
at2.run()
print("user exceptions:", [str(e.value)[:120] for e in at2.exception])
labels = [c.label for c in at2.checkbox]
print("user checkboxes:", labels)
print("user sees clear-data checkbox (should be False):", any("Clear existing data" in (l or "") for l in labels))
