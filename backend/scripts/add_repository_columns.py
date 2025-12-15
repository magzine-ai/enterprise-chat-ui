"""Migration script to add new columns to java_repositories table."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, text
from app.core.database import engine


def add_repository_columns():
    """Add new columns to java_repositories table if they don't exist."""
    with Session(engine) as session:
        try:
            # Check if table exists
            result = session.exec(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='java_repositories'")
            ).first()
            
            if not result:
                print("⚠️ java_repositories table doesn't exist yet. It will be created on next init_db()")
                return
            
            # Check existing columns
            result = session.exec(
                text("PRAGMA table_info(java_repositories)")
            ).all()
            
            column_names = [row[1] for row in result]
            columns_to_add = []
            
            if 'github_url' not in column_names:
                columns_to_add.append(("github_url", "VARCHAR"))
            if 'github_branch' not in column_names:
                columns_to_add.append(("github_branch", "VARCHAR"))
            if 'file_count' not in column_names:
                columns_to_add.append(("file_count", "INTEGER"))
            if 'languages' not in column_names:
                columns_to_add.append(("languages", "VARCHAR"))
            
            if columns_to_add:
                print(f"Adding {len(columns_to_add)} column(s) to java_repositories table...")
                for col_name, col_type in columns_to_add:
                    default = "NULL"
                    if col_name == "github_branch":
                        default = "'main'"
                    session.exec(
                        text(f"ALTER TABLE java_repositories ADD COLUMN {col_name} {col_type} DEFAULT {default}")
                    )
                session.commit()
                print(f"✅ Successfully added columns: {[col[0] for col in columns_to_add]}")
            else:
                print("✅ All columns already exist")
                
        except Exception as e:
            print(f"❌ Error adding columns: {e}")
            session.rollback()
            raise


if __name__ == "__main__":
    add_repository_columns()
    print("Migration completed!")

