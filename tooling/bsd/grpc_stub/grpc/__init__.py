"""Import-only stub for `grpc`, for BSD targets where grpcio cannot be built.

`qdrant-client` hard-imports `grpc` at load time (even to use its *local*,
in-process store, which speaks no gRPC), and grpcio has no OpenBSD wheel and its
bundled `upb` fails to compile there. The Odysseus vector store uses qdrant-client
**local mode only** — it never opens a gRPC channel at runtime — so satisfying the
import is sufficient and correct; nothing here is ever called.

`tooling/provision_bsd_memory.sh` copies this package into the venv's
site-packages only when real grpcio is absent. If grpcio is present it wins
(this stub is never installed over it).

Every attribute resolves to a *distinct* placeholder subclass, because
`qdrant_client.connection` uses several grpc symbols as **base classes** in a
single `class` statement (sync and async client interceptors); returning the same
object for each would raise "duplicate base class". A permissive metaclass makes
the placeholders usable as base classes, decorators, and attribute chains alike.
"""

_cache = {}


def _make(name):
    c = _cache.get(name)
    if c is None:
        c = _cache[name] = _Meta(name, (_Stub,), {})
    return c


class _Meta(type):
    def __getattr__(cls, n):            # e.g. grpc.aio.UnaryUnaryClientInterceptor
        return _make(cls.__name__ + "." + n)


class _Stub(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):        # usable as a decorator
        return self

    def __getattr__(self, n):
        return self

    def __class_getitem__(cls, item):   # e.g. grpc.Foo[bar]
        return cls


def __getattr__(name):                  # any top-level grpc.X
    return _make(name)
