from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("orderbook")
except PackageNotFoundError:
    __version__ = "unknown"