from PIL import Image

from pitxu.lib.objects.animation import Animation
from pitxu.lib.objects.size import Size
from pitxu.lib.utils.animation_cache import compute_composite_fingerprint

POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")

DEFAULT_COMPOSITE_SPEC = {
    "position": "top-right",
    "badge_scale": 0.4,
    "margin": 0.0,
}


def normalize_composite_spec(spec: dict) -> dict:
    """
    The spec of a composite as it is used (and fingerprinted): the given values over the defaults, with the right types.

    Keys: `base` and `badge` (names of animations of `animations.map`, mandatory), `position` (one of POSITIONS),
    `badge_scale` (width of the badge as a fraction of the width of the base) and `margin` (distance from the corner,
    as a fraction of the width of the base).

    Raises ValueError if something is missing or wrong.
    """
    if not isinstance(spec, dict):
        raise ValueError("a composite must be a dictionary with `base` and `badge`")

    merged = {**DEFAULT_COMPOSITE_SPEC, **{k: v for k, v in spec.items() if v is not None}}
    for key in ("base", "badge"):
        if not merged.get(key):
            raise ValueError(f"a composite needs `{key}`")

    if merged["position"] not in POSITIONS:
        raise ValueError(f"`position` must be one of {list(POSITIONS)}, not [{merged['position']}]")

    merged["badge_scale"] = float(merged["badge_scale"])
    merged["margin"] = float(merged["margin"])
    if not 0 < merged["badge_scale"] <= 1:
        raise ValueError("`badge_scale` must be greater than 0 and not more than 1")

    return {
        "base": str(merged["base"]),
        "badge": str(merged["badge"]),
        "position": merged["position"],
        "badge_scale": merged["badge_scale"],
        "margin": merged["margin"],
    }


class CompositeAnimation(Animation):
    """
    An animation made of two others: a main one (the base) and a smaller one (the badge) in one of its corners.
    For example a smile with a moving ear in the top right corner, to tell that Pitxu is listening.

    It is generated frame by frame from the two GIF files and then it is exactly like any other Animation: the frames
    are resized to the sizes in use and stored in the same disk cache, keyed by the contents of both files, the spec and
    the cache versions, so it is only generated again when something changes.

    The base sets the frame count and the original size. The badge is stretched in time to play exactly once per loop
    of the base, so the loop is seamless whatever the length of each one.
    """

    def __init__(self, name: str, base_file: str, badge_file: str, spec: dict,
                 list_of_sizes_to_cache: list[Size] = None, cache_root: str = None):
        self.base_file = base_file
        self.badge_file = badge_file
        self.spec = normalize_composite_spec(spec)
        super().__init__(name, base_file, list_of_sizes_to_cache=list_of_sizes_to_cache, cache_root=cache_root)

    def _fingerprint(self) -> str:
        return compute_composite_fingerprint([self.base_file, self.badge_file], self.spec)

    def _decode_frames(self) -> list[Image.Image]:
        base_frames = self._decode_gif_file(self.base_file)
        badge_frames = self._decode_gif_file(self.badge_file)
        if not base_frames or not badge_frames:
            raise ValueError(f"No frames found to build the composite animation '{self.name}'")

        base_width, base_height = base_frames[0].size
        badge_width = max(1, round(base_width * self.spec["badge_scale"]))
        badge_height = max(1, round(badge_width * badge_frames[0].size[1] / badge_frames[0].size[0]))
        badge_size = Size(badge_width, badge_height)

        margin = round(base_width * self.spec["margin"])
        x = base_width - badge_width - margin if self.spec["position"].endswith("right") else margin
        y = margin if self.spec["position"].startswith("top") else base_height - badge_height - margin
        # Never outside of the base, whatever the margin
        x = min(max(x, 0), max(base_width - badge_width, 0))
        y = min(max(y, 0), max(base_height - badge_height, 0))

        # The badge frames are resized once, with the same method as every other frame.
        resized_badge_frames = [self._resize_frame_to_desired_size(frame, badge_size) for frame in badge_frames]

        merged_frames = []
        for index, base_frame in enumerate(base_frames):
            badge_index = index * len(resized_badge_frames) // len(base_frames)
            merged = base_frame.convert(self.OUTPUT_COLOR_MODE).copy()
            merged.alpha_composite(resized_badge_frames[badge_index], dest=(x, y))
            merged_frames.append(merged)
        return merged_frames
