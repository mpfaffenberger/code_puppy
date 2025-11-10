# Research Prompt: Alternatives to Admin-Required Windows Long Path Fix for winsdk Installation

## Context

I'm working on Code Puppy, a Python-based AI code generation tool. On Windows, we're encountering a build failure when installing the `winsdk` dependency due to Windows path-length limitations. I've implemented an admin-required solution but would like to explore **non-admin alternatives**.

## Current Problem

### The Error

When installing Code Puppy on Windows via `uvx code-puppy -i` or `pip install code-puppy`, the build fails with:

```
fatal error C1083: Cannot open compiler generated file: '': Invalid argument
```

With preceding warning:

```
CMake Warning in CMakeLists.txt:
  The object file directory
  C:/Users/USERNAME/AppData/Local/uv/cache/sdists-v9/index/.../winsdk/1.0.0b10/.../src/_skbuild/win-amd64-3.13/cmake-build/CMakeFiles/_winrt.dir/./
  has 175 characters. The maximum full path to an object file is 250 characters.
  Object file pywinrt/winsdk/src/py.Windows.ApplicationModel.Appointments.AppointmentsProvider.cpp.obj
  cannot be safely placed under this directory.
```

### Technical Details

**Package**: `winsdk==1.0.0b10` (Python bindings for Windows SDK/WinRT)

**Build System**: CMake + scikit-build + MSVC C++ compiler

**Package Manager**: `uv` (modern Python package manager from Astral)

**Cache Location**: `C:\Users\USERNAME\AppData\Local\uv\cache\sdists-v9\index\7836150ccc289c44\winsdk\1.0.0b10\...`

**Path Length Issue**:
- Object file directory path: ~175 characters
- Plus object filename: ~80 characters  
- **Total**: ~255 characters
- **Windows limit**: 250 characters for object files, 260 for general paths

**Windows Version**: Windows 10/11 (modern versions with long path support available but disabled by default)

**Python Version**: 3.13.5

**Use Case**: winsdk is required for Windows-native OCR functionality (GUI automation features)

### Dependency Declaration

```toml
# In pyproject.toml
"winsdk>=1.0.0b10; sys_platform == 'win32'",
```

## Current Solution (Admin Required)

I've implemented a solution that enables Windows Long Path Support:

### Approach

