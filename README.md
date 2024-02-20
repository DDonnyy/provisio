

# Provisio

Small utility library containing city provision metric used in other projects


## Base usage example
Use [dongraphio](https://github.com/DDonnyy/dongraphio) to get city's IntermodalGraph and adjacency matrix between two geodataframes

### SOON IN PYPI
```pip install provisio```

```python
import pandas as pd
import geopandas as gpd
import networkx as nx
from provisio import *

builds = gpd.read_file("test_data/buildings.geojson")
services = gpd.read_file("test_data/services.geojson")
matrix = pd.read_csv("test_data/matrix.csv")

demanded_building = demands_from_buildings_by_normative(builds,0.1)

prvs_buildings, prvs_services, prvs_links = get_service_provision(
        services=services, demanded_buildings=demanded_buildings, adjacency_matrix=matrix, threshold=10
    ).get_provisions()

```

