"""Migration script to add thinking_mode column to conversations table."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, text
from app.core.database import engine


def add_thinking_mode_column():
    """Add thinking_mode column to conversations table if it doesn't exist."""
    with Session(engine) as session:
        try:
            # Check if column exists (SQLite specific)
            result = session.exec(
                text("PRAGMA table_info(conversations)")
            ).all()
            
            column_names = [row[1] for row in result]
            
            if 'thinking_mode' not in column_names:
                print("Adding thinking_mode column to conversations table...")
                session.exec(
                    text("ALTER TABLE conversations ADD COLUMN thinking_mode VARCHAR DEFAULT 'thinking'")
                )
                session.commit()
                print("✅ Successfully added thinking_mode column")
            else:
                print("✅ thinking_mode column already exists")
                
        except Exception as e:
            print(f"❌ Error adding thinking_mode column: {e}")
            session.rollback()
            raise


if __name__ == "__main__":
    add_thinking_mode_column()
    print("Migration completed!")

