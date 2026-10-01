"""Projection for tests of migrations before 0013/0015; new defaults are tested separately."""

LEGACY_JSON = (
    "(to_jsonb(t) - ARRAY['category', 'positions', 'primary_position', 'roster_version', "
    "'accepts_challenges', 'fixture_id', 'municipality_code', 'location_confirmed_at', "
    "'callup_version', 'called_up'] - "
    "CASE WHEN to_jsonb(t) ? 'event_id' AND to_jsonb(t) ? 'name' "
    "THEN ARRAY['response', 'command_id'] ELSE ARRAY[]::text[] END)"
)
# Values newer than the downgraded migrations (0013 category, 0016 confirmed location).
# Only rows that hold newer data: touching other rows would queue deferred FK checks.
CLEAR_NEWER_TEAM_DATA = (
    "UPDATE teams SET category = NULL, municipality_code = NULL, location_confirmed_at = NULL "
    "WHERE category IS NOT NULL OR municipality_code IS NOT NULL"
)
