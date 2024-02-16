from typing import Optional, Any

from pydantic import BaseModel, field_validator, InstanceOf
import geopandas as gpd
import numpy as np
import pandas as pd
import pulp

from .utils import (
    additional_options,
    provision_matrix_transform,
)


class CityProvision(BaseModel):
    city_crs: int
    services: InstanceOf[gpd.GeoDataFrame]
    demanded_buildings: InstanceOf[gpd.GeoDataFrame]
    adjacency_matrix: []
    threshold: int
    user_selection_zone: Optional[dict] = None  # TODO вынести в метод
    calculation_type: str = "gravity"

    @staticmethod
    @field_validator("demanded_buildings")
    def ensure_buildings(cls, v: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if "building_id" not in v.columns:
            raise KeyError("column 'building_id' not found in provided GeoDataFrame")
        if "service_demand_value" not in v.columns:
            raise KeyError(
                "The column 'service_demand_value' was not found in the provided GeoDataFrame. This attribute "
                "corresponds to the number of demands for the selected service in each building."
            )


        v.index = v
        return v

        self.buildings.index = self.buildings["building_id"].values.astype(int)
        self.services = services.copy(deep=True).to_crs(self.city_crs)
        self.services.index = self.services["service_id"].values.astype(int)

        self.buildings[f"service_demand_left_value"] = self.buildings[f"service_demand_value"]
        self.buildings = self.buildings.dropna(subset=f"service_demand_value")
        self.services["capacity_left"] = self.services["capacity"]
        if user_selection_zone:
            self.user_selection_zone = user_selection_zone
        else:
            self.user_selection_zone = None

    def get_provisions(self):
        self._calculate_provisions()
        additional_options(
            self.buildings,
            self.services,
            self.distance_matrix,
            self.destination_matrix,
            self.normative,
        )

        self.buildings.index = self.buildings["building_id"].values.astype(int)
        self.buildings, self.services = self._is_shown(self.buildings, self.services)
        self.buildings = self.buildings.fillna(0)
        self.services = self.services.fillna(0)

        return {
            "houses": self.buildings,
            "services": self.services,
            "provisions": provision_matrix_transform(
                self.destination_matrix,
                self.services[self.services["is_shown"] == True],
                self.buildings[self.buildings["is_shown"] == True],
                self.distance_matrix,
            ).set_crs(self.city_crs),
        }

    def _calculate_provisions(self):
        self.destination_matrix = pd.DataFrame(
            0,
            index=self.distance_matrix.index,
            columns=self.distance_matrix.columns,
        )

        if self.calculation_type == "gravity":
            self.destination_matrix = self._provision_loop_gravity(self.buildings.copy(), self.services.copy(),
                                                                   self.distance_matrix.copy() + 1, self.normative,
                                                                   self.destination_matrix.copy())

        elif self.calculation_type == "linear":
            self.destination_matrix = self._provision_loop_linear(self.buildings.copy(), self.services.copy(),
                                                                  self.distance_matrix.copy(), self.normative,
                                                                  self.destination_matrix.copy())
        return

    def _provision_loop_gravity(
        self,
        houses_table,
        services_table,
        distance_matrix,
        selection_range,
        destination_matrix,
        temp_destination_matrix=None,
    ):
        def _calculate_flows_y(loc):
            c = services_table.loc[loc.name]["capacity_left"]
            d = houses_table.loc[loc.index][f"service_demand_left_value"]
            p = d / loc
            p = p / p.sum()
            if p.sum() == 0:
                return loc
            else:
                rng = np.random.default_rng(seed=0)
                r = pd.Series(0, p.index)
                choice = np.unique(rng.choice(p.index, int(c), p=p.values), return_counts=True)
                choice = r.add(pd.Series(choice[1], choice[0]), fill_value=0)
                return choice

        def _balance_flows_to_demands(loc):
            d = houses_table.loc[loc.name][f"service_demand_left_value"]
            loc = loc[loc > 0]
            if loc.sum() > 0:
                p = loc / loc.sum()
                rng = np.random.default_rng(seed=0)
                r = pd.Series(0, p.index)
                choice = np.unique(rng.choice(p.index, int(d), p=p.values), return_counts=True)
                choice = r.add(pd.Series(choice[1], choice[0]), fill_value=0)
                choice = pd.Series(
                    data=np.minimum(loc.sort_index().values, choice.sort_index().values),
                    index=loc.sort_index().index,
                )
                return choice
            else:
                return loc

        temp_destination_matrix = distance_matrix.apply(lambda x: _calculate_flows_y(x[x <= selection_range]), axis=1)
        temp_destination_matrix = temp_destination_matrix.fillna(0)
        temp_destination_matrix = temp_destination_matrix.apply(lambda x: _balance_flows_to_demands(x))
        temp_destination_matrix = temp_destination_matrix.fillna(0)
        destination_matrix = destination_matrix.add(temp_destination_matrix, fill_value=0)
        axis_1 = destination_matrix.sum(axis=1)
        axis_0 = destination_matrix.sum(axis=0)
        services_table["capacity_left"] = services_table["capacity"].subtract(axis_1, fill_value=0)
        houses_table[f"service_demand_left_value"] = houses_table[f"service_demand_value"].subtract(
            axis_0, fill_value=0
        )

        distance_matrix = distance_matrix.drop(
            index=services_table[services_table["capacity_left"] == 0].index.values,
            columns=houses_table[houses_table[f"service_demand_left_value"] == 0].index.values,
            errors="ignore",
        )
        selection_range += selection_range
        if len(distance_matrix.columns) > 0 and len(distance_matrix.index) > 0:
            return self._provision_loop_gravity(houses_table, services_table, distance_matrix, selection_range,
                                                destination_matrix, temp_destination_matrix)
        else:
            return destination_matrix

    def _provision_loop_linear(
        self,
        houses_table,
        services_table,
        distance_matrix,
        selection_range,
        destination_matrix,
    ):
        def declare_variables(loc):
            name = loc.name
            nans = loc.isna()
            index = nans[~nans].index
            t = pd.Series(
                [pulp.LpVariable(name=f"route_{name}_{I}", lowBound=0, cat="Integer") for I in index],
                index,
                dtype="object",
            )
            loc[~nans] = t
            return loc

        select = distance_matrix[distance_matrix.iloc[:] <= selection_range]
        select = select.apply(lambda x: 1 / (x + 1), axis=1)

        select = select.loc[:, ~select.columns.duplicated()].copy(deep=True)
        select = select.loc[~select.index.duplicated(), :].copy(deep=True)

        variables = select.apply(lambda x: declare_variables(x), axis=1)

        prob = pulp.LpProblem("problem", pulp.LpMaximize)
        for col in variables.columns:
            t = variables[col].dropna().values
            if len(t) > 0:
                prob += (
                    pulp.lpSum(t) <= houses_table[f"service_demand_left_value"][col],
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
                columns=list(set(set(destination_matrix.columns) - set(result.columns))),
                index=destination_matrix.index,
            ),
            how="outer",
        )
        result = result.fillna(0)
        destination_matrix = destination_matrix + result
        axis_1 = destination_matrix.sum(axis=1)
        axis_0 = destination_matrix.sum(axis=0)
        services_table["capacity_left"] = services_table["capacity"].subtract(axis_1, fill_value=0)
        houses_table[f"service_demand_left_value"] = houses_table[f"service_demand_value"].subtract(
            axis_0, fill_value=0
        )

        distance_matrix = distance_matrix.drop(
            index=services_table[services_table["capacity_left"] == 0].index.values,
            columns=houses_table[houses_table[f"service_demand_left_value"] == 0].index.values,
            errors="ignore",
        )

        selection_range += selection_range
        if len(distance_matrix.columns) > 0 and len(distance_matrix.index) > 0:
            return self._provision_loop_linear(houses_table, services_table, distance_matrix, selection_range,
                                               destination_matrix)
        else:
            return destination_matrix

    def _is_shown(self, buildings, services):
        if self.user_selection_zone:
            buildings["is_shown"] = buildings.within(self.user_selection_zone)
            a = buildings["is_shown"].copy()
            t = [self.destination_matrix[a[a].index.values].apply(lambda x: len(x[x > 0]) > 0, axis=1)]
            services["is_shown"] = pd.concat([a[a] for a in t])
        else:
            buildings["is_shown"] = True
            services["is_shown"] = True
        return buildings, services
