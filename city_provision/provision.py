from typing import Optional

import geopandas as gpd
import networkit as nk
import numpy as np
import pandas as pd
import pulp
from networkx import MultiDiGraph

from city_provision.utils import (
    convert_nx2nk,
    get_nx2nk_idmap,
    get_subgraph,
    load_graph_geometry,
    _additional_options,
)


class CityProvision:
    def __init__(
        self,
        city_crs: int,
        service_type: str,
        services: gpd.GeoDataFrame,
        demanded_buildings: gpd.GeoDataFrame,
        normative_time: int,
        valuation_type: str,
        intermodal_nx_graph: MultiDiGraph,
        user_selection_zone: Optional[dict] = None,
        return_jsons: bool = True,
        calculation_type: str = "gravity",
    ):
        self.city_crs = city_crs
        self.service_type = service_type
        self.valuation_type = valuation_type
        self.service_type_normative = normative_time
        self.return_jsons = return_jsons
        self.nx_graph = intermodal_nx_graph
        self.calculation_type = calculation_type

        mobility_sub_graph = get_subgraph(
            self.nx_graph, "type", ["subway", "bus", "tram", "trolleybus", "walk"]
        )

        self.graph_nk_time = convert_nx2nk(
            mobility_sub_graph,
            idmap=get_nx2nk_idmap(mobility_sub_graph),
            weight="time_min",
        )
        self.MobilitySubGraph = load_graph_geometry(mobility_sub_graph)

        self.buildings = demanded_buildings.copy(deep=True).dropna(
            subset="functional_object_id"
        )
        self.buildings.index = self.buildings["functional_object_id"].values.astype(int)
        self.services = services.copy(deep=True)
        self.services.index = self.services["id"].values.astype(int)

        self.user_provisions = {}
        self.errors = []

        self.buildings[
            f"{service_type}_service_demand_left_value_{self.valuation_type}"
        ] = self.buildings[f"{service_type}_service_demand_value_{self.valuation_type}"]
        self.buildings = self.buildings.dropna(
            subset=f"{service_type}_service_demand_value_{self.valuation_type}"
        )
        self.services["capacity_left"] = self.services["capacity"]
        if user_selection_zone:
            self.user_selection_zone = user_selection_zone
        else:
            self.user_selection_zone = None

    def get_provisions(self):
        self._calculate_provisions(
            self.Provisions[self.service_type],
            self.service_type,
            calculation_type=self.calculation_type,
        )
        (
            self.Provisions["buildings"],
            self.Provisions["services"],
        ) = _additional_options(
            self.Provisions["buildings"].copy(),
            self.Provisions["services"].copy(),
            self.Provisions["distance_matrix"].copy(),
            self.Provisions["destination_matrix"].copy(),
            self.Provisions["normative_distance"],
            self.service_type,
            self.user_selection_zone,
            self.valuation_type,
        )
        cols_to_drop = [
            x
            for x in self.buildings.columns
            for service_type in self.service_types
            if service_type in x
        ]
        self.buildings = self.buildings.drop(columns=cols_to_drop)
        for service_type in self.service_types:
            self.buildings = self.buildings.merge(
                self.Provisions[service_type]["buildings"],
                left_on="functional_object_id",
                right_on="functional_object_id",
            )
        to_rename_x = [x for x in self.buildings.columns if "_x" in x]
        to_rename_y = [x for x in self.buildings.columns if "_y" in x]
        self.buildings = self.buildings.rename(
            columns=dict(zip(to_rename_x, [x.split("_x")[0] for x in to_rename_x]))
        )
        self.buildings = self.buildings.rename(
            columns=dict(zip(to_rename_y, [y.split("_y")[0] for y in to_rename_y]))
        )
        self.buildings = self.buildings.loc[
            :, ~self.buildings.columns.duplicated()
        ].copy()
        self.buildings.index = self.buildings["functional_object_id"].values.astype(int)
        self.services = pd.concat(
            [
                self.Provisions[service_type]["services"]
                for service_type in self.service_types
            ]
        )
        self.buildings, self.services = self._is_shown(
            self.buildings, self.services, self.Provisions
        )
        self.buildings = self.buildings.fillna(0)
        self.services = self.services.fillna(0)

        if self.return_jsons:
            return {
                "houses": self.buildings,
                "services": self.services,
                "provisions": {
                    service_type: self._provision_matrix_transform(
                        self.Provisions[service_type]["destination_matrix"],
                        self.services[self.services["is_shown"] == True],
                        self.buildings[self.buildings["is_shown"] == True],
                    )
                    for service_type in self.service_types
                },
            }
        else:
            return self

    def _calculate_provisions(self, calculation_type):
        df = pd.DataFrame.from_dict(
            dict(self.nx_graph.nodes(data=True)), orient="index"
        )
        self.graph_gdf = gpd.GeoDataFrame(
            df, geometry=df["geometry"], crs=self.city_crs
        )
        from_houses = self.graph_gdf["geometry"].sindex.nearest(
            self.buildings["geometry"], return_distance=True, return_all=False
        )
        to_services = self.graph_gdf["geometry"].sindex.nearest(
            self.services["geometry"], return_distance=True, return_all=False
        )
        self.distance_matrix = pd.DataFrame(
            0, index=to_services[0][1], columns=from_houses[0][1]
        )

        splited_matrix = np.array_split(
            self.distance_matrix.copy(deep=True),
            int(len(self.distance_matrix) / 1000) + 1,
        )

        for i in range(len(splited_matrix)):
            r = nk.distance.SPSP(
                G=self.graph_nk_time, sources=splited_matrix[i].index.values
            ).run()
            splited_matrix[i] = splited_matrix[i].apply(
                lambda x: self._get_nk_distances(r, x), axis=1
            )
            del r
        self.distance_matrix = pd.concat(splited_matrix)
        del splited_matrix

        self.distance_matrix.index = Provisions["services"].index
        self.distance_matrix.columns = Provisions["buildings"].index
        Provisions["destination_matrix"] = pd.DataFrame(
            0,
            index=Provisions["distance_matrix"].index,
            columns=Provisions["distance_matrix"].columns,
        )
        print(
            Provisions["buildings"][
                f"{service_type}_service_demand_left_value_{self.valuation_type}"
            ].sum(),
            Provisions["services"]["capacity_left"].sum(),
            Provisions["normative_distance"],
        )

        if calculation_type == "gravity":
            Provisions["destination_matrix"] = self._provision_loop_gravity(
                Provisions["buildings"].copy(),
                Provisions["services"].copy(),
                Provisions["distance_matrix"].copy() + 1,
                Provisions["normative_distance"],
                Provisions["destination_matrix"].copy(),
                service_type,
            )

        elif calculation_type == "linear":
            Provisions["destination_matrix"] = self._provision_loop_linear(
                Provisions["buildings"].copy(),
                Provisions["services"].copy(),
                Provisions["distance_matrix"].copy(),
                Provisions["normative_distance"],
                Provisions["destination_matrix"].copy(),
                service_type,
            )
        return

    def _provision_loop_gravity(
        self,
        houses_table,
        services_table,
        distance_matrix,
        selection_range,
        destination_matrix,
        service_type,
        temp_destination_matrix=None,
    ):
        def _calculate_flows_y(loc):
            c = services_table.loc[loc.name]["capacity_left"]
            d = houses_table.loc[loc.index][
                f"{service_type}_service_demand_left_value_{self.valuation_type}"
            ]
            p = d / loc
            p = p / p.sum()
            if p.sum() == 0:
                return loc
            else:
                rng = np.random.default_rng(seed=0)
                r = pd.Series(0, p.index)
                choice = np.unique(
                    rng.choice(p.index, int(c), p=p.values), return_counts=True
                )
                choice = r.add(pd.Series(choice[1], choice[0]), fill_value=0)
                return choice

        def _balance_flows_to_demands(loc):
            d = houses_table.loc[loc.name][
                f"{service_type}_service_demand_left_value_{self.valuation_type}"
            ]
            loc = loc[loc > 0]
            if loc.sum() > 0:
                p = loc / loc.sum()
                rng = np.random.default_rng(seed=0)
                r = pd.Series(0, p.index)
                choice = np.unique(
                    rng.choice(p.index, int(d), p=p.values), return_counts=True
                )
                choice = r.add(pd.Series(choice[1], choice[0]), fill_value=0)
                choice = pd.Series(
                    data=np.minimum(
                        loc.sort_index().values, choice.sort_index().values
                    ),
                    index=loc.sort_index().index,
                )
                return choice
            else:
                return loc

        temp_destination_matrix = distance_matrix.apply(
            lambda x: _calculate_flows_y(x[x <= selection_range]), axis=1
        )
        temp_destination_matrix = temp_destination_matrix.fillna(0)
        temp_destination_matrix = temp_destination_matrix.apply(
            lambda x: _balance_flows_to_demands(x)
        )
        temp_destination_matrix = temp_destination_matrix.fillna(0)
        destination_matrix = destination_matrix.add(
            temp_destination_matrix, fill_value=0
        )
        axis_1 = destination_matrix.sum(axis=1)
        axis_0 = destination_matrix.sum(axis=0)
        services_table["capacity_left"] = services_table["capacity"].subtract(
            axis_1, fill_value=0
        )
        houses_table[
            f"{service_type}_service_demand_left_value_{self.valuation_type}"
        ] = houses_table[
            f"{service_type}_service_demand_value_{self.valuation_type}"
        ].subtract(
            axis_0, fill_value=0
        )

        distance_matrix = distance_matrix.drop(
            index=services_table[services_table["capacity_left"] == 0].index.values,
            columns=houses_table[
                houses_table[
                    f"{service_type}_service_demand_left_value_{self.valuation_type}"
                ]
                == 0
            ].index.values,
            errors="ignore",
        )
        selection_range += selection_range
        if len(distance_matrix.columns) > 0 and len(distance_matrix.index) > 0:

            return self._provision_loop_gravity(
                houses_table,
                services_table,
                distance_matrix,
                selection_range,
                destination_matrix,
                service_type,
                temp_destination_matrix,
            )
        else:
            print(
                houses_table[
                    f"{service_type}_service_demand_left_value_{self.valuation_type}"
                ].sum(),
                services_table["capacity_left"].sum(),
                selection_range,
            )
            return destination_matrix

    def _provision_loop_linear(
        self,
        houses_table,
        services_table,
        distance_matrix,
        selection_range,
        destination_matrix,
        service_type,
    ):

        select = distance_matrix[distance_matrix.iloc[:] <= selection_range]
        select = select.apply(lambda x: 1 / (x + 1), axis=1)

        select = select.loc[:, ~select.columns.duplicated()].copy(deep=True)
        select = select.loc[~select.index.duplicated(), :].copy(deep=True)

        variables = select.apply(lambda x: self._declare_varables(x), axis=1)

        prob = pulp.LpProblem("problem", pulp.LpMaximize)
        for col in variables.columns:
            t = variables[col].dropna().values
            if len(t) > 0:
                prob += (
                    pulp.lpSum(t)
                    <= houses_table[
                        f"{service_type}_service_demand_left_value_{self.valuation_type}"
                    ][col],
                    f"sum_of_capacities_{col}",
                )
            else:
                pass

        for index in variables.index:
            t = variables.loc[index].dropna().values
            if len(t) > 0:
                prob += (
                    pulp.lpSum(t) <= services_table["capacity_left"][index],
                    f"sum_of_demands_{index}",
                )
            else:
                pass
        costs = []
        for index in variables.index:
            t = variables.loc[index].dropna()
            t = t * select.loc[index].dropna()
            costs.extend(t)
        prob += (pulp.lpSum(costs), "Sum_of_Transporting_Costs")
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        to_df = {}
        for var in prob.variables():
            t = var.name.split("_")
            try:
                to_df[int(t[1])].update({int(t[2]): var.value()})
            except ValueError:
                print(t)
                pass
            except:
                to_df[int(t[1])] = {int(t[2]): var.value()}

        result = pd.DataFrame(to_df).transpose()
        result = result.join(
            pd.DataFrame(
                0,
                columns=list(
                    set(set(destination_matrix.columns) - set(result.columns))
                ),
                index=destination_matrix.index,
            ),
            how="outer",
        )
        result = result.fillna(0)
        destination_matrix = destination_matrix + result
        axis_1 = destination_matrix.sum(axis=1)
        axis_0 = destination_matrix.sum(axis=0)
        services_table["capacity_left"] = services_table["capacity"].subtract(
            axis_1, fill_value=0
        )
        houses_table[
            f"{service_type}_service_demand_left_value_{self.valuation_type}"
        ] = houses_table[
            f"{service_type}_service_demand_value_{self.valuation_type}"
        ].subtract(
            axis_0, fill_value=0
        )

        distance_matrix = distance_matrix.drop(
            index=services_table[services_table["capacity_left"] == 0].index.values,
            columns=houses_table[
                houses_table[
                    f"{service_type}_service_demand_left_value_{self.valuation_type}"
                ]
                == 0
            ].index.values,
            errors="ignore",
        )

        selection_range += selection_range
        if len(distance_matrix.columns) > 0 and len(distance_matrix.index) > 0:
            return self._provision_loop_linear(
                houses_table,
                services_table,
                distance_matrix,
                selection_range,
                destination_matrix,
                service_type,
            )
        else:
            print(
                houses_table[
                    f"{service_type}_service_demand_left_value_{self.valuation_type}"
                ].sum(),
                services_table["capacity_left"].sum(),
                selection_range,
            )
            return destination_matrix