1. **PowerShell/Python setup scripts** that modify the registry:
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" 
     -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```

2. **Registry Key Modified**: `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`

3. **Requires**:
   - Administrator privileges
   - Computer restart (recommended for full effect)

4. **Result**: Allows paths up to 32,767 characters instead of 260

### Why This Works

Windows 10 (version 1607+) and Windows 11 support long paths, but the feature is disabled by default for backwards compatibility. Enabling it allows modern applications and build tools to use longer paths.

### Downsides

❌ Requires administrator privileges (blocking for some corporate environments)
❌ Requires system restart for full effect
❌ Modifies global system settings
❌ Users may be hesitant to run scripts as admin

## What I'm Looking For

**I need alternatives that:**
1. ✅ **Do NOT require administrator privileges**
2. ✅ Work with `uv` package manager
3. ✅ Work with modern Python (3.11+)
4. ✅ Don't break the user's existing setup
5. ✅ Can be automated/scripted (no manual steps per install)

## Options I've Considered

### Option 1: Use Shorter Cache Path (Partial Solution)

**Approach**: Set `UV_CACHE_DIR` environment variable to shorter path

```bash
# User-level (no admin)
export UV_CACHE_DIR="C:\uv"
# or
export UV_CACHE_DIR="C:\tmp\uv"
```

**Pros**:
- ✅ No admin required
- ✅ Reduces path length significantly

**Cons**:
- ⚠️ May still hit 250-char limit depending on username/paths
- ⚠️ Doesn't solve the root cause
- ⚠️ Requires user to set environment variable
- ❓ Unknown if this alone is sufficient

**Status**: Documented as fallback option, but uncertain if it fully solves the issue.

---

### Option 2: Use `subst` for Virtual Drive (Temporary Workaround)

**Approach**: Map project directory to short drive letter

```bash
subst P: C:\Users\USERNAME\path\to\project
cd P:\
uvx code-puppy -i
```

**Pros**:
- ✅ No admin required
- ✅ Dramatically shortens paths

**Cons**:
- ❌ Temporary (lost on reboot unless scripted)
- ❌ Manual steps required
- ❌ Not user-friendly
- ❌ Doesn't help with cache directories

**Status**: Documented but not recommended.

---

### Option 3: Use Pre-Built Wheels

**Approach**: Find or host pre-built `winsdk` wheels to avoid compilation

**Where to look**:
- Official PyPI (may not have wheels for all Python versions)
- Walmart's internal Artifactory: `https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple`
- Build our own wheels and host them

**Pros**:
- ✅ No admin required
- ✅ No compilation = no path issues
- ✅ Faster installation

**Cons**:
- ❓ Unknown if pre-built wheels exist for `winsdk==1.0.0b10` + Python 3.13
- ❌ Maintenance burden if we host our own
- ❌ May not exist for all platform/Python combinations

**Status**: Need to research availability.

---

### Option 4: Make winsdk Optional

**Approach**: Make Windows OCR features optional via extras

```toml
[project.optional-dependencies]
windows-ocr = ["winsdk>=1.0.0b10"]
```

**Pros**:
- ✅ No admin required for base installation
- ✅ Users can opt-in to OCR features

**Cons**:
- ⚠️ Reduces out-of-box functionality on Windows
- ⚠️ Doesn't solve the problem for users who need OCR
- ❌ May confuse users about feature availability

**Status**: Possible fallback, but not ideal.

---

### Option 5: Use Alternative OCR Library

**Approach**: Replace winsdk with a different Windows OCR solution

**Alternatives**:
- `pytesseract` (already included, but less accurate than native Windows OCR)
- `easyocr` (deep learning-based, large dependency)
- `paddleocr` (another ML-based option)
- Direct Windows.Media.Ocr COM automation (without winsdk)

**Pros**:
- ✅ No admin required
- ✅ Avoids winsdk entirely

**Cons**:
- ⚠️ May be less accurate than native Windows OCR
- ⚠️ Larger dependencies (for ML-based options)
- ❌ Requires rewriting existing OCR integration code

**Status**: Backup plan if no other solution works.

---

### Option 6: Use WSL2 or Docker

**Approach**: Run Code Puppy in Linux environment on Windows

**Pros**:
- ✅ No Windows path limits
- ✅ No admin required (for WSL2 setup, if already installed)

**Cons**:
- ❌ Can't access native Windows OCR from WSL2/Docker
- ❌ Requires WSL2 or Docker installation
- ❌ Not a native Windows solution
- ❌ GUI automation may not work properly

**Status**: Valid alternative but defeats the purpose of Windows-native features.

---

### Option 7: Pin to Older winsdk Version

**Approach**: Try `winsdk==1.0.0b9` or earlier

```toml
"winsdk==1.0.0b9; sys_platform == 'win32'",
```

**Pros**:
- ✅ No admin required if older version has shorter paths
- ✅ Simple change

**Cons**:
- ❓ Unknown if older versions work
- ❓ May have bugs or missing features
- ⚠️ Just kicking the can down the road

**Status**: Could try, but feels like a band-aid.

---

### Option 8: Modify CMake Build Configuration

**Approach**: Patch winsdk's build to use shorter intermediate paths

**Ideas**:
- Set `CMAKE_OBJECT_PATH_MAX` to allow longer paths
- Modify `setup.py` / `pyproject.toml` to use shorter build directory
- Override `_skbuild` directory location

**Pros**:
- ✅ No admin required
- ✅ Addresses root cause

**Cons**:
- ❌ Complex - requires forking/patching winsdk
- ❌ Maintenance burden
- ❓ May not be possible without deep CMake knowledge

**Status**: High complexity, low confidence.

---

### Option 9: Per-User Long Path Setting

**Approach**: Check if there's a user-level (HKCU) registry setting

**Research needed**:
- Does `HKCU\...\LongPathsEnabled` exist?
- Would applications/build tools respect it?

**Pros**:
- ✅ No admin required
- ✅ User-scoped

**Cons**:
- ❓ Unknown if this exists or works

**Status**: Need to research.

---

### Option 10: Use Python's Manifest to Enable Long Paths

**Approach**: Embed long path awareness in Python executable manifest

**Details**: Python 3.6+ can be built with a manifest that declares long path awareness:
```xml
<application xmlns="urn:schemas-microsoft-com:asm.v3">
  <windowsSettings>
    <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
  </windowsSettings>
