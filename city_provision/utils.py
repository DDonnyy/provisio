import numpy as np
import shapely
import geopandas as gpd


def provision_matrix_transform(
    destination_matrix, services, buildings, distance_matrix
):
    def subfunc(loc):
        try:
            return [
                {
                    "building_id": int(k),
                    "demand": int(v),
                    "service_id": int(loc.name),
                }
                for k, v in loc.to_dict().items()
            ]
        except:
            return np.NaN

    def subfunc_geom(loc):
        return shapely.geometry.LineString(
            (
                buildings["geometry"][loc["building_id"]],
                services["geometry"][loc["service_id"]],
            )
        )

    buildings.geometry = buildings.centroid
    services.geometry = services.centroid
    flat_matrix = destination_matrix.transpose().apply(
        lambda x: subfunc(x[x > 0]), result_type="reduce"
    )

    distribution_links = gpd.GeoDataFrame(
        data=[item for sublist in list(flat_matrix) for item in sublist]
    )

    distribution_links["distance"] = distribution_links.apply(
        lambda x: distance_matrix.loc[x["service_id"]][x["building_id"]],
        axis=1,
        result_type="reduce",
    )

    sel = distribution_links["building_id"].isin(
        buildings.index.values
    ) & distribution_links["service_id"].isin(services.index.values)
    sel = distribution_links.loc[sel[sel].index.values]
    distribution_links = distribution_links.set_geometry(
        sel.apply(lambda x: subfunc_geom(x), axis=1)
    )
    return distribution_links


def additional_options(
    buildings,
    services,
    Matrix,
    destination_matrix,
    normative_distance,
):
    # clear matrix same size as buildings and services if user sent sth new
    cols_to_drop = list(set(set(Matrix.columns.values) - set(buildings.index.values)))
    rows_to_drop = list(set(set(Matrix.index.values) - set(services.index.values)))
    Matrix = Matrix.drop(index=rows_to_drop, columns=cols_to_drop, errors="ignore")
    destination_matrix = destination_matrix.drop(
        index=rows_to_drop, columns=cols_to_drop, errors="ignore"
    )
    # bad performance
    # bad code
    # rewrite to vector operations [for col in ****]
    buildings[f"service_demand_left_value"] = buildings[f"service_demand_value"]
    buildings[f"supplyed_demands_within"] = 0
    buildings[f"supplyed_demands_without"] = 0
    services["capacity_left"] = services["capacity"]
    services["carried_capacity_within"] = 0
    services["carried_capacity_without"] = 0
    for i in range(len(destination_matrix)):
        loc = destination_matrix.iloc[i]
        s = Matrix.loc[loc.name] <= normative_distance
        within = loc[s]
        without = loc[~s]
        within = within[within > 0]
        without = without[without > 0]
        buildings[f"service_demand_left_value"] = buildings[
            f"service_demand_left_value"
        ].sub(within.add(without, fill_value=0), fill_value=0)
        buildings[f"supplyed_demands_within"] = buildings[
            f"supplyed_demands_within"
        ].add(within, fill_value=0)
        buildings[f"supplyed_demands_without"] = buildings[
            f"supplyed_demands_without"
        ].add(without, fill_value=0)
        services.at[loc.name, "capacity_left"] = (
            services.at[loc.name, "capacity_left"]
            - within.add(without, fill_value=0).sum()
        )
        services.at[loc.name, "carried_capacity_within"] = (
            services.at[loc.name, "carried_capacity_within"] + within.sum()
        )
        services.at[loc.name, "carried_capacity_without"] = (
            services.at[loc.name, "carried_capacity_without"] + without.sum()
        )
    buildings[f"provison_value"] = (
        buildings[f"supplyed_demands_within"] / buildings[f"service_demand_value"]
    )
    services["service_load"] = services["capacity"] - services["capacity_left"]
    buildings = buildings[
        [x for x in buildings.columns] + ["building_id"] + ["geometry"]
    ]
