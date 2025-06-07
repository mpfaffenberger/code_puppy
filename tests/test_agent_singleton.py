from code_puppy.agent import session_memory
from code_puppy.session_memory import SessionMemory


def test_session_memory_singleton():
    sm1 = session_memory()
    sm2 = session_memory()
    assert isinstance(sm1, SessionMemory)
    assert sm1 is sm2  # This must always be the same instance!
