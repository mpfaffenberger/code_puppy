import os
from rich.console import Console

NO_COLOR = bool(int(os.environ.get('CODE_PUPPY_NO_COLOR', '0')))
console = Console(no_color=NO_COLOR)
