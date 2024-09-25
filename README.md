# Outdated. 
## It will no longer be supported. The latest version of the method has been migrated to [ObjectNat](https://github.com/DDonnyy/objectnat) .

## Provisio 

Small utility library containing city provision metric used in other projects


## Base usage example
Use [dongraphio](https://github.com/DDonnyy/dongraphio) to get city's Intermodal Graph and adjacency matrix between two geodataframes

```pip install provisio```

```python
import pandas as pd
import geopandas as gpd
from provisio import *
buildings: gpd.GeoDataFrame = gpd.read_file("test_data/buildings.geojson").rename(
        columns={"your_demand_value_column": "demand"}
    )
services: gpd.GeoDataFrame = gpd.read_file("services.geojson")

matrix = pd.read_csv("test_data/matrix.csv")

prvs_buildings, prvs_services, prvs_links = get_service_provision(
    services=services, demanded_buildings=buildings, adjacency_matrix=matrix, threshold=10
)
prvs_buildings.to_file("result_buildings.geojson")
prvs_services.to_file("result_services.geojson")
prvs_links.to_file("result_links.geojson")

```

