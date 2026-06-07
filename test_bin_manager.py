from tooling.bin_manager import BinManager
import subprocess

def test_bin_manager():
    print("Testing BinManager...")
    
    # 1. Ensure aria2c is installed
    path = BinManager.ensure_binary("aria2c")
    
    if path:
        print(f"Successfully ensured binary at: {path}")
        
        # 2. Verify it's actually executable and returns a version
        try:
            result = subprocess.run([str(path), "--version"], capture_output=True, text=True, check=True)
            print("Binary verification successful!")
            print(f"Version output: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"Binary exists but failed to run: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
    else:
        print("Failed to ensure aria2c binary.")

if __name__ == "__main__":
    test_bin_manager()
