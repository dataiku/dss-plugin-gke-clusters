import sys

from collections import Iterable, Mapping
from six import text_type

if sys.version_info > (3,):
    dku_basestring_type = str
else:
    dku_basestring_type = basestring

def _get_in_object_or_array(o, chunk, d):
    if isinstance(chunk, int):
        if chunk >= 0 and chunk < len(o):
            return o[chunk] if o[chunk] is not None else d
        else:
            return d
    else:
        return o.get(chunk, d)

def _safe_get_value(o, chunks, default_value=None):
    if len(chunks) == 1:
        return _get_in_object_or_array(o, chunks[0], default_value)
    else:
        return _safe_get_value(_get_in_object_or_array(o, chunks[0], {}), chunks[1:], default_value)

def is_none_or_blank(x):
    return x is None or (isinstance(x, text_type) and len(x.strip()) == 0)

def has_not_blank_property(d, k):
    return k in d and not is_none_or_blank(d[k])

def default_if_blank(x, d):
    if is_none_or_blank(x):
        return d
    else:
        return x

def merge_objects(a, b):
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        r = {}
        ks = set(a.keys()).union(set(b.keys()))
        for k in ks:
            if k in b and k in a:
                r[k] = merge_objects(a[k], b[k])
            elif k in b:
                r[k] = b[k]
            else:
                r[k] = a[k]
        return r
    elif isinstance(a, dku_basestring_type) and isinstance(b, dku_basestring_type):
        return b
    elif isinstance(a, Iterable) and isinstance(b, Iterable):
        ret = []
        for x in a:
            ret.append(x)
        for x in b:
            ret.append(x)
        return ret
    elif b is not None:
        return b
    else:
        return a
