import networkx as nx

from city_provision.provision import CityProvision
import geopandas as gpd


def main():

    gpd.GeoDataFrame(
        CityProvision(
            city_crs=32643,
            services=kindersgarten,
            demanded_buildings=gdf_demanded_buildings,
            service_type="kindergartens",
            valuation_type="model",
            intermodal_nx_graph=graph,
            normative_radius=300,
        ).get_provisions()
    ).to_file("result.geojson")


if __name__ == "__main__":
    main()
