"""Render animation frames at the display's physical resolution."""
from functools import lru_cache

import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf

@lru_cache(maxsize=32)
def _smooth_frame(path, max_width, max_height):
    source = GdkPixbuf.Pixbuf.new_from_file(path)
    width, height = source.get_width(), source.get_height()
    scale = min(max_width / width, max_height / height)
    target_width = max(1, round(width * scale))
    target_height = max(1, round(height * scale))
    if target_width == width and target_height == height:
        return source
    return source.scale_simple(target_width, target_height, GdkPixbuf.InterpType.HYPER)

def set_animation_frame(picture, path):
    factor = max(1, picture.get_scale_factor())
    width = max(1, picture.get_width() or 300) * factor
    height = max(1, picture.get_height() or 275) * factor
    frame = _smooth_frame(str(path), width, height)
    picture.set_paintable(Gdk.Texture.new_for_pixbuf(frame))
