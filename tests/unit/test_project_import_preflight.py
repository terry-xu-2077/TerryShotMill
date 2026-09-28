from io import BytesIO

import pytest
from shotmill.application.project_import_preflight import preflight_project_import
from shotmill.application.project_transfer_records import serialize_project_transfer_records
from shotmill.errors import ConflictError
from shotmill.media.project_package import write_project_package
from test_project_transfer_validation import graph


@pytest.mark.parametrize("tamper", [None, "missing", "extra", "records"])
def test_preflight_validates_all_layers_before_exposing_files(tmp_path, tamper):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    staging = tmp_path / "staging"
    staging.mkdir()
    records = serialize_project_transfer_records(graph())
    files = {"output.mp4": source}
    if tamper == "missing":
        files.clear()
    elif tamper == "extra":
        files["extra.bin"] = source
    elif tamper == "records":
        records["jobs"][0]["provider_profile_snapshot"] = {"baseUrl": "http://attacker"}
    stream = BytesIO()
    write_project_package(stream, records, files)
    stream.seek(0)
    if tamper:
        with pytest.raises(ConflictError), preflight_project_import(stream, staging_parent=staging):
            pytest.fail("Invalid package exposed to importer")
    else:
        with preflight_project_import(stream, staging_parent=staging) as package:
            extracted = package.files["output.mp4"]
            assert extracted.read_bytes() == b"media"
            assert package.source.project.id == "p"
        assert not extracted.exists()
    assert list(staging.iterdir()) == []
    assert source.read_bytes() == b"media"
