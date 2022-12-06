from collections.abc import MutableMapping
from typing import Any, Callable, Dict, Tuple, Union

import numpy as np
import xarray as xr
import zarr

from xsimlab import Model
from xsimlab.process import variables_dict


_DIMENSION_KEY = "_ARRAY_DIMENSIONS"


def _variable_value_getter(process_obj: Any, var_name: str) -> Callable:
    def value_getter():
        return getattr(process_obj, var_name)

    return value_getter


def _get_var_info(dataset: xr.Dataset, model: Model) -> Dict[Tuple[str, str], Dict]:
    var_info = {}

    var_clocks = {k: v for k, v in dataset.xsimlab.output_vars.items()}
    var_clocks.update({vk: None for vk in model.index_vars})

    for var_key, clock in var_clocks.items():
        p_name, v_name = var_key
        p_obj = model[p_name]
        v_obj = variables_dict(type(p_obj))[v_name]

        var_info[var_key] = {
            "clock": clock,
            "name": f"{p_name}__{v_name}",
            "obj": v_obj,
            "value_getter": _variable_value_getter(p_obj, v_name),
        }

    return var_info


def default_fill_value_from_dtype(dtype):
    if dtype.kind == "f":
        return np.nan
    elif dtype.kind in "c":
        return (
            default_fill_value_from_dtype(dtype.type().real.dtype),
            default_fill_value_from_dtype(dtype.type().imag.dtype),
        )
    else:
        return 0


class ZarrOutputStore:
    def __init__(
        self,
        dataset: xr.Dataset,
        model: Model,
        zobject: Union[zarr.Group, MutableMapping, str, None],
    ):
        self.dataset = dataset
        self.model = model

        self.in_memory = False
        self.consolidated = False

        if isinstance(zobject, zarr.Group):
            self.zgroup = zobject
        elif zobject is None:
            self.zgroup = zarr.group(store=zarr.MemoryStore())
            self.in_memory = True
        else:
            self.zgroup = zarr.group(store=zobject)

        self.output_vars = dataset.xsimlab.output_vars_by_clock
        self.output_save_steps = dataset.xsimlab.get_output_save_steps()

        self.var_info = _get_var_info(dataset, model)

        self.mclock_dim = dataset.xsimlab.master_clock_dim
        self.clock_sizes = dataset.xsimlab.clock_sizes

        # initialize clock incrementers
        self.clock_incs = {clock: 0 for clock in dataset.xsimlab.clock_coords}
        self.clock_incs[None] = 0

    def write_input_xr_dataset(self):
        # output/index variables already in input dataset will be replaced
        drop_vars = [vi["name"] for vi in self.var_info.values()]
        ds = self.dataset.drop(drop_vars, errors="ignore")

        ds.xsimlab._reset_output_vars(self.model, {})
        ds.to_zarr(self.zgroup.store, group=self.zgroup.path, mode="a")

    def _create_zarr_dataset(self, var_key: Tuple[str, str], name=None):
        var = self.var_info[var_key]["obj"]

        if name is None:
            name = self.var_info[var_key]["name"]

        array = self.var_info[var_key]["value_getter"]()
        if np.isscalar(array):
            array = np.asarray(array)

        clock = self.var_info[var_key]["clock"]

        if clock is None:
            shape = array.shape
        else:
            shape = (self.clock_sizes[clock],) + tuple(array.shape)

        chunks = True
        compressor = "default"

        # TODO: more performance assessment
        # if self.in_memory:
        #     chunks = False
        #     compressor = None

        zdataset = self.zgroup.create_dataset(
            name,
            shape=shape,
            chunks=chunks,
            dtype=array.dtype,
            compressor=compressor,
            fill_value=default_fill_value_from_dtype(array.dtype),
        )

        # add dimension labels and variable attributes as metadata
        dim_labels = None

        for dims in var.metadata["dims"]:
            if len(dims) == array.ndim:
                dim_labels = list(dims)

        if dim_labels is None:
            raise ValueError(
                f"Output array of {array.ndim} dimension(s) "
                f"for variable '{name}' doesn't match any of "
                f"its accepted dimension(s): {var.metadata['dims']}"
            )

        if clock is not None:
            dim_labels.insert(0, clock)

        zdataset.attrs[_DIMENSION_KEY] = tuple(dim_labels)
        if var.metadata["description"]:
            zdataset.attrs["description"] = var.metadata["description"]
        zdataset.attrs.update(var.metadata["attrs"])

        # reset consolidated since metadata has just been updated
        self.consolidated = False

    def write_output_vars(self, istep: int):
        save_istep = self.output_save_steps.isel(**{self.mclock_dim: istep})

        for clock, var_keys in self.output_vars.items():
            if clock is None and istep != -1:
                continue
            if not save_istep.data_vars.get(clock, True):
                continue

            clock_inc = self.clock_incs[clock]

            if clock_inc == 0:
                for vk in var_keys:
                    self._create_zarr_dataset(vk)

            for vk in var_keys:
                zkey = self.var_info[vk]["name"]
                array = self.var_info[vk]["value_getter"]()

                if clock is None:
                    self.zgroup[zkey][:] = array
                else:
                    self.zgroup[zkey][clock_inc] = array

            self.clock_incs[clock] += 1

    def write_index_vars(self):
        for var_key in self.model.index_vars:
            _, vname = var_key
            self._create_zarr_dataset(var_key, name=vname)

            array = self.var_info[var_key]["value_getter"]()
            self.zgroup[vname][:] = array

    def consolidate(self):
        zarr.consolidate_metadata(self.zgroup.store)
        self.consolidated = True

    def open_as_xr_dataset(self) -> xr.Dataset:
        if self.in_memory:
            chunks = None
        else:
            chunks = "auto"

        ds = xr.open_zarr(
            self.zgroup.store,
            group=self.zgroup.path,
            chunks=chunks,
            consolidated=self.consolidated,
            # disable mask (not nice with zarr default fill_value=0)
            mask_and_scale=False,
        )

        if self.in_memory:
            # lazy loading may be confusing for the default, in-memory option
            ds.load()
        else:
            # load scalar data vars (there might be many of them: model params)
            for da in ds.data_vars.values():
                if not da.dims:
                    da.load()

        return ds
