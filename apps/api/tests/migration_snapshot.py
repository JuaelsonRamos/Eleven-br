"""Projection for tests of migrations before 0013; new defaults are tested separately."""

LEGACY_JSON = "(to_jsonb(t) - ARRAY['category', 'positions', 'primary_position', 'roster_version'])"
