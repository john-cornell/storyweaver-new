# Setup

## Python environment: venv only (no Anaconda)

This project uses a standard Python venv. **Do not use Anaconda** — use the system Python or python.org installer.

### 1. Deactivate Anaconda (if installed)

```powershell
conda deactivate
# Optional: prevent base from auto-activating
conda config --set auto_activate_base false
```

### 2. Create venv with system Python

Use `py` launcher (Windows) or `python3` (Unix):

```powershell
py -3.12 -m venv .venv
# Or: python -m venv .venv   (only if python points to system Python, NOT Anaconda)
```

### 3. Activate venv

```powershell
.venv\Scripts\activate
```

Your prompt should show `(.venv)` and **not** `(base)`. If you see `(base)`, conda is still active — run `conda deactivate` first.

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Run the app

```powershell
python app.py
```

To verify you're using venv Python (not Anaconda):

```powershell
python -c "import sys; print(sys.executable)"
# Should show: ...\storyweaver2\.venv\Scripts\python.exe
# NOT: C:\ProgramData\anaconda3\...
```
