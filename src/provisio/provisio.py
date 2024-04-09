from typing import Tuple

import geopandas as gpd
import pandas as pd

from .provision_logic import CityProvision


def demands_from_buildings_by_normative(buildings_with_people: gpd.GeoDataFrame, normative: float) -> gpd.GeoDataFrame:
    """Calculate demands from buildings based on the given normative value.

    Args:
    buildings_with_people (gpd.GeoDataFrame): buildings with "population" column.
    normative (float): normative value representing the number of people per 1000 population in need of some service.

    Returns:
    gpd.GeoDataFrame: A new GeoDataFrame with the calculated demands saved as the "demand" column.
    """
    demanded = buildings_with_people.copy()
    demanded["demand"] = demanded["population"] * normative
    return demanded


def get_service_provision(
    demanded_buildings: gpd.GeoDataFrame,
    adjacency_matrix: pd.DataFrame,
    services: gpd.GeoDataFrame,
    threshold: int,
    calculation_type: str = "gravity",
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Calculate load from buildings with demands on the given services using the distances matrix between them.

    Args:
        services (gpd.GeoDataFrame): GeoDataFrame of services
        adjacency_matrix (pd.DataFrame): DataFrame representing the adjacency matrix
        demanded_buildings (gpd.GeoDataFrame): GeoDataFrame of demanded buildings
        threshold (int): Threshold value
        calculation_type (str): Calculation type for provision, might be "gravity" or "linear"
    Returns:
        Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]: Tuple of GeoDataFrames representing provision
        buildings, provision services, and provision links
    """
    provision_buildings, provision_services, provision_links = CityProvision(
        services=services,
        demanded_buildings=demanded_buildings,
        adjacency_matrix=adjacency_matrix,
        threshold=threshold,
        calculation_type=calculation_type,
    ).get_provisions()
    return provision_buildings, provision_services, provision_links
