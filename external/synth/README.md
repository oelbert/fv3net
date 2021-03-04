Synth
=====

The package `synth` provides tools for generating synthetic xarray datasets for testing purposes. Compared to real data, it is much easier and cheaper to manage code for generating synthetic using software version control tools like git.

Usage
-----

This packages allows the user to build up a "schema" describing their data. A schema is a reduced description of a zarr/xarray dataset that can

1.  be easily serialized to disk and loaded again
2.  used to generate a random dataset
3.  validate an existing dataset

This package defines a set of dataclasses defining a schema. It also contains fixtures for datasets used by VCM-ML in training models, allowing for unit and regression testing of data pipelines.

The function synth.read\_schema\_from\_zarr can be used to generate a schema from an existing dataset. For example, suppose we have loaded a zarr group like this:

    import sys
    import fsspec
    import zarr
    import synth

    url = "gs://path/to/data.zarr"
    mapper = fsspec.get_mapper(url)
    group = zarr.open_group(mapper)

This data could comprise many gigabytes, so it is unweildy to manage, and use within a testing framework. To generate a condensed description, you can generate a reduced "schema" like this:

    schema = synth.read_schema_from_zarr(
        group, coords=("time", "tile", "grid_xt", "grid_yt")
    )

Next, `schema` can be serialized to json and dumped to disk like this:

    with open("schema.json", "w") as f:
        synth.dump(schema, f)

The json file includes a "version" entry to ensure that schema's generated by older versions of this code remain legible to new versions.

> **note**
>
> While old schema may be read by newer versions of the code, there is no guarantee that `generate` will return the same values, so checks of bit-for-bit reproducibilty may need to be updated.

The json file can then be checked into version control and loaded inside of a test script like this:

    with open("schema.json" , "r") as f:
        schema = synth.load(f)

A fake xarray dataset can be created:

    ds = synth.generate(schema)

The data for each chunk will be identically generated from a uniform distribution. The upper and lower bounds of this distribution are set by default in the code, but can be overrided using the `ranges` argument of `synth.generate`.

A dataset can be validated by checking its schema against a reference schema:

    with open("schema.json" , "r") as f:
        ref_schema = synth.load(f)

    zarr_schema = synth.read_schema_from_zarr(
        group, coords=("time", "tile", "grid_xt", "grid_yt")
    )

    assert zarr_schema == ref_schema

Note that the equality operator `==` checks the following:

1.  the dataset has the same coordinates in terms of names and dimension names
2.  the dataset has the same variables in terms of names, dimension names, and data shape, type, and chunks.

Note that coordinate shapes and values and dataset, coordinate, and variable attributes are not compared. The equality operator can also be used directly on coordinate and variable schema.

Pytest dataset fixtures
-----------------------

The package contains fixtures for two datasets used for ML training in fv3net: nudging tendencies, and fine-res apparent sources. The fixtures in `synth._dataset_fixtures` may be imported into a `conftest.py` file and then used in testing mappers and other functions that load or use these data:: from synth import ( dataset\_fixtures\_dir, data\_source\_name, nudging\_dataset\_path, fine\_res\_dataset\_path, data\_source\_path, grid\_dataset, )

Fixtures exist for each invididual dataset (e.g, `nudging_dataset_path`), returning its path in a temporary testing directory, and for a parametrized fixture (`data_source_path`) that will sequentially return the paths of all datasets.

Existing tools
--------------

Python has some [rich tools](https://faker.readthedocs.io/en/master/) for generating fake data, but nothing specialized to xarray/zarr.