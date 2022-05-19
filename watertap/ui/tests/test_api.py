"""
Tests for api module.
"""
# standard library
from io import StringIO
import os
from pathlib import Path

# third-party
import pytest

# from pyomo.environ import units as pyunits
from pyomo.environ import Var, Set, Reals
from watertap.ui.api import *

# Mocking and fixtures


class MockSubBlock1:
    name = "subblock1"
    doc = "sub-block 1"


class MockSubBlock2:
    name = "subblock2"
    doc = "sub-block 2"


class MockSubBlock3:
    name = "subblock3"
    doc = "sub-block 3"
    # sub-blocks
    subblock1 = MockSubBlock1()
    set_block_interface(subblock1, {})

    def component_map(self, **kwargs):
        return {"subblock1": getattr(self, "subblock1")}


class MockBlock:
    # name = "watertap.ui.tests.test_api.MockBlock"
    name = "Flowsheet"
    doc = "flowsheet description"
    foo_var = Var(name="foo_var", initialize=0.0, within=Reals)
    foo_var.construct()
    bar_idx = Set(initialize=[0, 1, 2])
    bar_idx.construct()
    bar_var = Var(bar_idx, name="bar_var", initialize=[0.0, 0.0, 0.0], within=Reals)
    bar_var.construct()
    # sub-blocks
    subblock1 = MockSubBlock1()
    set_block_interface(subblock1, {})
    subblock2 = MockSubBlock2()
    set_block_interface(subblock2, {})
    subblock3 = MockSubBlock3()  # note: no interface

    def component_map(self, **kwargs):
        return {
            "subblock1": getattr(self, "subblock1"),
            "subblock2": getattr(self, "subblock2"),
            "subblock3": getattr(self, "subblock3"),
        }


@pytest.fixture
def mock_block():
    return MockBlock()


def build_options(display_name=False, description=False, variables=0,
                  readonly_variables=[]):
    opts = {}
    if display_name:
        opts["display_name"] = "foo"
    if description:
        opts["description"] = "This is a foo"
    if variables >= 0:
        v = []
        for i in range(min(variables, 2)):
            name = "foo" if i == 0 else "bar"
            entry = {"display_name": f"{name} variable", "name": f"{name}_var"}
            if i in readonly_variables:
                entry["readonly"] = True
            v.append(entry)
        opts["variables"] = v
    return opts


# Tests
# -----


@pytest.mark.unit
def test_export_variables_simple(mock_block):
    export_variables(mock_block, name="Feed Z0", desc="Zero-Order feed block",
                     variables=["foo_var", "bar_var"])


@pytest.mark.unit
def test_export_variables_complex(mock_block):
    export_variables(mock_block, name="Feed Z0", desc="Zero-Order feed block",
                     variables=[{"name": "foo_var", "readonly": True},
                                "bar_var"])


@pytest.mark.unit
def test_set_block_interface(mock_block):
    # no keys
    set_block_interface(mock_block, {})
    # invalid key
    data = {"test": "data"}
    with pytest.raises(ValueError):
        set_block_interface(mock_block, data)
    # ok key
    data = {"display_name": "foo"}
    set_block_interface(mock_block, data)
    # existing object
    obj = BlockInterface(mock_block, data)
    set_block_interface(mock_block, obj)


@pytest.mark.unit
def test_get_block_interface(mock_block):
    # data
    data = {"display_name": "foo"}
    set_block_interface(mock_block, data)
    assert get_block_interface(mock_block) is not None
    # existing object
    obj = BlockInterface(mock_block, data)
    set_block_interface(mock_block, obj)
    obj2 = get_block_interface(mock_block)
    assert obj2 is obj


