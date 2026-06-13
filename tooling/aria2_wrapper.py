import subprocess
from pathlib import Path
from typing import List, Optional, Dict
from tooling.bin_manager import BinManager

class Aria2Wrapper:
    """
    Wrapper for aria2c to handle Hugging Face downloads.
    Generates appropriate command-line arguments and executes the binary.
    """

    def __init__(self, connections: int = 16, split: int = 16):
        self.connections = connections
        self.split = split

    def build_command(
        self, 
        url: str, 
        destination: Path, 
        headers: Optional[Dict[str, str]] = None, 
        resume: bool = True
    ) -> List[str]:
        """
        Builds the aria2c command line arguments.
        """
        # Ensure binary is available
        binary_path = BinManager.ensure_binary("aria2c")
        if not binary_path:
            raise RuntimeError("aria2c binary could not be ensured. Downloader cannot proceed.")

        # Construct the command as a list for safe subprocess execution
        command = [str(binary_path)]
        command.append("--allow-overwrite=true")
        command.extend(["-x", str(self.connections)])
        command.extend(["-s", str(self.split)])
        command.extend(["-d", str(destination.parent)])
        command.extend(["-o", destination.name])
        
        if resume:
            command.append("-c")
            
        if headers:
            for key, value in headers.items():
                command.append(f"--header={key}: {value}")
                
        command.append(url)
        
        return command

    def dry_run(self, url: str, destination: Path, headers: Optional[Dict[str, str]] = None, resume: bool = True) -> str:
        """
        Returns the command that would be executed for verification.
        """
        command = self.build_command(url, destination, headers, resume)
        return " ".join([f'"{arg}"' if " " in arg else arg for arg in command])

    def execute(self, url: str, destination: Path, headers: Optional[Dict[str, str]] = None, resume: bool = True):
        """
        Executes the aria2c download.
        """
        command = self.build_command(url, destination, headers, resume)
        
        try:
            process = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True
            )
            return process.stdout
        except subprocess.CalledProcessError as e:
            print(f"aria2c execution failed: {e.stderr}")
            raise e

