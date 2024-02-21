import geopandas as gpd
import numpy as np
import pandas as pd
import shapely


def provision_matrix_transform(
    destination_matrix: pd.DataFrame,
    services: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    distance_matrix: pd.DataFrame,
):
    def subfunc(loc):
        try:
            return [
                {
                    "building_index": int(k),
                    "demand": int(v),
                    "service_index": int(loc.name),
                }
                for k, v in loc.to_dict().items()
            ]
        except:
            return np.NaN

    def subfunc_geom(loc):
        return shapely.geometry.LineString(
            (
                buildings["geometry"][loc["building_index"]],
                services["geometry"][loc["service_index"]],
            )
        )

    buildings.geometry = buildings.centroid
    services.geometry = services.centroid
    flat_matrix = destination_matrix.transpose().apply(lambda x: subfunc(x[x > 0]), result_type="reduce")

    distribution_links = gpd.GeoDataFrame(data=[item for sublist in list(flat_matrix) for item in sublist])

    distribution_links["distance"] = distribution_links.apply(
        lambda x: distance_matrix.loc[x["service_index"]][x["building_index"]],
        axis=1,
        result_type="reduce",
    )

    sel = distribution_links["building_index"].isin(buildings.index.values) & distribution_links["service_index"].isin(
        services.index.values
    )
    sel = distribution_links.loc[sel[sel].index.values]
    distribution_links = distribution_links.set_geometry(sel.apply(lambda x: subfunc_geom(x), axis=1)).set_crs(
        buildings.crs
    )
    return distribution_links


def additional_options(
    buildings,
    services,
    matrix,
    destination_matrix,
    normative_distance,
):
    # bad performance
    # bad code
    # rewrite to vector operations [for col in ****]
    buildings["supplyed_demands_within"] = 0
    buildings["supplyed_demands_without"] = 0
    services["carried_capacity_within"] = 0
    services["carried_capacity_without"] = 0
    for i in range(len(destination_matrix)):
        loc = destination_matrix.iloc[i]
        s = matrix.loc[loc.name] <= normative_distance
        within = loc[s]
        without = loc[~s]
        within = within[within > 0]
        without = without[without > 0]
        buildings["demand_left"] = buildings["demand_left"].sub(within.add(without, fill_value=0), fill_value=0)
        buildings["supplyed_demands_within"] = buildings["supplyed_demands_within"].add(within, fill_value=0)
        buildings["supplyed_demands_without"] = buildings["supplyed_demands_without"].add(without, fill_value=0)
        services.at[loc.name, "capacity_left"] = (
            services.at[loc.name, "capacity_left"] - within.add(without, fill_value=0).sum()
        )
        services.at[loc.name, "carried_capacity_within"] = (
            services.at[loc.name, "carried_capacity_within"] + within.sum()
        )
        services.at[loc.name, "carried_capacity_without"] = (
            services.at[loc.name, "carried_capacity_without"] + without.sum()
        )
    buildings["provison_value"] = buildings["supplyed_demands_within"] / buildings["demand"]
    services["service_load"] = services["capacity"] - services["capacity_left"]
    buildings = buildings[[x for x in buildings.columns] + ["building_id"] + ["geometry"]]
