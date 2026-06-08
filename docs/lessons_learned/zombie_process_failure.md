# TROUBLESHOOTING: ZOMBIE PROCESSES & DOUBLE-DOWNLOADS

## 🚨 THE CRITICAL FAILURE PATTERN
A high-severity failure occurs when the system attempts to "clean up" processes using a unique port but fails to account for **legacy processes** running on the default port.

### The "Double-Download" Scenario:
1. An old process (Zombie A) is running on the legacy default port (**6800**).
2. A new version of the code calculates a unique port (e.g., **6842**) and starts a new process (Process B).
3. The "Surgical Cleanup" logic only kills whatever is on port **6842**.
4. **Result:** Both Zombie A and Process B are now downloading the same files simultaneously.
5. **Symptom:** Data usage/download size exactly doubles (e.g., 18GB becomes 36GB).

## 🛠️ THE MANDATORY REMEDIATION
Whenever implementing a cleanup routine for external processes (`aria2c`, etc.), you **MUST** use a multi-stage purge:

### 1. Specific Target Kill
Kill the process associated with the current unique port.
`fuser -k [PORT]/tcp`

### 2. Legacy Port Purge
**Always** attempt to kill the legacy default port, regardless of the current port.
`fuser -k 6800/tcp`

### 3. Process Name Wipe
Use a broad `pkill` to ensure no orphaned coordinators or helper scripts remain.
`pkill -9 aria2c`
`pkill -9 -f aria2c_download.py`

## ⚠️ AI OPERATIONAL RULE
If a user reports that download sizes are doubling or that "too many files are downloading at once," **immediately assume a zombie process on port 6800** and execute the full purge sequence. Do not assume the "surgical" cleanup was sufficient.
