from google.protobuf.json_format import MessageToDict


def to_jsonable(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value.__class__, "pb"):
        return MessageToDict(value.__class__.pb(value))
    return value
