# Legacy

Code that is not part of the main pipeline anymore, but that is not removed yet.

| Package | State |
|---|---|
| `canvas` | Canvas V1. Only used by `eink` and `lcd`. Goes away when both are off it. |
| `lcd` | **Active**: ST7789 HAT for the PTT client mode. Waiting for its migration to `canvas_v2`. |
| `eink` | Not used. |
| `matrix_led` | Not used. Has its own macros, it does not use `canvas`. |

Nothing in the main pipeline (`main.py`, `reactions`, `canvas_v2`, `dsi_lcd`) should import from here,
except `Interaction`, which still loads these displays by config.
