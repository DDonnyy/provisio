"""Demands calculation logic is defined here."""

import pandas as pd


def demands_from_buildings_by_normative(buildings_with_people: pd.DataFrame, normative: float) -> pd.DataFrame:
    """Calculate demands from buildings and save them as `demand` column of new returned DataFrame.

    :param pd.DataFrame: buildings_with_people: buildings with "population" column.

    :param float: normative: normative value representing number of people on 1000 of population which are in
    need of some service.
    """
    demanded = buildings_with_people.copy()
    demanded["demand"] = demanded["population"] * normative
    return demanded


# где-то здесь уже должны быть введены идентификаторы зданий и сервисов, чтобы было проще работать с матрицей
def services_loads_from_demands_and_matrix(
    demanded_buildings: pd.DataFrame,
    services: pd.DataFrame,
    matrix: ...,
) -> pd.DataFrame:
    """Calculate load from buildings with demands on the given services using the distances matrix between them."""
    return ...
