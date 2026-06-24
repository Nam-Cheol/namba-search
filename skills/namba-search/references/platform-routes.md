# Platform Routes

Namba Search tries public, no-auth routes before generic HTTP strategies when
the platform publishes a suitable route. Examples include public feeds,
syndication endpoints, oEmbed, registry APIs, and media metadata tools.

Site-specific routing belongs in platform adapters or reference notes, not in
the generic WAF engine. Generic engine code must remain host-neutral except
for the explicit Phase 0 public-route boundary.
