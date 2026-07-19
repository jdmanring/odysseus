import os
import platform
import subprocess
import shutil
import tarfile
import zipfile
import urllib.request
from pathlib import Path
from typing import Dict, Tuple, Optional, List

class BinManager:
    """
    Manages standalone binaries for the Cookbook. 
    Handles OS/Architecture detection, automated fetching from remote sources,
    installation to a local bin directory, and permission management.
    """
    
    # Directory where binaries will be stored
    BIN_DIR = Path.home() / ".cookbook" / "bin"
    
    # Tool mapping: { tool_name: { (os, arch): (url, archive_type, binary_name) } }
    # archive_type: 'tar.gz', 'zip', or 'raw'
    # binary_name: The name of the executable inside the archive or the resulting file
    TOOL_MAP: Dict[str, Dict[Tuple[str, str], Tuple[str, str, str]]] = {
        "aria2c": {
            # Linux x86_64
            ("Linux", "x86_64"): (
                "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-x86_64-linux-musl_static.zip", 
                "zip", 
                "aria2c"
            ),
            # Linux AArch64
            ("Linux", "aarch64"): (
                "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-aarch64-linux-musl_static.zip", 
                "zip", 
                "aria2c"
            ),
            # macOS Intel
            ("Darwin", "x86_64"): (
                "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-x86_64-darwin_static.zip", 
                "zip", 
                "aria2c"
            ),
            # macOS ARM (M1/M2/M3)
            ("Darwin", "arm64"): (
                "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-arm64-darwin_static.zip", 
                "zip", 
                "aria2c"
            ),
            # Windows x86_64
            ("Windows", "AMD64"): (
                "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-x86_64-w64-mingw32_static.zip", 
                "zip", 
                "aria2c.exe"
            ),
        }
    }

    @classmethod
    def get_platform(cls) -> Tuple[str, str]:
        """
        Detects the current operating system and architecture.
        Returns: (os_name, arch_name)
        """
        os_name = platform.system() # 'Linux', 'Darwin', 'Windows'
        arch_name = platform.machine() # 'x86_64', 'aarch64', 'AMD64' (Windows)
        
        # Normalize architecture names.
        # macOS arm64 (M1/M2/M3) and Linux aarch64 are kept distinct because the
        # TOOL_MAP uses ("Darwin", "arm64") vs ("Linux", "aarch64") to match the
        # different static build filenames.
        if os_name == "Windows" and arch_name.upper() == "AMD64":
            arch_name = "AMD64"
        elif arch_name.lower() in ["x86_64", "amd64"]:
            arch_name = "x86_64"
        elif arch_name.lower() == "aarch64":
            arch_name = "aarch64"          # Linux ARM servers
        elif arch_name.lower() == "arm64":
            arch_name = "arm64"            # macOS Apple Silicon
            
        return os_name, arch_name

    @classmethod
    def ensure_binary(cls, tool_name: str) -> Optional[Path]:
        """
        Ensures a tool's binary is present and executable.
        If missing or incorrect for the platform, it will be downloaded and installed.
        
        Returns: Path to the binary if successful, None otherwise.
        """
        os_name, arch_name = cls.get_platform()
        platform_key = (os_name, arch_name)
        
        # Check if tool is supported on this platform
        if tool_name not in cls.TOOL_MAP or platform_key not in cls.TOOL_MAP[tool_name]:
            print(f"[BinManager] Tool '{tool_name}' is not supported on {os_name} {arch_name}")
            return None
            
        binary_path = cls.BIN_DIR / (tool_name if os_name != "Windows" else f"{tool_name}.exe")
        
        # 1. Check if binary already exists and is executable
        if binary_path.exists():
            if os.access(binary_path, os.X_OK):
                return binary_path
        
        # 2. Binary missing or not executable, proceed to install
        print(f"[BinManager] Installing {tool_name} for {os_name} {arch_name}...")
        url, archive_type, binary_name = cls.TOOL_MAP[tool_name][platform_key]
        
        try:
            cls.BIN_DIR.mkdir(parents=True, exist_ok=True)
            archive_path = cls.BIN_DIR / f"{tool_name}_temp_archive.{archive_type.split('.')[-1]}"
            
            # Download archive
            with urllib.request.urlopen(url) as response:
                with open(archive_path, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
            
            # Extract binary
            if archive_type == "tar.gz":
                with tarfile.open(archive_path, "r:gz") as tar:
                    # Find the binary in the archive (it might be in a subfolder)
                    members = [m for m in tar.getmembers() if m.name.endswith(binary_name)]
                    if not members:
                        raise FileNotFoundError(f"Binary {binary_name} not found in {archive_type} archive")
                    tar.extract(members[0], path=cls.BIN_DIR)
            elif archive_type == "zip":
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    # Find the binary in the zip
                    binary_in_zip = next((name for name in zip_ref.namelist() if name.endswith(binary_name)), None)
                    if not binary_in_zip:
                        raise FileNotFoundError(f"Binary {binary_name} not found in zip archive")
                    
                    # Extract and move to root of BIN_DIR if it's in a subfolder
                    source = zip_ref.extract(binary_in_zip, path=cls.BIN_DIR)
                    dest = cls.BIN_DIR / binary_name
                    shutil.move(source, dest)
            else:
                raise ValueError(f"Unsupported archive type: {archive_type}")
                
            # Clean up archive
            if archive_path.exists():
                os.remove(archive_path)
                
            # 3. Set permissions for Unix-like systems
            if os_name != "Windows":
                binary_path = cls.BIN_DIR / binary_name
                # Ensure the extracted binary is at the target path
                if binary_path.name != tool_name:
                    # Some archives extract as 'aria2c-1.37.0-linux-x86_64'
                    # We want it named simply 'aria2c'
                    shutil.move(str(binary_path), str(cls.BIN_DIR / tool_name))
                    binary_path = cls.BIN_DIR / tool_name
                    
                binary_path.chmod(0o755)
                
            return binary_path
            
        except Exception as e:
            print(f"[BinManager] Failed to install {tool_name}: {e}")
            return None

    @classmethod
    def get_binary_path(cls, tool_name: str) -> Optional[Path]:
        """
        Convenience method to check if a binary exists and return its path.
        Does NOT attempt to install.
        """
        os_name = platform.system()
        binary_name = tool_name if os_name != "Windows" else f"{tool_name}.exe"
        path = cls.BIN_DIR / binary_name
        if path.exists() and os.access(path, os.X_OK):
            return path
        return None
