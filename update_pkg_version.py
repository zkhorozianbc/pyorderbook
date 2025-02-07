import re
from pathlib import Path

import toml


def increment_version(version_str: str) -> str:
    major, minor, patch = map(int, version_str[1:].split("."))
    patch += 1
    if patch > 9:
        patch = 0
        minor += 1
    if minor > 9:
        minor = 0
        major += 1
    return f"v{major}.{minor}.{patch}"


def update_versions() -> str:
    repo_root = Path(__file__).parent
    pyproject_path = repo_root / "pyproject.toml"
    init_path = repo_root / "orderbook" / "__init__.py"

    pyproject = toml.load(pyproject_path)
    current_version = pyproject["project"]["version"]
    new_version = increment_version(current_version)

    pyproject["project"]["version"] = new_version
    with open(pyproject_path, "w") as f:
        toml.dump(pyproject, f)

    init_content = init_path.read_text()
    new_init_content = re.sub(
        r'(__version__\s*=\s*["\'].+?["\'])', f'__version__ = "{new_version}"', init_content
    )
    init_path.write_text(new_init_content)

    return new_version


if __name__ == "__main__":
    new_version = update_versions()
    print(f"Updated version to {new_version}")
