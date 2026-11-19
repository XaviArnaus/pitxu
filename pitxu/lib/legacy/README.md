# Legacy

Code that is not part of the main pipeline anymore, but that is not removed yet.

> ⚠️ **Deprecated.** These displays are behind the current implementation: they know nothing about the Animations
> area (`XprocessDisplayAnimations`, the `animations_display` setting), for example. Before using any of them,
> they need to be updated according to the current implementation. `lcd` only has empty Animations methods,
> so the actions that reach it don't fail; `matrix_led` and `eink` do not handle them at all (`matrix_led` no longer
> receives the thinking effect).

| Package | State |
|---|---|
| `canvas` | Canvas V1. Only used by `eink` and `lcd`. Goes away when both are off it. |
| `lcd` | **Active**: ST7789 HAT for the PTT client mode. Waiting for its migration to `canvas_v2`. |
| `eink` | Not used. |
| `macros_legacy.py` | Old drawing macros of Canvas V2. Never instantiated. |
| `macros_background_led.py` | The LED-emulation shapes of the background effects (mouth, scanner, countdown bar, init phase, cross), written for the tall top-left area. Replaced by the rectangles in `MacrosBackground`. Never instantiated. |
| `matrix_led` | Not used. Has its own macros, it does not use `canvas`. |

Nothing in the main pipeline (`main.py`, `reactions`, `canvas_v2`, `dsi_lcd`) should import from here,
except `Interaction`, which still loads these displays by config.
