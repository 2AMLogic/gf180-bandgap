#!/usr/bin/env python3
"""Shared klayout ``Builder`` boilerplate for ``layout/*/generate.py`` scripts.

Every ``layout/*/generate.py`` script that draws GDS directly with
``klayout.db`` (``layout/bandgap_top/generate.py``,
``layout/drc/fixtures/m2m3_stack_probe/generate.py``, ...) used to define its
own ``class Builder`` with an identical ``__init__``/``box()`` core: create a
``kdb.Layout``, set ``dbu``, create the top cell, register each layer from a
``LAYER_NAMES`` dict, and expose a ``box()`` primitive that inserts a
``kdb.Box`` on a registered layer. That 14-line core was duplicated
byte-for-byte across both call sites (gf180-bandgap#167) -- this module gives
it one implementation, the same shape ``layout/common/report_id.py`` already
established for the ``layout/{drc,lvs,netlist}`` run-script boilerplate
(gf180-bandgap#138).

``LAYER_NAMES`` itself stays per-file (each caller's set of layers differs --
``bandgap_top``'s covers 23 layers including labels, ``m2m3_stack_probe``'s
covers 10 for its Metal2/Metal3 routing-stack probe): this module takes it as
a constructor argument rather than owning a canonical copy.

Usage from a ``generate.py`` entry point::

    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(
        0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common")
    )

    from klayout_builder import BuilderBase

    TOP_CELL = "my_top"
    LAYER_NAMES = {...}

    class Builder(BuilderBase):
        def __init__(self) -> None:
            super().__init__(TOP_CELL, LAYER_NAMES)

        # ... file-specific drawing methods, on top of the inherited box() ...
"""

from __future__ import annotations

import klayout.db as kdb


class BuilderBase:
    """``kdb.Layout``/cell/layer setup + the ``box()`` drawing primitive.

    ``top_cell`` and ``layer_names`` are supplied by the caller -- this base
    class has no opinion on either; it only owns the mechanism that turns a
    ``layer_names`` dict into registered ``klayout.db`` layers and a
    ``self._layers`` lookup ``box()`` uses.
    """

    def __init__(self, top_cell: str, layer_names: dict[tuple[int, int], str]) -> None:
        self.layout = kdb.Layout()
        self.layout.dbu = 0.001
        self.cell = self.layout.create_cell(top_cell)
        self._layers: dict[tuple[int, int], int] = {}
        for pair, name in layer_names.items():
            index = self.layout.layer(*pair)
            self.layout.set_info(index, kdb.LayerInfo(pair[0], pair[1], name))
            self._layers[pair] = index

    def box(self, layer: tuple[int, int], x0: int, y0: int, x1: int, y1: int) -> None:
        self.cell.shapes(self._layers[layer]).insert(kdb.Box(x0, y0, x1, y1))
