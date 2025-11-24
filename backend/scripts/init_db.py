"""Initialize database tables."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")

