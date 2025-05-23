"""GraphQL scalars & connection primitives
This module is split into *two* logical sections but lives in the same
canvas for easy review.  In a real repo you would break these into
``graphql/scalars.py`` and ``graphql/connections.py`` and import them
(wherever `settings.BASE_DIR / "ecommerce_platform/graphql"` exists).
"""

# ---------------------------------------------------------------------------
# scalars.py – custom Graphene scalars
# ---------------------------------------------------------------------------
import json
import graphene


class JSONScalar(graphene.Scalar):
    """A permissive JSON scalar.

    * **serialize**: Always returns the Python object untouched so that
      Graphene can re‑serialize it to the client.

    * **parse_value**: Accepts dict / list directly (typical when
      variables are sent) or a JSON‑encoded string.

    * **parse_literal**: Handles hard‑coded literals in the query DSL.
    """

    @staticmethod
    def serialize(value):
        return value

    @staticmethod
    def parse_value(value):
        # When the client uses variables, Graphene hands us native Python
        # objects already.  Only decode when we receive a string.
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            # Fall back to raw value – GraphQL validation will scream if
            # the type truly mismatches.
            return value

    @staticmethod
    def parse_literal(node):  # type: ignore[override]
        return JSONScalar.parse_value(getattr(node, "value", node))


# ---------------------------------------------------------------------------
# connections.py – Relay helpers
# ---------------------------------------------------------------------------
from graphene import relay


class CountedConnection(relay.Connection):
    """A reusable Relay connection that exposes `totalCount`."""

    class Meta:
        abstract = True

    total_count = graphene.Int()

    @staticmethod
    def resolve_total_count(root, info, **_kwargs):
        # Graphene sets `root.length` when using `DjangoFilterConnectionField`.
        return getattr(root, "length", len(root.edges))


# Example specialisation -----------------------------------------------------

# To keep this file independent from model‑specific types we import lazily
# inside Meta.  Graphene resolves the dotted path at schema build time.

class ProductConnection(CountedConnection):
    class Meta:
        node = "ecommerce_platform.graphql.types.product.ProductType"
