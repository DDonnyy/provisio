import geopandas as gpd
import pandas as pd

from .provision_logic import CityProvision


def demands_from_buildings_by_normative(buildings_with_people: gpd.GeoDataFrame, normative: float) -> gpd.GeoDataFrame:
    """Calculate demands from buildings and save them as `demand` column of new returned DataFrame.
    :param pd.DataFrame: buildings_with_people: buildings with "population" column.
    :param float: normative: normative value representing number of people on 1000 of population which are in
    need of some service.
    """
    demanded = buildings_with_people.copy()
    demanded["demand"] = demanded["population"] * normative
    return demanded


def get_service_provision(
    services: gpd.GeoDataFrame, adjacency_matrix: pd.DataFrame, demanded_buildings: gpd.GeoDataFrame, threshold: int
) -> (gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame):
    """Calculate load from buildings with demands on the given services using the distances matrix between them."""
    provision_buildings, provision_services, provision_links = CityProvision(
        services=services, demanded_buildings=demanded_buildings, adjacency_matrix=adjacency_matrix, threshold=threshold
    ).get_provisions()
    return provision_buildings, provision_services, provision_links
