import rasterio
import numpy as np

# قراءة الـ DEM
with rasterio.open("data/processed/dem_20m_crop.tif") as src:
    elev = src.read(1)
    # تحويل للمتر × 10 وتخزينه كـ Int16
    elev_dm = np.round(elev * 10).astype(np.int16)
    elev_dm.tofile("web/data/elev_dm_i16.bin")
    print("Saved web/data/elev_dm_i16.bin (Int16)")