@pytest.mark.unit
def test_block_interface_constructor(mock_block):
    for i in range(4):  # combinations of display_name and description
        disp, desc = (i % 2) == 0, ((i // 2) % 2) == 0
        obj = BlockInterface(
            mock_block, build_options(display_name=disp, description=desc)
        )
        obj.get_exported_variables()  # force looking at contents


@pytest.mark.unit
def test_block_interface_get_exported_variables(mock_block):
    # no variables section
    obj = BlockInterface(mock_block, build_options(variables=-1))
    assert len(list(obj.get_exported_variables())) == 0
    # empty variables section
    obj = BlockInterface(mock_block, build_options(variables=0))
    assert len(list(obj.get_exported_variables())) == 0
    # 1 variable
    obj = BlockInterface(mock_block, build_options(variables=1))
    assert len(list(obj.get_exported_variables())) == 1
    # 2 variables
    obj = BlockInterface(mock_block, build_options(variables=2))
    assert len(list(obj.get_exported_variables())) == 2


@pytest.mark.unit
def test_workflow_actions():
    wfa = WorkflowActions
    assert wfa.build is not None
    assert wfa.solve is not None


@pytest.mark.unit
def test_flowsheet_interface_constructor(mock_block):
    fsi = FlowsheetInterface(build_options(variables=2))
    fsi.set_block(mock_block)


@pytest.mark.unit
def test_flowsheet_interface_as_dict(mock_block):
    obj = FlowsheetInterface(build_options(variables=2))
    obj.set_block(mock_block)
    d = obj.as_dict()
    fs = d["blocks"][0]
    assert "variables" in fs


@pytest.mark.unit
def test_flowsheet_interface_save(mock_block, tmpdir):
    obj = FlowsheetInterface(build_options(variables=2))
    obj.set_block(mock_block)
    # string
    filename = "test-str.json"
    str_path = os.path.join(tmpdir, filename)
    obj.save(str_path)
    assert os.path.exists(os.path.join(tmpdir, filename))
    # path
    filename = "test-path.json"
    path_path = Path(tmpdir) / filename
    obj.save(path_path)
    assert os.path.exists(os.path.join(tmpdir, filename))
    # stream
    strm = StringIO()
    obj.save(strm)
    assert strm.getvalue() != ""


@pytest.mark.unit
def test_flowsheet_interface_load(mock_block, tmpdir):
    obj = FlowsheetInterface(build_options(variables=2))
    obj.set_block(mock_block)
    filename = "saved.json"
    obj.save(Path(tmpdir) / filename)
    # print(f"@@ saved: {json.dumps(obj.as_dict(), indent=2)}")
    obj2 = FlowsheetInterface.load_from(Path(tmpdir) / filename, mock_block)
    assert obj2 == obj


@pytest.mark.unit
def test_flowsheet_interface_load_missing(mock_block, tmpdir):
    obj = FlowsheetInterface(build_options(variables=2))
    obj.set_block(mock_block)
    filename = "saved.json"
    # manual save, and remove some variables
    d = obj.as_dict()
    block = d["blocks"][0]
    block["variables"] = []
    fp = open(Path(tmpdir) / filename, "w", encoding="utf-8")
    json.dump(d, fp)
    fp.close()
    # reload
    obj2 = FlowsheetInterface.load_from(Path(tmpdir) / filename, mock_block)
    assert obj2.get_var_extra() != {}
    assert obj2.get_var_missing() == {}


class ScalarValueBlock:
    name = "Flowsheet"
    doc = "flowsheet description"
    foo_var = Var(name="foo_var", initialize=0.0, within=Reals)
    foo_var.construct()
    bar_var = Var(name="bar_var", initialize=0.0, within=Reals)
    bar_var.construct()


@pytest.mark.unit
def test_flowsheet_interface_load_readonly(tmpdir):
    vkey = BlockSchemaDefinition.VALU_KEY
    block = ScalarValueBlock()
    export_variables(block, variables=["foo_var", {"name": "bar_var", "readonly": True}])
    obj = FlowsheetInterface({"display_name": "Flowsheet"})
    obj.set_block(block)
    readonly_index = 1
    filename = "saved.json"
    # manual save, and change the variables
    d = obj.as_dict()
    dblock = d["blocks"][0]
    # Save old values, modify all the variables (add 1)
    old_values = []
    for var_entry in dblock["variables"]:
        value = var_entry[vkey]
        old_values.append(value)
        var_entry[vkey] = value + 1
    # Write out
    fp = open(Path(tmpdir) / filename, "w", encoding="utf-8")
    json.dump(d, fp)
    fp.close()
    # Reload
    obj.load(Path(tmpdir) / filename)
    # See that variables have changed, except readonly one
    d = obj.as_dict()
    block = d["blocks"][0]
    for i, var_entry in block["variables"]:
        if i == readonly_index:
            assert var_entry[vkey] == old_values[i]
        else:
            assert var_entry[vkey] == old_values[i] + 1


def test_flowsheet_interface_get_var(mock_block):
    fsi = FlowsheetInterface(build_options(variables=1))
    fsi.set_block(mock_block)
    with pytest.raises(KeyError):
        fsi.get_var_missing()
    with pytest.raises(KeyError):
        fsi.get_var_extra()


@pytest.mark.unit
def test_schema():
    schema = FlowsheetInterface.get_schema()
    assert schema.validate({}) is not None  # missing 'name' and 'blocks'
    assert schema.validate({"name": "x", "blocks": []}) is None  # ok
    assert (
        schema.validate({"name": "x", "blocks": "foo"}) is not None
    )  # blocks must be list
    assert (
        schema.validate({"name": "x", "blocks": [], "extra": {}}) is None
    )  # ok (extra ok)
    assert (
        schema.validate({"name": "x", "blocks": [{"name": "x", "blocks": []}]}) is None
    )  # nested


@pytest.mark.component
def test_schema_performance():
    import time

    schema = FlowsheetInterface.get_schema()

    def section(name, num_vars):
        d = {"name": name, "blocks": []}
        variables = []
        for i in range(num_vars):
            v = {
                "name": f"v{i}",
                "display_name": f"variable {i}",
                "units": "dimensionless",
            }
            variables.append(v)
        d["variables"] = variables
        return d

    # build a big data object
    d = {"name": "__root__", "blocks": []}
    nblocks = [100, 10]
    nvars = 100
    for i in range(nblocks[0]):
        block = section(f"block{i}", nvars)
        for j in range(nblocks[1]):
            block2 = section(f"block{i}_{j}", nvars)
            block["blocks"].append(block2)
        d["blocks"].append(block)

    print(
        f"validating flowsheet with {nblocks[0]  * nblocks[1]} blocks each with {nvars} variables"
    )
    t0 = time.time()
    schema.validate(d)
    t1 = time.time()
    dur = t1 - t0
    print(
        f"time to validate = {dur:.3f}s or {dur/(nblocks[0]  * nblocks[1])*1000} ms/block"
    )

    # should never take more than 1/50th sec per block (sub-ms times are normal)
    assert dur < (0.02 * nblocks[0] * nblocks[1])


def test_add_action_type(mock_block):
    fsi = FlowsheetInterface(build_options(variables=1))
    fsi.set_block(mock_block)

    # Add 2 actions:
    #   cook <- eat
    fsi.add_action_type("cook")
    fsi.add_action_type("eat", deps=["cook"])
    fsi.set_action("cook", add_action_cook, dish=_dish)
    fsi.set_action("eat", add_action_eat)

    # Check actions
    assert fsi.get_action("cook") == (add_action_cook, {"dish": _dish})
    assert fsi.get_action("eat") == (add_action_eat, {})

    # Run actions
    fsi.run_action("eat")

    # Add some problematic actions
    with pytest.raises(KeyError):
        # unknown dependency
        fsi.add_action_type("go-inside", deps=["open-door"])

    with pytest.raises(ValueError):
        # cannot depend on self
        fsi.add_action_type("a1", deps=["a1"])


_dish = "mac&cheese"
_cooked = None


def add_action_cook(dish=None, **kwargs):
    global _cooked
    _cooked = dish
    print("cook")


def add_action_eat(**kwargs):
    assert _cooked == _dish
    print("eat")
