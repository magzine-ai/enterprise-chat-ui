"""
Migration script to add agent column to conversations table.
"""

from sqlalchemy import text
from app.core.database import engine


def add_agent_column():
    """Add agent column to conversations table if it doesn't exist."""
    with engine.begin() as conn:
        try:
            result = conn.execute(text("PRAGMA table_info(conversations);"))
            column_names = [row[1] for row in result]
            if "agent" not in column_names:
                print("Adding agent column to conversations table...")
                conn.execute(text("ALTER TABLE conversations ADD COLUMN agent VARCHAR DEFAULT 'ask'"))
                print("✅ Successfully added agent column")
            else:
                print("✅ agent column already exists")
        except Exception as e:
            print(f"❌ Error adding agent column: {e}")


if __name__ == "__main__":
    add_agent_column()

