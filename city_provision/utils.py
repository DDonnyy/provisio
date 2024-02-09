import numpy as np
import pandas as pd
import networkit as nk
import shapely
import geopandas as gpd


def load_graph_geometry(G_nx, node=True, edge=False):
    if edge:
        for u, v, data in G_nx.edges(data=True):
            data["geometry"] = shapely.wkt.loads(data["geometry"])
    if node:
        for u, data in G_nx.nodes(data=True):
            data["geometry"] = shapely.geometry.Point([data["x"], data["y"]])
    return G_nx


def get_subgraph(G_nx, attr, value):
    return G_nx.edge_subgraph(
        [
            (u, v, k)
            for u, v, k, d in G_nx.edges(data=True, keys=True)
            if d[attr] in value
        ]
    )


def get_nx2nk_idmap(G_nx):
    idmap = dict(
        (id, u) for (id, u) in zip(G_nx.nodes(), range(G_nx.number_of_nodes()))
    )
    return idmap


def get_nk_attrs(G_nx):
    attrs = dict(
        (u, {"x": d[-1]["x"], "y": d[-1]["y"]})
        for (d, u) in zip(G_nx.nodes(data=True), range(G_nx.number_of_nodes()))
    )
    return pd.DataFrame(attrs.values(), index=attrs.keys())


def convert_nx2nk(G_nx, idmap=None, weight=None):

    if not idmap:
        idmap = get_nx2nk_idmap(G_nx)
    n = max(idmap.values()) + 1
    edges = list(G_nx.edges())

    if weight:
        G_nk = nk.Graph(n, directed=G_nx.is_directed(), weighted=True)
        for u_, v_ in edges:
            u, v = idmap[u_], idmap[v_]
            d = dict(G_nx[u_][v_])
            u_ = int(u_)
            v_ = int(v_)
            if len(d) > 1:
                for d_ in d.values():
                    v__ = G_nk.addNodes(2)
                    u__ = v__ - 1
                    w = round(d_[weight], 1) if weight in d_ else 1
                    G_nk.addEdge(u, v, w)
                    G_nk.addEdge(u_, u__, 0, addMissing=True)
                    G_nk.addEdge(v_, v__, 0, addMissing=True)
            else:
                d_ = list(d.values())[0]
                w = round(d_[weight], 1) if weight in d_ else 1
                G_nk.addEdge(u, v, w)
    else:
        G_nk = nk.Graph(n, directed=G_nx.is_directed())
        for u_, v_ in edges:
            u, v = idmap[u_], idmap[v_]
            G_nk.addEdge(u, v)

    return G_nk


def get_nk_distances(nk_dists, loc):
    target_nodes = loc.index
    source_node = loc.name
    distances = [nk_dists.getDistance(source_node, node) for node in target_nodes]
    return pd.Series(data=distances, index=target_nodes)


def provision_matrix_transform(destination_matrix, services, buildings):
    def subfunc(loc):
        try:
            return [
                {"house_id": int(k), "demand": int(v), "service_id": int(loc.name)}
                for k, v in loc.to_dict().items()
            ]
        except:
            return np.NaN

    def subfunc_geom(loc):
        return shapely.geometry.LineString(
            (
                buildings["geometry"][loc["house_id"]],
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
    sel = distribution_links["house_id"].isin(
        buildings.index.values
    ) & distribution_links["service_id"].isin(services.index.values)
    sel = distribution_links.loc[sel[sel].index.values]
    distribution_links = distribution_links.set_geometry(sel.apply(lambda x: subfunc_geom(x), axis=1))
    return distribution_links


def additional_options(
    buildings,
    services,
    Matrix,
    destination_matrix,
    normative_distance,
    service_type,
    selection_zone,
    valuation_type,
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
    buildings[f"{service_type}_service_demand_left_value_{valuation_type}"] = buildings[
        f"{service_type}_service_demand_value_{valuation_type}"
    ]
    buildings[f"{service_type}_supplyed_demands_within"] = 0
    buildings[f"{service_type}_supplyed_demands_without"] = 0
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
        buildings[f"{service_type}_service_demand_left_value_{valuation_type}"] = (
            buildings[f"{service_type}_service_demand_left_value_{valuation_type}"].sub(
                within.add(without, fill_value=0), fill_value=0
            )
        )
        buildings[f"{service_type}_supplyed_demands_within"] = buildings[
            f"{service_type}_supplyed_demands_within"
        ].add(within, fill_value=0)
        buildings[f"{service_type}_supplyed_demands_without"] = buildings[
            f"{service_type}_supplyed_demands_without"
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
    buildings[f"{service_type}_provison_value"] = (
        buildings[f"{service_type}_supplyed_demands_within"]
        / buildings[f"{service_type}_service_demand_value_{valuation_type}"]
    )
    services["service_load"] = services["capacity"] - services["capacity_left"]
    buildings = buildings[
        [x for x in buildings.columns if service_type in x] + ["building_id"] +["geometry"]
    ]
    return buildings, services
