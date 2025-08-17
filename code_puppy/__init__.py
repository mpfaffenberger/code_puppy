try:
    import importlib.metadata

    __version__ = importlib.metadata.version("code-puppy")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.1"
