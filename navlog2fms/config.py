import json
import os

_CONFIG_PATH = os.path.expanduser("~/.navlog2fms")


def load() -> dict:
    if not os.path.isfile(_CONFIG_PATH):
        return {}
    with open(_CONFIG_PATH) as f:
        return json.load(f)


def save(data: dict) -> None:
    existing = load()
    existing.update(data)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(existing, f, indent=2)


def get_xplane_path() -> str | None:
    return load().get("xplane_path")


def set_xplane_path(path: str) -> None:
    save({"xplane_path": path})
    print(f"Saved X-Plane path: {path}")
