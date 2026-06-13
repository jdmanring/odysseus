import unittest
import subprocess
import shutil
import tempfile
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

    def test_reinstall_aria2c(self):
        """
        Verify that BinManager performs a fresh installation if the binary is missing.
        """
        # 1. Get the current working binary
        original_path = BinManager.ensure_binary("aria2c")
        self.assertIsNotNone(original_path, "Setup failed: aria2c not found.")

        # 2. Create a backup and remove the original
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "aria2c_backup"

            # Move original out of the way
            shutil.move(str(original_path), str(backup_path))

            # 3. Ensure the binary is now "missing" from the manager's perspective
            self.assertIsNone(BinManager.get_binary_path("aria2c"), "BinManager still thinks aria2c is present")

            # 4. Attempt to re-install
            new_path = BinManager.ensure_binary("aria2c")

            # 5. Verify re-installation succeeded — the manager always uses the same
            # canonical install path, so new_path == original_path is correct.
            self.assertIsNotNone(new_path, "BinManager failed to re-install aria2c")
            self.assertTrue(new_path.exists(), "Re-installed binary does not exist")

            # 6. Verify it actually works
            result = subprocess.run([str(new_path), "--version"], capture_output=True, text=True, check=True)
            self.assertIn("aria2", result.stdout.lower())

            # 7. Clean up: Restore the original
            shutil.move(str(backup_path), str(original_path))

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
