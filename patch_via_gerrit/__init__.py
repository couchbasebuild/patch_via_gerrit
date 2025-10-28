"""patch_via_gerrit - Tool used to modify a local 'repo sync' with changes from Gerrit."""


def __getattr__(name: str) -> str:
    if name != "__version__":
        msg = f"module {__name__} has no attribute {name}"
        raise AttributeError(msg)

    from importlib.metadata import version

    return version("patch-via-gerrit")
