"""
Repository Manager Service for managing Java repositories and incremental indexing.

This service handles repository registration, file scanning, change detection,
and coordinates the indexing process.
"""

from typing import List, Dict, Any, Optional, Set
from pathlib import Path
import os
import hashlib
from datetime import datetime
from sqlmodel import Session, select
from app.core.config import settings
from app.models.java_repository import JavaRepository, RepositoryIndexStatus
from app.models.java_chunk import JavaChunk
from app.services.java_indexer_service import java_indexer_service
from app.services.opensearch_service import opensearch_service
import asyncio


class RepositoryManager:
    """
    Service for managing Java repositories.
    
    Handles repository registration, file discovery, change detection,
    and incremental indexing coordination.
    """
    
    def __init__(self):
        """Initialize the repository manager."""
        self.repositories_path = Path(settings.java_repositories_path)
        self.repositories_path.mkdir(parents=True, exist_ok=True)
    
    def register_repository(
        self,
        session: Session,
        name: str,
        local_path: str,
        description: Optional[str] = None
    ) -> JavaRepository:
        """
        Register a new Java repository.
        
        Args:
            session: Database session
            name: Repository name
            local_path: Local file system path to repository
            description: Optional description
        
        Returns:
            JavaRepository: Created repository object
        
        Raises:
            ValueError: If path doesn't exist or is invalid
        """
        path = Path(local_path)
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Repository path does not exist or is not a directory: {local_path}")
        
        # Check if repository already exists
        existing = session.exec(
            select(JavaRepository).where(JavaRepository.local_path == str(path.absolute()))
        ).first()
        
        if existing:
            return existing
        
        repository = JavaRepository(
            name=name,
            local_path=str(path.absolute()),
            description=description,
            status=RepositoryIndexStatus.PENDING
        )
        
        session.add(repository)
        session.commit()
        session.refresh(repository)
        
        print(f"✅ Registered repository: {name} at {local_path}")
        return repository
    
    def scan_repository(self, repository: JavaRepository) -> List[str]:
        """
        Scan repository and discover all Java files.
        
        Args:
            repository: JavaRepository object
        
        Returns:
            List[str]: List of Java file paths
        """
        java_files = java_indexer_service.find_java_files(repository.local_path)
        print(f"📁 Found {len(java_files)} Java files in {repository.name}")
        return java_files
    
    def get_changed_files(
        self,
        session: Session,
        repository: JavaRepository
    ) -> List[str]:
        """
        Detect files that have changed since last indexing.
        
        Args:
            session: Database session
            repository: JavaRepository object
        
        Returns:
            List[str]: List of changed file paths
        """
        if not repository.last_indexed_at:
            # First time indexing - index all files
            return self.scan_repository(repository)
        
        # Get existing chunks for this repository
        existing_chunks = session.exec(
            select(JavaChunk).where(JavaChunk.repository_id == repository.id)
        ).all()
        
        # Build map of file paths to last modified times
        existing_files = {}
        for chunk in existing_chunks:
            if chunk.file_path not in existing_files:
                existing_files[chunk.file_path] = chunk.last_modified
        
        # Scan for all Java files
        all_java_files = self.scan_repository(repository)
        
        # Find changed files
        changed_files = []
        for file_path in all_java_files:
            file_stat = os.stat(file_path)
            file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
            
            if file_path not in existing_files:
                # New file
                changed_files.append(file_path)
            elif file_mtime > existing_files[file_path]:
                # Modified file
                changed_files.append(file_path)
        
        print(f"🔄 Found {len(changed_files)} changed files in {repository.name}")
        return changed_files
    
    def get_file_hash(self, file_path: str) -> str:
        """
        Calculate hash of file content for change detection.
        
        Args:
            file_path: Path to file
        
        Returns:
            str: SHA256 hash of file content
        """
        with open(file_path, 'rb') as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()
    
    async def index_repository(
        self,
        session: Session,
        repository: JavaRepository,
        incremental: bool = True
    ) -> Dict[str, Any]:
        """
        Index a repository (full or incremental).
        
        Args:
            session: Database session
            repository: JavaRepository object
            incremental: Whether to do incremental indexing (only changed files)
        
        Returns:
            Dict with indexing statistics
        """
        repository.status = RepositoryIndexStatus.INDEXING
        session.add(repository)
        session.commit()
        
        stats = {
            'total_files': 0,
            'indexed_files': 0,
            'total_chunks': 0,
            'indexed_chunks': 0,
            'errors': 0
        }
        
        try:
            # Get files to index
            if incremental:
                files_to_index = self.get_changed_files(session, repository)
            else:
                files_to_index = self.scan_repository(repository)
            
            stats['total_files'] = len(files_to_index)
            
            if not files_to_index:
                repository.status = RepositoryIndexStatus.COMPLETED
                repository.last_indexed_at = datetime.utcnow()
                session.add(repository)
                session.commit()
                return stats
            
            # Delete existing chunks for changed files (if incremental)
            if incremental:
                for file_path in files_to_index:
                    existing_chunks = session.exec(
                        select(JavaChunk).where(
                            JavaChunk.repository_id == repository.id,
                            JavaChunk.file_path == file_path
                        )
                    ).all()
                    for chunk in existing_chunks:
                        # Delete from OpenSearch if enabled
                        if settings.java_opensearch_enabled and opensearch_service.is_available() and chunk.id:
                            try:
                                await opensearch_service.delete_java_chunk(chunk.id)
                            except Exception as e:
                                print(f"⚠️ Failed to delete chunk {chunk.id} from OpenSearch: {e}")
                        session.delete(chunk)
                session.commit()
            
            # Process files in batches
            batch_size = settings.java_indexer_batch_size
            all_chunks = []
            
            for i, file_path in enumerate(files_to_index):
                try:
                    # Parse file
                    parsed_data = java_indexer_service.parse_java_file(file_path)
                    if not parsed_data:
                        continue
                    
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        file_content = f.read()
                    
                    # Generate chunks
                    chunks = java_indexer_service.generate_chunks(
                        parsed_data,
                        file_content,
                        repository.id
                    )
                    
                    all_chunks.extend(chunks)
                    stats['indexed_files'] += 1
                    
                    # Process in batches
                    if len(all_chunks) >= batch_size:
                        await self._process_chunk_batch(session, all_chunks, repository.id)
                        stats['indexed_chunks'] += len(all_chunks)
                        all_chunks = []
                    
                except Exception as e:
                    print(f"❌ Error indexing {file_path}: {e}")
                    stats['errors'] += 1
            
            # Process remaining chunks
            if all_chunks:
                await self._process_chunk_batch(session, all_chunks, repository.id)
                stats['indexed_chunks'] += len(all_chunks)
            
            # Build call graph
            if all_chunks:
                java_indexer_service.build_call_graph(all_chunks)
                java_indexer_service.update_chunk_callers_callees(all_chunks)
                
                # Update chunks with call graph info
                for chunk_data in all_chunks:
                    chunk = session.exec(
                        select(JavaChunk).where(
                            JavaChunk.fqn == chunk_data['fqn'],
                            JavaChunk.repository_id == repository.id
                        )
                    ).first()
                    if chunk:
                        chunk.set_callers(chunk_data.get('callers', []))
                        chunk.set_callees(chunk_data.get('callees', []))
                        session.add(chunk)
                        
                        # Update OpenSearch relationships if enabled
                        if settings.java_opensearch_enabled and opensearch_service.is_available() and chunk.id:
                            try:
                                await opensearch_service.update_java_chunk_relationships(
                                    chunk_id=chunk.id,
                                    callers=chunk.get_callers(),
                                    callees=chunk.get_callees()
                                )
                            except Exception as e:
                                print(f"⚠️ Failed to update chunk {chunk.id} relationships in OpenSearch: {e}")
                session.commit()
            
            stats['total_chunks'] = stats['indexed_chunks']
            
            # Update repository status
            repository.status = RepositoryIndexStatus.COMPLETED
            repository.last_indexed_at = datetime.utcnow()
            session.add(repository)
            session.commit()
            
            print(f"✅ Indexed repository {repository.name}: {stats}")
            
        except Exception as e:
            print(f"❌ Error indexing repository {repository.name}: {e}")
            repository.status = RepositoryIndexStatus.FAILED
            session.add(repository)
            session.commit()
            raise
        
        return stats
    
    async def _process_chunk_batch(
        self,
        session: Session,
        chunks: List[Dict[str, Any]],
        repository_id: int
    ):
        """
        Process a batch of chunks: store in DB and generate embeddings.
        
        Args:
            session: Database session
            chunks: List of chunk dictionaries
            repository_id: Repository ID
        """
        # Ensure OpenSearch index exists if enabled
        if settings.java_opensearch_enabled and opensearch_service.is_available():
            await opensearch_service.ensure_java_index_exists()
        
        # Generate embeddings
        texts = [chunk['code'] for chunk in chunks]
        embeddings = await java_indexer_service.generate_embeddings(texts)
        
        # Store chunks in database
        for i, chunk_data in enumerate(chunks):
            chunk = JavaChunk(
                type=chunk_data['type'],
                fqn=chunk_data['fqn'],
                file_path=chunk_data['file_path'],
                start_line=chunk_data['start_line'],
                end_line=chunk_data['end_line'],
                code=chunk_data['code'],
                summary=chunk_data.get('summary'),
                repository_id=repository_id,
                last_modified=chunk_data.get('last_modified', datetime.utcnow())
            )
            
            # Set JSON fields
            chunk.set_imports(chunk_data.get('imports', []))
            chunk.set_annotations(chunk_data.get('annotations', []))
            chunk.set_callers(chunk_data.get('callers', []))
            chunk.set_callees(chunk_data.get('callees', []))
            if 'implemented_interfaces' in chunk_data:
                chunk.set_implemented_interfaces(chunk_data['implemented_interfaces'])
            if 'extended_class' in chunk_data:
                chunk.extended_class = chunk_data['extended_class']
            
            session.add(chunk)
            session.flush()  # Get chunk ID
            
            # Store embedding in OpenSearch if enabled
            if settings.java_opensearch_enabled and opensearch_service.is_available():
                embedding = embeddings[i] if i < len(embeddings) else None
                if embedding:
                    try:
                        await opensearch_service.index_java_chunk(
                            chunk_id=chunk.id,
                            repository_id=repository_id,
                            chunk_type=chunk.type,
                            fqn=chunk.fqn,
                            file_path=chunk.file_path,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            code=chunk.code,
                            summary=chunk.summary,
                            embedding=embedding,
                            imports=chunk.get_imports(),
                            annotations=chunk.get_annotations(),
                            callers=chunk.get_callers(),
                            callees=chunk.get_callees(),
                            implemented_interfaces=chunk.get_implemented_interfaces(),
                            extended_class=chunk.extended_class,
                            test_references=chunk.get_test_references(),
                            last_modified=chunk.last_modified.isoformat() if chunk.last_modified else None
                        )
                    except Exception as e:
                        print(f"⚠️ Failed to index chunk {chunk.id} in OpenSearch: {e}")
                        # Continue processing even if OpenSearch indexing fails
        
        session.commit()


# Global instance
repository_manager = RepositoryManager()

