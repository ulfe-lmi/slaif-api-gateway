"""Service-layer exports."""

__all__ = ["KeyService"]


def __getattr__(name: str):
    if name == "KeyService":
        from slaif_gateway.services.key_service import KeyService

        return KeyService
    raise AttributeError(name)
