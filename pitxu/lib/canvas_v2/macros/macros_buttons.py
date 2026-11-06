from PIL import ImageDraw

from pyxavi import Config, Dictionary, dd
from pitxu.lib.objects import Point

from pitxu.lib.canvas_v2.macros.macros_base import MacrosBase

class MacrosButtons(MacrosBase):
    """
    Drawings that take place in the status area, which is the "bottom-center" area of the layout.
    """

    def __init__(self, config: Config, params: Dictionary):
        super(MacrosButtons, self).__init__(config, params)

        self._xlog.debug("Initialized MacrosButtons.")
    
    