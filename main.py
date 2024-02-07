import networkx as nx
from city_graphs import graphs


def main():
    city_osm_id = 3955288
    city_crs = 32639
    """
    If you need to upload public transportation data from a file, please fill in the dictionary below.
    Leave 'None' in case of no file or provide the file name with the .geojson format.
    For example:
    "bus": {"stops": "bus_stop_Tara.geojson", "routes": "Tara_routes.geojson"}
    OR
    "bus": {"stops": None, "routes": None}"
    """
    gdf_files = {
        "subway": {"stops": None, "routes": None},
        "tram": {"stops": None, "routes": None},
        "trolleybus": {"stops": None, "routes": None},
        "bus": {"stops": None, "routes": None},
    }

    G_graph: nx.MultiDiGraph = graphs.get_intermodal_graph(city_osm_id, city_crs, gdf_files)
    nx.write_graphml(G_graph, f"{city_osm_id}.graphml")



if __name__ == "__main__":
    main()

