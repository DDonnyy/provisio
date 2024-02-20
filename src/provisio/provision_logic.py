import logging
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import pulp
from pydantic import BaseModel, InstanceOf, field_validator, model_validator

from .utils import (
    additional_options,
    provision_matrix_transform,
)

# pylint: disable=singleton-comparison


class CityProvision(BaseModel):
    services: InstanceOf[gpd.GeoDataFrame]
    demanded_buildings: InstanceOf[gpd.GeoDataFrame]
    adjacency_matrix: InstanceOf[pd.DataFrame]
    threshold: int
    user_selection_zone: Optional[dict] = None  # TODO вынести в метод
    calculation_type: str = "gravity"
    _destination_matrix = None

    @field_validator("demanded_buildings")
    @classmethod
    def ensure_buildings(cls, v: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if "demand" not in v.columns:
            raise KeyError(
                "The column 'demand' was not found in the provided 'demanded_buildings' GeoDataFrame. "
                "This attribute corresponds to the number of demands for the selected service in each building."
            )
        v = v.copy()
        v["demand"] = v["demand"].replace(0, np.nan)
        rows_count = v.shape[0]
        v = v.dropna(subset="demand")
        dif_rows_count = rows_count - v.shape[0]
        v["demand_left"] = v["demand"]
        if dif_rows_count > 0:
            logging.info(
                "%s rows were deleted from the 'demanded_buildings' GeoDataFrame due"
                " to null or zero values in the 'demand' column",
                dif_rows_count,
            )
        return v

    @field_validator("services")
    @classmethod
    def ensure_services(cls, v: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if "capacity" not in v.columns:
            raise KeyError(
                "Column 'capacity' was not found in provided 'services' GeoDataFrame. This attribute "
                "corresponds to the total capacity for each service."
            )
        v = v.copy()
        rows_count = v.shape[0]
        v["capacity"] = v["capacity"].replace(0, np.nan)
        v = v.dropna(subset="capacity")
        dif_rows_count = rows_count - v.shape[0]
        if v.shape[0] == 0:
            raise ValueError("Column 'capacity' in 'services' GeoDataFrame  has no valid value")
        if dif_rows_count > 0:
            logging.info(
                "%s rows were deleted from the 'services' GeoDataFrame due to null values in the 'capacity' column",
                dif_rows_count,
            )
        v["capacity_left"] = v["capacity"]
        return v

    @model_validator(mode="after")
    def delete_useless_matrix_columns(self) -> "CityProvision":
        self.adjacency_matrix = self.adjacency_matrix.copy()
        indexes = set(self.demanded_buildings.index.tolist())
        columns = set(self.adjacency_matrix.columns.tolist())
        dif = columns ^ indexes
        self.adjacency_matrix.drop(columns=(list(dif)), inplace=True)
        return self

    def _get_provisions(self) -> (gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame):
        self._calculate_provisions()
        additional_options(
            self.demanded_buildings,
            self.services,
            self.adjacency_matrix,
            self._destination_matrix,
            self.threshold,
        )
        self.demanded_buildings, self.services = self._is_shown(self.demanded_buildings, self.services)
        self.demanded_buildings = self.demanded_buildings.fillna(0)
        self.services = self.services.fillna(0)

        return (
            self.demanded_buildings,
            self.services,
            provision_matrix_transform(
                self._destination_matrix,
                self.services[self.services["is_shown"] == True],
                self.demanded_buildings[self.demanded_buildings["is_shown"] == True],
                self.adjacency_matrix,
            ),
        )

    def _calculate_provisions(self):
        self._destination_matrix = pd.DataFrame(
            0,
            index=self.adjacency_matrix.index,
            columns=self.adjacency_matrix.columns,
        )

        if self.calculation_type == "gravity":
            self._destination_matrix = self._provision_loop_gravity(
                self.demanded_buildings.copy(),
                self.services.copy(),
                self.adjacency_matrix.copy() + 1,
                self.threshold,
                self._destination_matrix.copy(),
            )

        elif self.calculation_type == "linear":
            self._destination_matrix = self._provision_loop_linear(
                self.demanded_buildings.copy(),
                self.services.copy(),
                self.adjacency_matrix.copy(),
                self.threshold,
                self._destination_matrix.copy(),
            )

    def _provision_loop_gravity(
        self,
        houses_table: gpd.GeoDataFrame,
        services_table: gpd.GeoDataFrame,
        distance_matrix: pd.DataFrame,
        selection_range,
        destination_matrix: pd.DataFrame,
        temp_destination_matrix=None,
    ):
        def _calculate_flows_y(loc):
            c = services_table.loc[loc.name]["capacity_left"]
            d = houses_table.loc[loc.index]["demand_left"]
            p = d / loc
            p = p / p.sum()
            if p.sum() == 0:
                return loc
            rng = np.random.default_rng(seed=0)
            r = pd.Series(0, p.index)
            choice = np.unique(rng.choice(p.index, int(c), p=p.values), return_counts=True)
            choice = r.add(pd.Series(choice[1], choice[0]), fill_value=0)
            return choice

        def _balance_flows_to_demands(loc):
            d = houses_table.loc[loc.name]["demand_left"]
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
            return loc

        temp_destination_matrix = distance_matrix.apply(lambda x: _calculate_flows_y(x[x <= selection_range]), axis=1)
        temp_destination_matrix = temp_destination_matrix.fillna(0)
        temp_destination_matrix = temp_destination_matrix.apply(lambda x: _balance_flows_to_demands(x))
        temp_destination_matrix = temp_destination_matrix.fillna(0)
        destination_matrix = destination_matrix.add(temp_destination_matrix, fill_value=0)
        axis_1 = destination_matrix.sum(axis=1)
        axis_0 = destination_matrix.sum(axis=0)
        services_table["capacity_left"] = services_table["capacity"].subtract(axis_1, fill_value=0)
        houses_table["demand_left"] = houses_table["demand"].subtract(axis_0, fill_value=0)

        distance_matrix = distance_matrix.drop(
            index=services_table[services_table["capacity_left"] == 0].index.values,
            columns=houses_table[houses_table["demand_left"] == 0].index.values,
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
                temp_destination_matrix,
            )
        return destination_matrix

    def _provision_loop_linear(
        self,
        houses_table: gpd.GeoDataFrame,
        services_table: gpd.GeoDataFrame,
        distance_matrix: pd.DataFrame,
        selection_range,
        destination_matrix: pd.DataFrame,
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
                    pulp.lpSum(t) <= houses_table["demand_left"][col],
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
        houses_table["demand_left"] = houses_table["demand"].subtract(axis_0, fill_value=0)

        distance_matrix = distance_matrix.drop(
            index=services_table[services_table["capacity_left"] == 0].index.values,
            columns=houses_table[houses_table["demand_left"] == 0].index.values,
            errors="ignore",
        )

        selection_range += selection_range
        if len(distance_matrix.columns) > 0 and len(distance_matrix.index) > 0:
            return self._provision_loop_linear(
                houses_table, services_table, distance_matrix, selection_range, destination_matrix
            )
        return destination_matrix

    def _is_shown(self, buildings, services):
        if self.user_selection_zone:
            buildings["is_shown"] = buildings.within(self.user_selection_zone)
            a = buildings["is_shown"].copy()
            t = [self._destination_matrix[a[a].index.values].apply(lambda x: len(x[x > 0]) > 0, axis=1)]
            services["is_shown"] = pd.concat([a[a] for a in t])
        else:
            buildings["is_shown"] = True
            services["is_shown"] = True
        return buildings, services
