"""
Test script to compare different chunking strategies.

This script helps you test and compare chunking strategies by:
1. Indexing a repository with different strategies
2. Comparing chunk statistics (count, size, storage)
3. Testing search quality with sample queries

Usage:
  PYTHONPATH=. python scripts/test_chunking_strategies.py \
    --repo-path /path/to/repo \
    --strategies method_only,class_metadata,recursive \
    --test-queries "getUser", "createUser", "updateUser"
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.services.repository_manager import repository_manager
from app.models.java_repository import JavaRepository
from app.models.java_chunk import JavaChunk
from sqlmodel import select


async def test_strategy(
    strategy: str,
    repo_path: str,
    repo_name: str
) -> Dict[str, Any]:
    """Test a chunking strategy and return statistics."""
    print(f"\n{'='*60}")
    print(f"Testing Strategy: {strategy}")
    print(f"{'='*60}")
    
    # Update config for this strategy
    original_strategy = settings.java_chunking_strategy
    settings.java_chunking_strategy = strategy
    
    try:
        with Session(engine) as session:
            # Register or get repository
            repo = repository_manager.register_repository(
                session=session,
                name=f"{repo_name}_{strategy}",
                local_path=repo_path,
                description=f"Test repo for {strategy} strategy"
            )
            
            # Clear existing chunks for this test
            existing_chunks = session.exec(
                select(JavaChunk).where(JavaChunk.repository_id == repo.id)
            ).all()
            for chunk in existing_chunks:
                session.delete(chunk)
            session.commit()
            
            # Index repository
            print(f"📁 Indexing repository with strategy '{strategy}'...")
            stats = await repository_manager.index_repository(
                session=session,
                repository=repo,
                incremental=False
            )
            
            # Get chunk statistics
            chunks = session.exec(
                select(JavaChunk).where(JavaChunk.repository_id == repo.id)
            ).all()
            
            # Calculate statistics
            chunk_sizes = [len(chunk.code or '') for chunk in chunks]
            chunk_types = {}
            for chunk in chunks:
                chunk_type = chunk.type
                chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
            
            total_size = sum(chunk_sizes)
            avg_size = total_size / len(chunks) if chunks else 0
            max_size = max(chunk_sizes) if chunk_sizes else 0
            min_size = min(chunk_sizes) if chunk_sizes else 0
            
            strategy_stats = {
                'strategy': strategy,
                'repository_id': repo.id,
                'total_chunks': len(chunks),
                'chunk_types': chunk_types,
                'total_size_chars': total_size,
                'avg_chunk_size': round(avg_size, 2),
                'max_chunk_size': max_size,
                'min_chunk_size': min_size,
                'indexing_stats': stats
            }
            
            print(f"✅ Strategy '{strategy}' completed:")
            print(f"   Total chunks: {len(chunks)}")
            print(f"   Chunk types: {chunk_types}")
            print(f"   Avg size: {avg_size:.0f} chars")
            print(f"   Max size: {max_size} chars")
            print(f"   Min size: {min_size} chars")
            print(f"   Total size: {total_size:,} chars")
            
            return strategy_stats
            
    finally:
        # Restore original strategy
        settings.java_chunking_strategy = original_strategy


async def compare_strategies(
    strategies: List[str],
    repo_path: str,
    repo_name: str,
    output_file: Optional[str] = None
):
    """Compare multiple chunking strategies."""
    results = []
    
    for strategy in strategies:
        try:
            stats = await test_strategy(strategy, repo_path, repo_name)
            results.append(stats)
        except Exception as e:
            print(f"❌ Error testing strategy '{strategy}': {e}")
            import traceback
            traceback.print_exc()
    
    # Print comparison table
    print(f"\n{'='*80}")
    print("STRATEGY COMPARISON")
    print(f"{'='*80}")
    print(f"{'Strategy':<20} {'Chunks':<10} {'Avg Size':<12} {'Max Size':<12} {'Total Size':<15}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['strategy']:<20} "
              f"{result['total_chunks']:<10} "
              f"{result['avg_chunk_size']:<12.0f} "
              f"{result['max_chunk_size']:<12} "
              f"{result['total_size_chars']:<15,}")
    
    # Save results to file
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✅ Results saved to {output_file}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Test and compare chunking strategies")
    parser.add_argument("--repo-path", required=True, help="Repository path to test")
    parser.add_argument("--repo-name", default="test_repo", help="Repository name")
    parser.add_argument(
        "--strategies",
        default="method_only,class_metadata,recursive,sliding_window,hybrid",
        help="Comma-separated list of strategies to test"
    )
    parser.add_argument("--output", help="Output JSON file for results")
    args = parser.parse_args()
    
    strategies = [s.strip() for s in args.strategies.split(',')]
    
    print(f"🧪 Testing Chunking Strategies")
    print(f"   Repository: {args.repo_path}")
    print(f"   Strategies: {', '.join(strategies)}")
    print(f"   Max chunk size: {settings.java_max_chunk_size}")
    print(f"   Enforce size: {settings.java_enforce_chunk_size}")
    
    results = asyncio.run(compare_strategies(strategies, args.repo_path, args.repo_name, args.output))
    
    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")
    
    if results:
        # Find strategy with best balance
        best_balance = min(
            results,
            key=lambda x: abs(x['avg_chunk_size'] - 500) + (x['total_chunks'] / 100)
        )
        print(f"✅ Best balance: {best_balance['strategy']}")
        print(f"   - {best_balance['total_chunks']} chunks")
        print(f"   - Avg size: {best_balance['avg_chunk_size']:.0f} chars")
        
        # Find smallest storage
        smallest = min(results, key=lambda x: x['total_size_chars'])
        print(f"\n💾 Smallest storage: {smallest['strategy']}")
        print(f"   - Total size: {smallest['total_size_chars']:,} chars")
        
        # Find most chunks (best precision)
        most_chunks = max(results, key=lambda x: x['total_chunks'])
        print(f"\n🎯 Most precise: {most_chunks['strategy']}")
        print(f"   - {most_chunks['total_chunks']} chunks")


if __name__ == "__main__":
    main()

