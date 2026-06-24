import os
import tempfile
from code_puppy.undo_manager import UndoManager

def test_undo_manager():
    manager = UndoManager()
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"hello world")
        filepath = f.name
    
    manager.record_change(filepath, "replace_in_file")
    
    with open(filepath, "w") as f:
        f.write("new world")
        
    res = manager.undo_last()
    assert "Undid" in res
    
    with open(filepath, "r") as f:
        assert f.read() == "hello world"
        
    os.remove(filepath)
