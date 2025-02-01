from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

try:
    __version__ = version("orderbook")
except PackageNotFoundError:
    __version__ = "unknown"
