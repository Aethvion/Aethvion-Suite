"""
Misaka Cipher - File Vector Store
Manages semantic indexing and search for workspace files.
"""

from pathlib import Path
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.utils import get_logger
from core.utils.paths import VAULT_SEARCH

logger = get_logger(__name__)

class FileVectorStore:
    """
    File Vector Store - Semantic search for workspace files.

    Uses FastEmbed for efficient local embeddings and ChromaDB for storage.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the File Vector Store.

        Args:
            storage_path: Path to ChromaDB storage.
        """
        if storage_path is None:
            storage_path = VAULT_SEARCH
        
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Lazy imports for better startup time
        import chromadb
        from chromadb.config import Settings
        from fastembed import TextEmbedding
        
        # Initialize FastEmbed
        logger.info("Initializing FastEmbed TextEmbedding model...")
        self.embedding_model = TextEmbedding() 
        
        # Initialize ChromaDB
        logger.info(f"Initializing ChromaDB at {self.storage_path}")
        self.client = chromadb.PersistentClient(
            path=str(self.storage_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        self.collection = self.client.get_or_create_collection(
            name="workspace_files",
            metadata={"description": "Semantic index for Misaka Cipher workspace files"}
        )
        
        logger.info("File Vector Store initialized successfully")

    def index_file(self, rel_path: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """
        Index or update a file in the vector store.
        
        Args:
            rel_path: Relative path of the file from workspace root.
            content: The text content of the file.
            metadata: Additional metadata (domain, created_at, etc).
        """
        try:
            # Generate embedding
            # FastEmbed process a list and returns a generator
            embeddings = list(self.embedding_model.embed([content]))
            embedding = embeddings[0].tolist()
            
            # Prepare metadata for ChromaDB (flatten lists/dicts)
            flattened_meta = {
                "path": rel_path,
                "indexed_at": datetime.now().isoformat()
            }
            if metadata:
                for k, v in metadata.items():
                    if isinstance(v, (list, dict)):
                        flattened_meta[k] = json.dumps(v)
                    else:
                        flattened_meta[k] = v
            
            # Upsert into collection
            self.collection.upsert(
                ids=[rel_path],
                embeddings=[embedding],
                documents=[content[:5000]], # ChromaDB stores documents for retrieval too, capped for efficiency
                metadatas=[flattened_meta]
            )
            
            logger.info(f"Indexed file: {rel_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to index file {rel_path}: {e}")
            return False

    def search(self, query: str, limit: int = 10, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for files semantically.
        
        Args:
            query: Semantic search query.
            limit: Max results to return.
            domain: Optional domain filter.
            
        Returns:
            List of results with paths and scores.
        """
        try:
            # Generate query embedding
            query_embeddings = list(self.embedding_model.embed([query]))
            query_vector = query_embeddings[0].tolist()
            
            # Filter by domain if provided
            where = {"domain": domain} if domain else None
            
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=limit,
                where=where
            )
            
            formatted_results = []
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    "path": results['ids'][0][i],
                    "score": results['distances'][0][i], # Distance, lower is better
                    "metadata": results['metadatas'][0][i],
                    "excerpt": results['documents'][0][i][:200] + "..."
                })
                
            return formatted_results
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def remove_file(self, rel_path: str):
        """Remove a file from the index."""
        try:
            self.collection.delete(ids=[rel_path])
            logger.info(f"Removed from index: {rel_path}")
        except Exception as e:
            logger.error(f"Failed to remove file from index: {e}")

# Global singleton
_file_vector_store = None

def get_file_vector_store() -> FileVectorStore:
    """Get the global FileVectorStore instance."""
    global _file_vector_store
    if _file_vector_store is None:
        _file_vector_store = FileVectorStore()
    return _file_vector_store
