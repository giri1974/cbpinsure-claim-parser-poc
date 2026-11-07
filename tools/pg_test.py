"""Quick Postgres connectivity + schema check. Reads DATABASE_URL + DB_MODE from env."""
import os, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT))

from claimparser import config, db
print("mode:", config.mode(), "| server:", config.server_label())
ok, msg = db.test_connection()
print("test:", ok, msg[:160])
if ok:
    db.init_db()
    tabs = db.query_df("select table_name from information_schema.tables where table_schema='dbo' order by table_name")
    print("tables:", tabs["table_name"].tolist())
