#!/usr/bin/env python3
"""
Standalone XML Parser for Data and Rules Files

This script parses XML files from a repository, classifies them as data/rules/generic,
extracts meaningful chunks, and optionally generates embeddings and indexes to OpenSearch.

Usage:
    python standalone_xml_parser.py --repo-path /path/to/repo --output-dir ./output
    python standalone_xml_parser.py --repo-path /path/to/repo --opensearch-host https://... --opensearch-index xml-chunks
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import xml.etree.ElementTree as ET

# Optional dependencies
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from aws_requests_auth.aws_auth import AWSRequestsAuth
    import boto3
    OPENSEARCH_AVAILABLE = True
except ImportError:
    OPENSEARCH_AVAILABLE = False

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class XMLParser:
    """Parser for XML data and rules files."""
    
    def __init__(self, max_chunk_size: int = 2000, chunk_overlap: int = 200):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.repo_path = None
    
    def find_xml_files(self, repo_path: str, exclude_patterns: Optional[List[str]] = None) -> List[str]:
        """
        Find all XML files in repository, excluding build/config files.
        
        Args:
            repo_path: Root path of repository
            exclude_patterns: Additional file patterns to exclude
            
        Returns:
            List of XML file paths
        """
        repo = Path(repo_path)
        self.repo_path = repo_path
        
        # Default exclude patterns (build/config files)
        default_excludes = [
            'pom.xml', 'build.xml', 'settings.xml', 'web.xml',
            'applicationContext.xml', 'spring.xml', 'beans.xml',
            'persistence.xml', 'hibernate.cfg.xml', 'log4j.xml',
            'logback.xml', 'maven.xml', '.idea', '.vscode'
        ]
        
        if exclude_patterns:
            default_excludes.extend(exclude_patterns)
        
        exclude_dirs = {
            '.git', 'node_modules', 'target', 'build', '__pycache__', '.venv',
            'test', 'tests', '__tests__', 'spec',
            'test/java', 'test/resources', 'src/test', 'src/test/java', 'src/test/resources'
        }
        
        xml_files = []
        for xml_file in repo.rglob('*.xml'):
            # Skip excluded directories
            if any(excluded in xml_file.parts for excluded in exclude_dirs):
                continue
            
            # Skip excluded file patterns
            if xml_file.name in default_excludes:
                continue
            
            xml_files.append(str(xml_file))
        
        return sorted(xml_files)
    
    def classify_xml_type(self, root: ET.Element, file_path: str) -> str:
        """
        Classify XML file as 'data', 'rules', or 'generic'.
        
        Args:
            root: Root XML element
            file_path: Path to XML file
            
        Returns:
            Classification: 'data', 'rules', or 'generic'
        """
        file_name = Path(file_path).name.lower()
        root_tag = root.tag.lower()
        
        # Rules files patterns
        rules_patterns = ['rule', 'ruleset', 'rules', 'condition', 'policy', 'workflow', 'decision']
        if any(pattern in root_tag for pattern in rules_patterns):
            return 'rules'
        if any(pattern in file_name for pattern in ['rule', 'policy', 'workflow', 'decision']):
            return 'rules'
        
        # Check for rule-like child elements
        child_tags = [child.tag.lower() for child in root]
        if any(pattern in ' '.join(child_tags) for pattern in rules_patterns):
            return 'rules'
        
        # Data files patterns
        data_patterns = ['data', 'dataset', 'records', 'items', 'list', 'collection', 'entry', 'row']
        if any(pattern in root_tag for pattern in data_patterns):
            return 'data'
        if any(pattern in file_name for pattern in ['data', 'dataset', 'record', 'item']):
            return 'data'
        
        # Check for data-like child elements
        if any(pattern in ' '.join(child_tags) for pattern in data_patterns):
            return 'data'
        
        return 'generic'
    
    def parse_xml_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Parse XML file and extract structure.
        
        Args:
            file_path: Path to XML file
            
        Returns:
            Dictionary with parsed XML structure and chunks
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse XML
            try:
                root = ET.fromstring(content)
            except ET.ParseError as e:
                print(f"⚠️ XML parse error in {file_path}: {e}")
                return None
            
            # Classify XML type
            xml_type = self.classify_xml_type(root, file_path)
            
            # Extract chunks based on type
            if xml_type == 'rules':
                chunks = self._extract_rules_chunks(root, content, file_path)
            elif xml_type == 'data':
                chunks = self._extract_data_chunks(root, content, file_path)
            else:
                chunks = self._extract_generic_chunks(root, content, file_path)
            
            return {
                'language': 'xml',
                'file_path': file_path,
                'relative_path': self._get_relative_path(file_path),
                'file_content': content,
                'xml_type': xml_type,
                'root_element': root.tag,
                'chunks': chunks,
                'total_chunks': len(chunks)
            }
        except Exception as e:
            print(f"⚠️ Error parsing {file_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_relative_path(self, file_path: str) -> str:
        """Get relative path from repo root."""
        if not self.repo_path:
            return file_path
        try:
            return str(Path(file_path).relative_to(Path(self.repo_path)))
        except ValueError:
            return file_path
    
    def _extract_rules_chunks(self, root: ET.Element, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract chunks from XML rules files."""
        chunks = []
        relative_path = self._get_relative_path(file_path)
        
        # Find all rule elements (try common rule patterns)
        rule_elements = []
        for pattern in ['.//rule', './/Rule', './/RULE', './/policy', './/Policy', './/condition', './/Condition']:
            rule_elements.extend(root.findall(pattern))
        
        # If no specific rule elements found, treat root as a single rule
        if not rule_elements:
            rule_elements = [root]
        
        for idx, rule in enumerate(rule_elements):
            try:
                rule_text = ET.tostring(rule, encoding='unicode', method='xml')
            except Exception:
                # Fallback: use text content
                rule_text = ET.tostring(rule, encoding='unicode')
            
            # Extract rule metadata
            rule_name = rule.get('name') or rule.get('id') or rule.get('key') or f"rule_{idx}"
            rule_type = rule.get('type') or rule.get('ruleType') or 'generic'
            rule_id = rule.get('id') or rule.get('ruleId') or ''
            
            # Find description or summary
            description = ''
            desc_elem = rule.find('description') or rule.find('Description') or rule.find('summary') or rule.find('Summary')
            if desc_elem is not None and desc_elem.text:
                description = desc_elem.text.strip()
            
            # Calculate line numbers (approximate)
            rule_start = content.find(rule_text[:50]) if len(rule_text) > 50 else content.find(rule_text)
            start_line = content[:rule_start].count('\n') + 1 if rule_start >= 0 else 1
            end_line = start_line + rule_text.count('\n')
            
            chunk = {
                'type': 'xml_rule',
                'rule_name': rule_name,
                'rule_type': rule_type,
                'rule_id': rule_id,
                'rule_index': idx,
                'file_path': relative_path,
                'code': rule_text,
                'summary': f"Rule: {rule_name} (type: {rule_type})" + (f" - {description[:50]}" if description else ""),
                'description': description,
                'language': 'xml',
                'filetype': '.xml',
                'xml_type': 'rules',
                'start_line': start_line,
                'end_line': end_line
            }
            
            # Generate IDs
            chunk['chunk_id'] = self._generate_chunk_id(chunk)
            chunk['_id'] = self._generate_chunk_content_id(chunk)
            
            chunks.append(chunk)
        
        return chunks
    
    def _extract_data_chunks(self, root: ET.Element, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract chunks from XML data files."""
        chunks = []
        relative_path = self._get_relative_path(file_path)
        
        # Strategy 1: Extract by repeating child elements (e.g., <record>, <item>, <entry>)
        child_elements = list(root)
        
        if child_elements:
            # Group by element tag name
            element_groups = {}
            for child in child_elements:
                tag = child.tag
                if tag not in element_groups:
                    element_groups[tag] = []
                element_groups[tag].append(child)
            
            # Extract chunks for each group
            for tag, elements in element_groups.items():
                for idx, element in enumerate(elements):
                    try:
                        element_text = ET.tostring(element, encoding='unicode', method='xml')
                    except Exception:
                        element_text = ET.tostring(element, encoding='unicode')
                    
                    # Calculate line numbers
                    element_start = content.find(element_text[:50]) if len(element_text) > 50 else content.find(element_text)
                    start_line = content[:element_start].count('\n') + 1 if element_start >= 0 else 1
                    end_line = start_line + element_text.count('\n')
                    
                    # Extract element ID or key
                    element_id = element.get('id') or element.get('key') or element.get('name') or f"{tag}_{idx}"
                    
                    chunk = {
                        'type': 'xml_data',
                        'element_name': tag,
                        'element_id': element_id,
                        'element_index': idx,
                        'file_path': relative_path,
                        'code': element_text,
                        'summary': f"Data element: {tag} (id: {element_id})",
                        'language': 'xml',
                        'filetype': '.xml',
                        'xml_type': 'data',
                        'start_line': start_line,
                        'end_line': end_line
                    }
                    
                    # Generate IDs
                    chunk['chunk_id'] = self._generate_chunk_id(chunk)
                    chunk['_id'] = self._generate_chunk_content_id(chunk)
                    
                    chunks.append(chunk)
        
        # Strategy 2: If no child elements or chunks too large, chunk by size
        if not chunks or (chunks and any(len(c['code']) > self.max_chunk_size for c in chunks)):
            chunks = []
            lines = content.split('\n')
            chunk_size = self.max_chunk_size // 100  # Approximate lines per chunk
            
            for i in range(0, len(lines), chunk_size - self.chunk_overlap // 100):
                chunk_lines = lines[i:min(i + chunk_size, len(lines))]
                chunk_text = '\n'.join(chunk_lines)
                
                chunk = {
                    'type': 'xml_data',
                    'element_name': root.tag,
                    'element_index': i // chunk_size,
                    'file_path': relative_path,
                    'code': chunk_text,
                    'summary': f"XML data section {i // chunk_size + 1}",
                    'language': 'xml',
                    'filetype': '.xml',
                    'xml_type': 'data',
                    'start_line': i + 1,
                    'end_line': min(i + chunk_size, len(lines))
                }
                
                # Generate IDs
                chunk['chunk_id'] = self._generate_chunk_id(chunk)
                chunk['_id'] = self._generate_chunk_content_id(chunk)
                
                chunks.append(chunk)
        
        return chunks
    
    def _extract_generic_chunks(self, root: ET.Element, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract chunks from generic XML files."""
        chunks = []
        relative_path = self._get_relative_path(file_path)
        
        # Chunk by size (lines)
        lines = content.split('\n')
        chunk_size = self.max_chunk_size // 100  # Approximate lines per chunk
        
        for i in range(0, len(lines), chunk_size - self.chunk_overlap // 100):
            chunk_lines = lines[i:min(i + chunk_size, len(lines))]
            chunk_text = '\n'.join(chunk_lines)
            
            chunk = {
                'type': 'xml_generic',
                'element_name': root.tag,
                'element_index': i // chunk_size,
                'file_path': relative_path,
                'code': chunk_text,
                'summary': f"XML content section {i // chunk_size + 1}",
                'language': 'xml',
                'filetype': '.xml',
                'xml_type': 'generic',
                'start_line': i + 1,
                'end_line': min(i + chunk_size, len(lines))
            }
            
            # Generate IDs
            chunk['chunk_id'] = self._generate_chunk_id(chunk)
            chunk['_id'] = self._generate_chunk_content_id(chunk)
            
            chunks.append(chunk)
        
        return chunks
    
    def _generate_chunk_id(self, chunk: Dict[str, Any]) -> str:
        """Generate unique chunk ID based on location."""
        file_path = chunk.get('file_path', '')
        chunk_type = chunk.get('type', 'unknown')
        index = chunk.get('element_index', chunk.get('rule_index', 0))
        start_line = chunk.get('start_line', 1)
        end_line = chunk.get('end_line', 1)
        
        id_string = f"{file_path}::{chunk_type}::{index}::{start_line}::{end_line}"
        chunk_hash = hashlib.sha256(id_string.encode()).hexdigest()[:16]
        return f"xml_{chunk_hash}"
    
    def _generate_chunk_content_id(self, chunk: Dict[str, Any]) -> str:
        """Generate unique ID based on chunk content."""
        content_string = chunk.get('code', '') + chunk.get('file_path', '')
        content_hash = hashlib.sha256(content_string.encode()).hexdigest()
        return content_hash


class EmbeddingGenerator:
    """Generate embeddings for XML chunks."""
    
    def __init__(self, openai_api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        self.client = None
        self.model = model
        if openai_api_key and OPENAI_AVAILABLE:
            self.client = AsyncOpenAI(api_key=openai_api_key)
    
    async def generate_embeddings(self, chunks: List[Dict[str, Any]], batch_size: int = 100) -> List[Dict[str, Any]]:
        """Generate embeddings for chunks in batches."""
        if not self.client:
            print("⚠️ OpenAI client not available. Skipping embeddings.")
            return chunks
        
        print(f"🧮 Generating embeddings for {len(chunks)} chunks...")
        
        # Prepare texts for embedding
        texts = []
        for chunk in chunks:
            # Combine code and summary for better semantic understanding
            text = f"{chunk.get('summary', '')}\n{chunk.get('code', '')}"
            texts.append(text)
        
        # Generate embeddings in batches
        all_embeddings = []
        iterator = range(0, len(texts), batch_size)
        if TQDM_AVAILABLE:
            iterator = tqdm(iterator, desc="Generating embeddings")
        
        for i in iterator:
            batch_texts = texts[i:i + batch_size]
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch_texts
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"⚠️ Error generating embeddings for batch {i}: {e}")
                # Add empty embeddings for failed batch
                all_embeddings.extend([[]] * len(batch_texts))
        
        # Add embeddings to chunks
        for chunk, embedding in zip(chunks, all_embeddings):
            chunk['embedding'] = embedding
        
        print(f"✅ Generated {len([c for c in chunks if c.get('embedding')])} embeddings")
        return chunks


class OpenSearchIndexer:
    """Index XML chunks to OpenSearch."""
    
    def __init__(self, host: str, index_name: str, use_aws_auth: bool = False,
                 aws_region: str = 'us-east-1', verify_certs: bool = True):
        self.host = host
        self.index_name = index_name
        self.use_aws_auth = use_aws_auth
        self.aws_region = aws_region
        self.verify_certs = verify_certs
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize OpenSearch client."""
        if not OPENSEARCH_AVAILABLE:
            print("⚠️ OpenSearch libraries not available. Install: pip install opensearch-py aws-requests-auth boto3")
            return
        
        try:
            if self.use_aws_auth:
                # AWS authentication
                session = boto3.Session()
                credentials = session.get_credentials()
                awsauth = AWSRequestsAuth(
                    credentials,
                    self.aws_region,
                    'es'
                )
                self.client = OpenSearch(
                    hosts=[self.host],
                    http_auth=awsauth,
                    use_ssl=True,
                    verify_certs=self.verify_certs,
                    connection_class=RequestsHttpConnection
                )
            else:
                # Basic authentication or no auth
                self.client = OpenSearch(
                    hosts=[self.host],
                    use_ssl=True,
                    verify_certs=self.verify_certs
                )
            
            print(f"✅ Connected to OpenSearch: {self.host}")
        except Exception as e:
            print(f"⚠️ Error connecting to OpenSearch: {e}")
            self.client = None
    
    def ensure_index(self):
        """Create or update OpenSearch index with XML-specific mapping."""
        if not self.client:
            return False
        
        mapping = {
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "_id": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "file_path": {"type": "keyword"},
                    "code": {
                        "type": "text",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "summary": {"type": "text"},
                    "description": {"type": "text"},
                    "language": {"type": "keyword"},
                    "filetype": {"type": "keyword"},
                    "xml_type": {"type": "keyword"},  # 'data', 'rules', 'generic'
                    "rule_name": {"type": "keyword"},
                    "rule_type": {"type": "keyword"},
                    "rule_id": {"type": "keyword"},
                    "element_name": {"type": "keyword"},
                    "element_id": {"type": "keyword"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1536,  # OpenAI embedding dimension
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib"
                        }
                    }
                }
            },
            "settings": {
                "index": {
                    "knn": True,
                    "number_of_shards": 5,
                    "number_of_replicas": 1
                }
            }
        }
        
        try:
            if self.client.indices.exists(index=self.index_name):
                print(f"ℹ️ Index {self.index_name} already exists")
            else:
                self.client.indices.create(index=self.index_name, body=mapping)
                print(f"✅ Created index: {self.index_name}")
            return True
        except Exception as e:
            print(f"⚠️ Error ensuring index: {e}")
            return False
    
    def index_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 100):
        """Index chunks to OpenSearch in batches."""
        if not self.client:
            print("⚠️ OpenSearch client not available. Skipping indexing.")
            return
        
        if not chunks:
            print("⚠️ No chunks to index.")
            return
        
        print(f"📊 Indexing {len(chunks)} chunks to OpenSearch...")
        
        # Prepare bulk body
        bulk_body = []
        for chunk in chunks:
            # Use _id as document ID
            doc_id = chunk.get('_id', chunk.get('chunk_id'))
            
            # Prepare document (exclude _id from body, it's used as doc ID)
            doc = {k: v for k, v in chunk.items() if k != '_id'}
            
            bulk_body.append({"index": {"_index": self.index_name, "_id": doc_id}})
            bulk_body.append(doc)
        
        # Index in batches
        iterator = range(0, len(bulk_body), batch_size * 2)  # *2 because each chunk has 2 items (action + doc)
        if TQDM_AVAILABLE:
            iterator = tqdm(iterator, desc="Indexing to OpenSearch")
        
        for i in iterator:
            batch = bulk_body[i:i + batch_size * 2]
            try:
                response = self.client.bulk(body=batch)
                if response.get('errors'):
                    errors = [item for item in response['items'] if 'error' in item.get('index', {})]
                    if errors:
                        print(f"⚠️ {len(errors)} errors in batch {i // (batch_size * 2)}")
            except Exception as e:
                print(f"⚠️ Error indexing batch {i // (batch_size * 2)}: {e}")
        
        print(f"✅ Indexed {len(chunks)} chunks to {self.index_name}")


async def main():
    parser = argparse.ArgumentParser(description="Standalone XML Parser for Data and Rules Files")
    
    # Required arguments
    parser.add_argument("--repo-path", required=True, help="Path to repository root")
    parser.add_argument("--output-dir", default="./xml_output", help="Output directory for chunks JSON")
    
    # XML parsing options
    parser.add_argument("--max-chunk-size", type=int, default=2000, help="Maximum chunk size in characters")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap size")
    parser.add_argument("--exclude-patterns", nargs='+', help="Additional XML file patterns to exclude")
    
    # Embedding options
    parser.add_argument("--openai-api-key", help="OpenAI API key for embeddings")
    parser.add_argument("--embedding-model", default="text-embedding-3-small", help="Embedding model")
    parser.add_argument("--no-embeddings", action="store_true", help="Skip embedding generation")
    
    # OpenSearch options
    parser.add_argument("--opensearch-host", help="OpenSearch host URL")
    parser.add_argument("--opensearch-index", default="xml-chunks", help="OpenSearch index name")
    parser.add_argument("--use-aws-auth", action="store_true", help="Use AWS authentication for OpenSearch")
    parser.add_argument("--aws-region", default="us-east-1", help="AWS region for authentication")
    parser.add_argument("--no-verify-certs", action="store_true", help="Disable SSL certificate verification")
    
    args = parser.parse_args()
    
    # Initialize parser
    xml_parser = XMLParser(
        max_chunk_size=args.max_chunk_size,
        chunk_overlap=args.chunk_overlap
    )
    
    # Find XML files
    print(f"📁 Scanning for XML files in: {args.repo_path}")
    xml_files = xml_parser.find_xml_files(args.repo_path, args.exclude_patterns)
    print(f"   Found {len(xml_files)} XML files")
    
    if not xml_files:
        print("❌ No XML files found. Exiting.")
        return
    
    # Parse XML files
    print(f"\n📄 Parsing XML files...")
    all_chunks = []
    parsed_files = []
    
    iterator = xml_files
    if TQDM_AVAILABLE:
        iterator = tqdm(xml_files, desc="Parsing XML files")
    
    for xml_file in iterator:
        parsed = xml_parser.parse_xml_file(xml_file)
        if parsed:
            parsed_files.append(parsed)
            all_chunks.extend(parsed['chunks'])
    
    print(f"✅ Parsed {len(parsed_files)} XML files")
    print(f"   Generated {len(all_chunks)} chunks")
    
    # Statistics
    xml_types = {}
    for parsed in parsed_files:
        xml_type = parsed.get('xml_type', 'unknown')
        xml_types[xml_type] = xml_types.get(xml_type, 0) + 1
    
    print(f"\n📊 XML File Statistics:")
    print(f"   Rules files: {xml_types.get('rules', 0)}")
    print(f"   Data files: {xml_types.get('data', 0)}")
    print(f"   Generic files: {xml_types.get('generic', 0)}")
    
    # Generate embeddings if requested
    if not args.no_embeddings and args.openai_api_key:
        print(f"\n🧮 Generating embeddings...")
        embedding_gen = EmbeddingGenerator(
            openai_api_key=args.openai_api_key,
            model=args.embedding_model
        )
        all_chunks = await embedding_gen.generate_embeddings(all_chunks)
    
    # Save chunks to JSON
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    chunks_file = output_dir / "xml_chunks.json"
    output_data = {
        "repo_path": args.repo_path,
        "total_files": len(parsed_files),
        "total_chunks": len(all_chunks),
        "xml_types": xml_types,
        "timestamp": datetime.now().isoformat(),
        "chunks": all_chunks,
        "files": [
            {
                "file_path": p['file_path'],
                "relative_path": p['relative_path'],
                "xml_type": p['xml_type'],
                "root_element": p['root_element'],
                "total_chunks": p['total_chunks']
            }
            for p in parsed_files
        ]
    }
    
    with open(chunks_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Saved chunks to: {chunks_file}")
    
    # Index to OpenSearch if configured
    if args.opensearch_host:
        print(f"\n📊 Indexing to OpenSearch...")
        indexer = OpenSearchIndexer(
            host=args.opensearch_host,
            index_name=args.opensearch_index,
            use_aws_auth=args.use_aws_auth,
            aws_region=args.aws_region,
            verify_certs=not args.no_verify_certs
        )
        
        if indexer.client:
            indexer.ensure_index()
            indexer.index_chunks(all_chunks)
    
    print(f"\n✅ XML parsing complete!")
    print(f"   Files parsed: {len(parsed_files)}")
    print(f"   Chunks generated: {len(all_chunks)}")
    print(f"   Output: {chunks_file}")


if __name__ == "__main__":
    asyncio.run(main())

