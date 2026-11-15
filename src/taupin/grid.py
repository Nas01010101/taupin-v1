"""The field grid every baked layer shares: a north-up UTM 18N square of 2 m cells.

The extent is a 600 m square over the mapped meadows of the Secteur des Champs and the Chalet
d'accueil des Champs (OpenStreetMap landuse=meadow ways 477189276 to 477189278).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Grid:
    x0: float          # west edge, metres (UTM)
    y_top: float       # north edge, metres (UTM)
    res: float         # cell side, metres
    size: int          # cells per side
    crs: str = "EPSG:32618"

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        side = self.res * self.size
        return (self.x0, self.y_top - side, self.x0 + side, self.y_top)

    def transform(self):
        from rasterio.transform import from_origin
        return from_origin(self.x0, self.y_top, self.res, self.res)

    def center(self, row: float, col: float) -> tuple[float, float]:
        """UTM coordinates of the centre of cell (row, col)."""
        return (self.x0 + (col + 0.5) * self.res, self.y_top - (row + 0.5) * self.res)

    def coarse(self, res: float) -> "Grid":
        """Same extent at a coarser cell size (for 10-30 m satellite reads)."""
        n = round(self.size * self.res / res)
        return Grid(self.x0, self.y_top, self.res * self.size / n, n, self.crs)


# The first bake sat 90 m east and 480 m north of this, on woods and a housing street; lidar
# showed 1.1 ha of open ground there. Shifts are multiples of 30 m, the HLS pixel.
PARCEL = Grid(x0=596172.8437110512, y_top=5039681.716137531, res=2.0, size=300)
