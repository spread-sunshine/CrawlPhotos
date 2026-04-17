import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.dont_write_bytecode = True

from app.database.db import Database
db = Database()
db.initialize()

# Exact copy of list_photos logic
page = 1
page_size = 5
target_only = False
status_filter = None

offset = (page - 1) * page_size
where_parts = []
params = []

if target_only:
    where_parts.append("contains_target = 1")
if status_filter:
    where_parts.append("status = ?")
    params.append(status_filter)

where_clause = (" AND ".join(where_parts)) if where_parts else "1=1"

try:
    count_row = db.execute_query_one(
        f"SELECT COUNT(*) AS total FROM photos WHERE {where_clause}",
        params,
    )
    print('count OK:', count_row)
except Exception as e:
    print('count ERROR:', e)
    traceback.print_exc()

try:
    total = count_row["total"] if count_row else 0
    rows = db.execute_query_all(
        f"SELECT * FROM photos WHERE {where_clause} "
        f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    print('query OK, rows:', len(rows))
except Exception as e:
    print('query ERROR:', e)
    traceback.print_exc()
