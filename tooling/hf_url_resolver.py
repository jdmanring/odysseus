import os
from typing import List, Tuple, Optional
from huggingface_hub import HfApi

class HfUrlResolver:
    """
    Resolves Hugging Face repository files to direct download URLs.
    """
    
    def __init__(self, token: Optional[str] = None):
        self.api = HfApi(token=token)

    def resolve_snapshot_urls(self, repo_id: str, include: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Returns a list of (url, relative_path) for all files in a repo snapshot.
        """
        files = self.api.list_repo_files(repo_id)
        
        # Filter files based on include pattern (simple glob-like)
        # For a more robust implementation, we could use fnmatch
        if include:
            import fnmatch
            files = [f for f in files if fnmatch.fnmatch(f, include)]
        
        urls = []
        for file_path in files:
            # Construct the direct download URL
            # Pattern: https://huggingface.co/{repo_id}/resolve/main/{file_path}
            # We use 'main' as default branch; a more complete version would check the default branch.
            url = f"https://huggingface.co/{repo_id}/resolve/main/{file_path}"
            urls.append((url, file_path))
            
        return urls
