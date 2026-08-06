import json
from pathlib import Path

from muon_analysis.io.runinfo import (
    build_runinfo,
    discover_runinfo_path,
    discover_runtype,
    get_runinfo,
    list_runtypes,
    normalize_run_id,
    RunInfoNotFoundError,
    RunInfoValidationError,
)


def _payload():
    return {
        "run_info": {
            "runtype": "run_R8520",
            "outfile_name": "foo",
            "outfile_path": "/data/raw/RAW",
            "custom_field": 42,
        },
        "run_option": {
            "run_tag": "pmt test",
            "run_comment": ["spe gain"],
        },
    }


def test_normalize():
    assert normalize_run_id(179) == "00179"
    assert normalize_run_id("00179") == "00179"


def test_build_runinfo(tmp_path):
    rinfo = tmp_path / "run_R8520" / "00179" / "runinfo.json"
    rinfo.parent.mkdir(parents=True)
    payload = _payload()
    rinfo.write_text(json.dumps(payload))
    ri = build_runinfo(179, rinfo, payload)
    assert ri.run_id == "00179"
    assert ri.raw_dir == Path("/data/raw/RAW")
    assert ri.datatype == ["spe gain"]
    assert ri.metadata["custom_field"] == 42


def test_runinfo_detection_error(tmp_path):
    root = tmp_path
    try:
        discover_runinfo_path(179, root)
        raise AssertionError("expected RunInfoNotFoundError")
    except RunInfoNotFoundError:
        pass


def test_get_runinfo_roundtrip(tmp_path):
    root = tmp_path
    rinfo = root / "run_R8520" / "00179" / "runinfo.json"
    rinfo.parent.mkdir(parents=True)
    rinfo.write_text(json.dumps(_payload()))
    ri = get_runinfo(179, root)
    assert ri.datatype == ["spe gain"]


def test_invalid_run_tag(tmp_path):
    payload = _payload()
    payload["run_option"]["run_tag"] = "wrong"
    try:
        build_runinfo(179, Path("/x/runinfo.json"), payload,
                      strict_validation=True)
        raise AssertionError("expected RunInfoValidationError")
    except RunInfoValidationError:
        pass


def test_invalid_run_tag_non_strict_yields_empty_datatype(tmp_path):
    payload = _payload()
    payload["run_option"]["run_tag"] = "wrong"
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ri = build_runinfo(179, Path("/x/runinfo.json"), payload)
    assert ri.datatype == []


def _write_runtype(root, runtype, run_id):
    p = root / runtype / str(run_id).zfill(5) / "runinfo.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = _payload()
    payload["run_info"]["runtype"] = runtype
    p.write_text(json.dumps(payload))
    return p


def test_list_runtypes(tmp_path):
    _write_runtype(tmp_path, "run6_Xe", 183)
    _write_runtype(tmp_path, "run7_Xe", 184)
    (tmp_path / "not_a_run").mkdir()
    rts = list_runtypes(tmp_path)
    assert set(rts) == {"run6_Xe", "run7_Xe"}


def test_list_runtypes_with_candidates(tmp_path):
    _write_runtype(tmp_path, "run6_Xe", 183)
    rts = list_runtypes(tmp_path, candidates=["run6_Xe", "run7_Xe"])
    assert rts == ["run6_Xe"]


def test_discover_runtype_auto(tmp_path):
    _write_runtype(tmp_path, "run6_Xe", 183)
    assert discover_runtype(183, tmp_path) == "run6_Xe"


def test_get_runinfo_auto_discovers_runtype(tmp_path):
    p = _write_runtype(tmp_path, "run6_Xe", 183)
    payload = json.loads(p.read_text())
    payload["run_info"]["runtype"] = "run6_Xe"
    p.write_text(json.dumps(payload))
    ri = get_runinfo(183, tmp_path)  # no explicit runtype
    assert ri.runtype == "run6_Xe"
    assert ri.raw_dir == Path("/data/raw/RAW")


def test_get_runinfo_explicit_runtype_scopes(tmp_path):
    _write_runtype(tmp_path, "run6_Xe", 183)
    ri = get_runinfo(183, tmp_path, runtype="run6_Xe")
    assert ri.runtype == "run6_Xe"


def test_discover_runtype_not_found(tmp_path):
    try:
        discover_runtype(99999, tmp_path)
        raise AssertionError("expected RunInfoNotFoundError")
    except RunInfoNotFoundError:
        pass
