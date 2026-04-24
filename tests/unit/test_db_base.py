from slaif_gateway.db.base import Base, metadata, naming_convention


def test_base_metadata_exists() -> None:
    assert Base.metadata is metadata


def test_naming_convention_has_core_keys() -> None:
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in naming_convention
