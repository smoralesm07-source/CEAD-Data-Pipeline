from cead_pipeline.primary import probe_payload


def test_probe_payload():
    payload=probe_payload(2025,"01101")
    assert ("anio[]","2025") in payload
    assert ("comuna[]","1101") in payload
    assert ("grupo[]","401") in payload
