import networkx as nx
from city_graphs import graphs
from city_provision.provision import CityProvision
import geopandas as gpd


def main():
    # city_osm_id = 421007
    # city_crs = 32636
    # """
    # If you need to upload public transportation data from a file, please fill in the dictionary below.
    # Leave 'None' in case of no file or provide the file name with the .geojson format.
    # For example:
    # "bus": {"stops": "bus_stop_Tara.geojson", "routes": "Tara_routes.geojson"}
    # OR
    # "bus": {"stops": None, "routes": None}"
    # """
    # gdf_files = {
    #     "subway": {"stops": None, "routes": None},
    #     "tram": {"stops": None, "routes": None},
    #     "trolleybus": {"stops": None, "routes": None},
    #     "bus": {"stops": None, "routes": None},
    # }
    #
    # G_graph: nx.MultiDiGraph = graphs.get_intermodal_graph(city_osm_id, city_crs, gdf_files)
    # nx.write_graphml(G_graph, f"{city_osm_id}.graphml")
    gdf_demanded_buildings = gpd.read_file("buildings.geojson")
    gdf_services = gpd.read_file("tara_kinder.geojson")
    graph: nx.MultiDiGraph = nx.read_graphml("Тара.graphml")
    gpd.GeoDataFrame(
        CityProvision(
            city_crs=32636,
            service_type="kindergartens",
            services=gdf_services,
            demanded_buildings=gdf_demanded_buildings,
            valuation_type="model",
            intermodal_nx_graph=graph,
            normative_radius=300,
        ).get_provisions()["provision"]
    ).to_file("result.geojson")


if __name__ == "__main__":
    main()
