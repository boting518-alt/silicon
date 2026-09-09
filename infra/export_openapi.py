"""Generate the API contract without opening a database connection."""
import json
from pathlib import Path
from silicon.main import create_app
from silicon.settings import Settings

app = create_app(Settings("postgresql+psycopg://unused@localhost/unused", "test"))
Path("packages/api-client/openapi.json").write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
