"""
Migration script: Add branch column to java_chunks table.

This migration adds a 'branch' column to store the branch name for each chunk,
enabling branch-specific queries and filtering.
"""
import sqlite3
from app.core.config import settings


def add_branch_to_chunks():
    """Add branch column to java_chunks table."""
    db_path = settings.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(java_chunks)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'branch' not in columns:
            print("📝 Adding 'branch' column to java_chunks table...")
            cursor.execute("ALTER TABLE java_chunks ADD COLUMN branch VARCHAR")
            
            # Backfill: get branch from repository
            print("🔄 Backfilling branch data from repositories...")
            cursor.execute("""
                UPDATE java_chunks 
                SET branch = (
                    SELECT COALESCE(github_branch, 'main') 
                    FROM java_repositories 
                    WHERE java_repositories.id = java_chunks.repository_id
                )
                WHERE branch IS NULL
            """)
            
            conn.commit()
            print("✅ Successfully added 'branch' column to java_chunks table")
            print("✅ Backfilled branch data from repositories")
        else:
            print("ℹ️ 'branch' column already exists in java_chunks table")
            
    except Exception as e:
        print(f"❌ Error adding branch column: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    add_branch_to_chunks()

