from pywinauto import Application

app = Application(backend="uia").connect(title_re=".*Calculator.*")
window = app.top_window()

print("=" * 80)
print("CALCULATOR CONTROL IDENTIFIERS:")
print("=" * 80)

window.print_control_identifiers()
