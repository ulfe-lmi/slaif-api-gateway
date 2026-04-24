from fastapi import FastAPI


def test_package_imports() -> None:
    import slaif_gateway

    assert slaif_gateway is not None


def test_fastapi_app_exists() -> None:
    from slaif_gateway.main import app

    assert isinstance(app, FastAPI)
