"""
Aethvion Suite - Model Downloader
Handles downloading models from Hugging Face
"""

import os
from pathlib import Path
from typing import Optional, Callable
from huggingface_hub import hf_hub_download
from core.utils.logger import get_logger

logger = get_logger(__name__)

class ModelDownloader:
    """
    Utility for downloading models from Hugging Face.
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            from core.utils.paths import LOCAL_MODELS_GGUF
            self.base_dir = LOCAL_MODELS_GGUF
        else:
            self.base_dir = Path(base_dir)
            
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def download_model(
        self, 
        repo_id: str, 
        filename: str, 
        subfolder: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """
        Download a model from Hugging Face.
        
        Args:
            repo_id: HF repo ID (e.g. "unsloth/Llama-3.2-1B-Instruct-GGUF")
            filename: Name of the file to download (e.g. "Llama-3.2-1B-Instruct-Q4_K_M.gguf")
            subfolder: Optional subfolder within the repo
            
        Returns:
            Path to the downloaded file
        """
        logger.info(f"Starting download of {filename} from {repo_id}...")
        
        try:
            # Download file
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                subfolder=subfolder,
                local_dir=str(self.base_dir),
                local_dir_use_symlinks=False
            )
            
            logger.info(f"Model downloaded successfully to {path}")
            return Path(path)
            
        except Exception as e:
            logger.error(f"Failed to download model: {str(e)}")
            raise e
