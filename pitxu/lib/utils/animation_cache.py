import hashlib
import json
import os

# Bump it when the way the cached frames are generated changes (conversion, resize algorithm, format...),
#   so every previously cached animation is considered stale and gets regenerated.
ANIMATION_CACHE_VERSION = 2  # 2: frames decoded with the right transparency (RGB_ALWAYS) and resized with premultiplied alpha

DEFAULT_STORAGE_PATH = "storage/"
DEFAULT_ANIMATION_CACHE_FOLDER = "animations/"


def compute_fingerprint(file_path: str) -> str:
    """
    Short hash of the animation file contents and the cache version.
    Based on the contents, not on the modification time, so it survives a git checkout or a copy to another device.
    """
    sha1 = hashlib.sha1()
    sha1.update(f"v{ANIMATION_CACHE_VERSION}".encode())
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha1.update(chunk)
    return sha1.hexdigest()[:12]


# Bump it when the way a composite animation is put together changes (position, scale, timing...)
COMPOSITE_GENERATION_VERSION = 1


def compute_composite_fingerprint(file_paths: list[str], spec: dict) -> str:
    """
    Short hash of the contents of all the GIF files a composite animation is made of, the way they are merged
    (the spec) and the cache versions. Changing any of them regenerates the composite.
    """
    sha1 = hashlib.sha1()
    sha1.update(f"v{ANIMATION_CACHE_VERSION}c{COMPOSITE_GENERATION_VERSION}".encode())
    sha1.update(json.dumps(spec, sort_keys=True).encode())
    for file_path in file_paths:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha1.update(chunk)
    return sha1.hexdigest()[:12]


def build_cache_dir_name(animation_name: str, fingerprint: str) -> str:
    return f"{animation_name}-{fingerprint}"


def get_cache_root(config) -> str | None:
    """
    Where the prepared animation frames are stored. None if the cache is disabled by configuration.
    """
    if not config.get("animations.cache.enabled", True):
        return None
    path = config.get("animations.cache.path", None)
    if path is None:
        path = os.path.join(config.get("storage.path", DEFAULT_STORAGE_PATH), DEFAULT_ANIMATION_CACHE_FOLDER)
    return path
