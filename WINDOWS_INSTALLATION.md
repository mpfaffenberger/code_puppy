# Windows Installation Guide

## 🐶 Quick Start for Windows Users

Code Puppy works great on Windows, but there's **one important setup step** you need to do first to avoid build errors with certain dependencies.

## TL;DR - The Essential Fix

Before installing Code Puppy on Windows, you **must enable long path support**. This takes 30 seconds:

### Option 1: PowerShell Script (Recommended)

```powershell
# Run PowerShell as Administrator, then:
cd path\to\code-puppy
.\scripts\windows_setup.ps1
```

### Option 2: Manual Registry Edit

```powershell
# Run PowerShell as Administrator, then:
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

### Option 3: Python Setup Script

```bash
# Run as Administrator:
python scripts/setup_windows.py
```

## Why Is This Needed?

### The Problem

Windows has a legacy path-length limitation:
- **Maximum path length**: 260 characters
- **Maximum object file path**: 250 characters

When building certain Python packages (like `winsdk` for Windows OCR features), the build tools create deeply nested temporary directories that exceed this limit, causing errors like:

```
fatal error C1083: Cannot open compiler generated file: '': Invalid argument
```

Or warnings like:

```
CMake Warning: The object file directory has 175 characters.
The maximum full path to an object file is 250 characters.
```

### The Solution

Modern Windows (10 version 1607+, Windows 11) supports paths longer than 260 characters, but this feature is **disabled by default** for backwards compatibility. Enabling it is safe and recommended by Microsoft.

## Detailed Setup Instructions

### Method 1: Automated PowerShell Setup (Easiest)

1. **Clone or download the repository**:
   ```powershell
   git clone https://gecgithub01.walmart.com/genaica/code-puppy.git
   cd code-puppy
   ```

2. **Run the setup script as Administrator**:
   ```powershell
   # Right-click PowerShell -> "Run as Administrator"
   .\scripts\windows_setup.ps1
   ```

3. **Restart your computer** (recommended for changes to take full effect)

4. **Install Code Puppy**:
   ```bash
   uvx code-puppy -i
   ```

### Method 2: Manual Registry Edit

If you prefer to do it manually:

1. **Open PowerShell as Administrator**:
   - Press `Win + X`
   - Select "Windows PowerShell (Admin)" or "Terminal (Admin)"

2. **Enable long paths**:
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```

3. **Optionally enable for Python specifically**:
   ```powershell
   New-ItemProperty -Path "HKLM:\SOFTWARE\Python\PythonCore" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```

4. **Restart your computer**

5. **Verify it worked**:
   ```powershell
   Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled"
   ```
   Should show: `LongPathsEnabled : 1`

### Method 3: Group Policy Editor (For Enterprise)

If you're on Windows Pro or Enterprise:

1. Press `Win + R`, type `gpedit.msc`, press Enter
2. Navigate to: `Computer Configuration > Administrative Templates > System > Filesystem`
3. Find: `Enable Win32 long paths`
4. Set it to: `Enabled`
5. Click OK and restart your computer

## Verification

After enabling long paths, verify it worked:

```powershell
# Check registry value
Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled"

# Or use the Python helper
python scripts/setup_windows.py
```

You should see confirmation that long paths are enabled.

## Installation After Setup

Once long paths are enabled, install Code Puppy normally:

```bash
# Using uvx (recommended)
uvx code-puppy -i

# Or using pip
pip install code-puppy
```

## Troubleshooting

### "Access Denied" when running scripts

**Solution**: You need Administrator privileges. Right-click PowerShell and select "Run as Administrator".

### Setup script says "Execution Policy" error

**Solution**: Run PowerShell with bypass:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows_setup.ps1
```

### Still getting path-length errors after enabling long paths

**Solutions**:

1. **Restart your computer** - Changes require a reboot to take full effect

2. **Use shorter cache directory** - Set a custom UV cache location:
   ```powershell
   $env:UV_CACHE_DIR="C:\uv-cache"
   # Or set permanently:
   [System.Environment]::SetEnvironmentVariable("UV_CACHE_DIR", "C:\uv-cache", "User")
   ```

3. **Use subst for even shorter paths**:
   ```powershell
   subst P: C:\Users\YourName\path\to\code-puppy
   cd P:\
   uvx code-puppy -i
   ```

### Build still fails for winsdk

If you're still having issues with `winsdk` specifically:

1. **Check if pre-built wheel exists**:
   ```bash
   pip download winsdk --only-binary=:all:
   ```

2. **Try installing from Walmart artifactory** (may have pre-built wheels):
   ```bash
   pip install winsdk --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --trusted-host pypi.ci.artifacts.walmart.com
   ```

3. **Skip GUI-Cub features** - If you don't need Windows OCR capabilities, you can install without GUI-Cub dependencies (though this is not officially supported).

## Alternative: Docker/WSL2

If you don't want to modify Windows registry settings, you can run Code Puppy in WSL2:

```bash
# In WSL2 Ubuntu/Debian:
curl -LsSf https://astral.sh/uv/install.sh | sh
uvx code-puppy -i
```

No long-path configuration needed in Linux!

## Security & Safety

**Is enabling long paths safe?**

Yes! This is an officially supported Windows feature:
- Recommended by Microsoft for modern applications
- Required by many development tools (Git, Node.js, etc.)
- Does not affect system stability or security
- Only affects how the filesystem handles path lengths
- Can be safely disabled later if needed (though you won't want to)

**What does it change?**
- Allows paths longer than 260 characters
- Required by modern development workflows
- Does NOT weaken security or system protection
- Does NOT affect other applications negatively

## References

- [Microsoft: Enable Long Paths in Windows 10](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)
- [Microsoft: Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
- [Python: Windows Long Path Support](https://docs.python.org/3/using/windows.html#removing-the-max-path-limitation)

## Support

If you're still having issues after following this guide:

1. Check the [main README](README.md) for general troubleshooting
2. See [WINDOWS_DPI_SETUP.md](WINDOWS_DPI_SETUP.md) for DPI-related issues
3. See [WINDOWS_UNICODE_FIX.md](WINDOWS_UNICODE_FIX.md) for Unicode issues
4. Open an issue on GitHub with:
   - Your Windows version (`winver`)
   - Output of the setup script
   - Full error message from installation

---

**🐶 Happy coding with Code Puppy on Windows! 🐶**
