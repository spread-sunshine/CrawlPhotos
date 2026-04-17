import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.dont_write_bytecode = True

from app.database.db import Database
from app.api.server import create_app

db = Database()
db.initialize()

app = create_app(db=db)

# Get the client to make a real request
from fastapi.testclient import TestClient
client = TestClient(app)
try:
    resp = client.get('/api/v1/photos?page=1&page_size=2')
    print('Status:', resp.status_code)
    print('Body:', resp.text[:500])
except Exception as e:
    print('Error:', e)
    traceback.print_exc()
