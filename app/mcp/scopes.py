"""OAuth scopes the connector grants and checks (DECISIONS.md CONN-AS)."""

READ = "leadpilot:read"
WRITE = "leadpilot:write"
# Claude appends this to every authorization request; granting it is what
# makes the token endpoint issue a refresh token.
OFFLINE_ACCESS = "offline_access"

SUPPORTED = (READ, WRITE, OFFLINE_ACCESS)
