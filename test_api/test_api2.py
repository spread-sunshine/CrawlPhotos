import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.dont_write_bytecode = True

from app.database.db import Database
from app.api.server import create_app
import traceback

db = Database()
db.initialize()

app = create_app(db=db, orchestrator=None)

# Get the list_photos function from the app
for route in app.routes:
    if hasattr(route, 'path') and route.path == '/api/v1/photos':
        func = getattr(route, 'app', None) or route
        break

# Try calling the function directly
try:
    rows = db.execute_query_all('SELECT * FROM photos LIMIT 2')
    r = rows[0]
    print('Row keys:', list(r.keys()))

    source_photo_id = r.get('personal_photo_id', '')
    upload_time = r.get('created_at')
    contains_target = bool(r.get('contains_target'))
    confidence = float(r.get('confidence') or 0)

    item = {
        'photo_id': r.get('photo_id', ''),
        'source_photo_id': source_photo_id,
        'upload_time': upload_time,
        'local_path': r.get('local_path'),
        'contains_target': contains_target,
        'confidence': confidence,
        'status': r.get('status', 'unknown'),
        'created_at': r.get('created_at', ''),
    }
    print('Item:', item)
except Exception as e:
    with open('d:/ugit/Test/CrawlPhotos/test_api/test_api_err.txt', 'w') as f:
        f.write(traceback.format_exc())
        print('Error written to file')
