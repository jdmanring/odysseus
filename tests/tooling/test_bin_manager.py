import unittest
import subprocess
from pathlib import Path
from tooling.bin_manager import BinManager

class TestBinManager(unittest.TestCase):
    """
    Comprehensive tests for the BinManager utility.
    Ensures binary resolution, installation, and verification.
    """

    def test_ensure_binary_aria2c(self):
        """
        Verify that BinManager can correctly identify or ensure the presence
        of the aria2c binary.
        """
        path = BinManager.ensure_binary("aria2c")
        
        # The binary should be found (either in system path or installed by manager)
        self.assertIsNotNone(path, "BinManager failed to find or install aria2c")
        self.assertTrue(Path(path).exists(), f"BinManager returned path {path} but it does not exist on disk")
        self.assertTrue(Path(path).is_file(), f"BinManager returned path {path} but it is not a file")

    def test_binary_execution(self):
        """
        Verify that the binary returned by BinManager is actually executable
        and responds to version queries.
        """
        path = BinManager.ensure_binary("aria2c")
        self.assertIsNotNone(path, "Cannot test execution because binary was not found")
        
        try:
            # Running --version is a safe way to verify the binary is functional
            result = subprocess.run(
                [str(path), "--version"], 
                capture_output=True, 
                text=True, 
                check=True,
                timeout=5
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("aria2", result.stdout.lower())
        except subprocess.CalledProcessError as e:
            self.fail(f"Binary at {path} failed to execute: {e}")
        except subprocess.TimeoutExpired:
            self.fail(f"Binary at {path} timed out during version check")

    def test_invalid_binary_resolution(self):
        """
        Verify that BinManager handles requests for non-existent/unsupported binaries gracefully.
        """
        # We use a random string that is unlikely to be a binary the manager knows how to install
        invalid_bin = "non_existent_binary_xyz_123"
        path = BinManager.ensure_binary(invalid_bin)
        
        # Depending on the implementation, this should return None or raise a specific error
        # Assuming the current implementation returns None on failure
        self.assertIsNone(path, f"BinManager should not have resolved the invalid binary: {invalid_bin}")

if __name__ == "__main__":
    unittest.main()