</application>
```

**Pros**:
- ✅ No admin required
- ✅ Per-application setting

**Cons**:
- ❓ Does `uv`'s managed Python have this?
- ❓ Would it apply to child processes (CMake, ninja, cl.exe)?
- ❌ May not affect build tools

**Status**: Worth investigating.

---

## Questions for Research

### High Priority

1. **Are there pre-built wheels for `winsdk==1.0.0b10` for Python 3.11-3.13 on Windows?**
   - Where can I find them?
   - Are they on PyPI, or do I need to check alternative sources?

2. **Is there a per-user (non-admin) registry setting for long paths?**
   - Would `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\...` work?
   - Would build tools (CMake, MSVC) respect it?

3. **Can I set `UV_CACHE_DIR` to `C:\uv` or `C:\tmp\uv` and avoid the 250-char limit?**
   - What's the shortest safe path?
   - Will this alone solve the issue, or are there other long paths in the build?

4. **Does Python's long path manifest affect child processes (CMake, cl.exe)?**
   - If I ensure Python has the manifest, will builds work?
   - Can I patch uv's managed Python to include this?

5. **Can I modify winsdk's build process without forking?**
   - Environment variables to shorten paths?
   - `setup.py` / `pyproject.toml` overrides?
   - CMake configuration flags?

### Medium Priority

6. **What's the shortest possible path I can use for UV_CACHE_DIR on Windows?**
   - `C:\u` (2 chars base)?
   - Are there restrictions on directory names?

7. **Can I pre-compile winsdk and distribute wheels myself?**
   - How to build wheels on a machine with long paths enabled?
   - Where to host them (GitHub Releases, Artifactory, etc.)?

8. **Are there alternative Windows OCR libraries that don't require compilation?**
   - Pure Python solutions?
   - Wheels available for all Python versions?

9. **Does `winsdk==1.0.0b9` or earlier versions avoid the path length issue?**
   - Are they compatible with Python 3.13?
   - What features are missing?

10. **Can I use `PEP 660` editable installs or build isolation options to control paths?**
    - `pip install --no-build-isolation`?
    - Custom build backends?

### Low Priority

11. **Are there Windows API calls to enable long paths for current process only?**
    - SetDllDirectory, SetCurrentDirectory with `\\?\` prefix?
    - Would this help build tools?

12. **Can I use junction points / symbolic links to shorten cache paths?**
    - Similar to `subst` but persistent?
    - Would `uv` follow them correctly?

## Ideal Solution Characteristics

**Must Have**:
- ✅ No administrator privileges required
- ✅ Automated (scriptable, no manual steps)
- ✅ Works with `uv` package manager
- ✅ Compatible with Python 3.11-3.13
- ✅ Doesn't break existing functionality

**Nice to Have**:
- ✅ No system restart required
- ✅ Works out-of-box for new users
- ✅ Doesn't require environment variable setup
- ✅ Maintains full Windows OCR functionality
- ✅ Low maintenance burden

## Technical Environment

**Operating System**: Windows 10 (1607+) / Windows 11

**Python Version**: 3.11, 3.12, 3.13

**Package Manager**: `uv` (from Astral, modern pip replacement)

**Build Tools**: CMake 3.x, MSVC 19.x (Visual Studio 2022), Ninja

**Corporate Environment**: Walmart (restricted admin access, behind proxy)

**Proxy Settings**:
```bash
HTTP_PROXY=http://sysproxy.wal-mart.com:8080
HTTPS_PROXY=http://sysproxy.wal-mart.com:8080
```

**Internal Artifactory**: `https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple`

## Request

Please research and provide:

1. **Evaluation of each option above** - feasibility, pros/cons, implementation details

2. **Additional alternatives** I haven't considered

3. **Recommended approach(es)** with step-by-step implementation

4. **Specific commands/code** to test proposed solutions

5. **Known limitations** or gotchas for each approach

6. **Answers to the questions** listed above (especially high priority ones)

## Output Format

Please structure your response as:

```markdown
# Research Results: winsdk Installation Alternatives (No Admin Required)

## Executive Summary
[Quick summary of best options]

## Detailed Analysis

### Option X: [Name]
**Feasibility**: High/Medium/Low
**Complexity**: High/Medium/Low
**Recommended**: Yes/No/Maybe

[Details...]

## Recommended Approaches

### Approach 1: [Name]
[Step-by-step implementation]

### Approach 2: [Name]
[Step-by-step implementation]

## Answers to Specific Questions

1. Question 1...
   Answer: ...

## Additional Considerations
[Other insights, warnings, etc.]
```

## References

- [winsdk PyPI](https://pypi.org/project/winsdk/)
- [uv Package Manager](https://github.com/astral-sh/uv)
- [Microsoft: Maximum Path Length Limitation](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)
- [Python: Windows Long Path Support](https://docs.python.org/3/using/windows.html#removing-the-max-path-limitation)
- [PEP 632: Build System Independence](https://peps.python.org/pep-0632/)

---

**Thank you for your research assistance!** 🙏
