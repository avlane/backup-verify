"""Backup policy configuration (RPO targets per database)."""
import fnmatch
import json
from dataclasses import dataclass, field, replace
from typing import Optional


class ConfigError(ValueError):
    """The configuration file is unreadable or invalid."""


POLICY_KEYS = {"full_max_age_hours", "diff_max_age_hours", "log_max_age_minutes"}
TOP_LEVEL_KEYS = {"defaults", "databases", "exclude"}


@dataclass(frozen=True)
class Policy:
    full_max_age_hours: float = 26.0
    diff_max_age_hours: Optional[float] = None
    log_max_age_minutes: Optional[float] = 30.0


@dataclass
class Config:
    defaults: Policy = field(default_factory=Policy)
    databases: dict = field(default_factory=dict)
    exclude: list = field(default_factory=lambda: ["tempdb"])

    def policy_for(self, name):
        """An exact name wins; otherwise the first matching wildcard section, in file order."""
        key = name.lower()
        if key in self.databases:
            return self.databases[key]
        for pattern, policy in self.databases.items():
            if fnmatch.fnmatchcase(key, pattern):
                return policy
        return self.defaults

    def is_excluded(self, name):
        key = name.lower()
        return any(fnmatch.fnmatchcase(key, pattern.lower()) for pattern in self.exclude)


def _policy(section, base, where):
    if not isinstance(section, dict):
        raise ConfigError("%s must be an object" % where)
    unknown = set(section) - POLICY_KEYS
    if unknown:
        raise ConfigError("%s: unknown key(s): %s" % (where, ", ".join(sorted(unknown))))
    values = {}
    for key, value in section.items():
        if value is False:  # TOML has no null
            value = None
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ConfigError("%s: %s must be a positive number or null" % (where, key))
        values[key] = value
    return replace(base, **values)


def parse_config(data):
    if not isinstance(data, dict):
        raise ConfigError("the top level of the config must be an object")
    unknown = set(data) - TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError("unknown top-level key(s): %s" % ", ".join(sorted(unknown)))
    defaults = _policy(data.get("defaults", {}), Policy(), "defaults")
    databases = {}
    for name, section in data.get("databases", {}).items():
        databases[name.lower()] = _policy(section, defaults, "databases.%s" % name)
    exclude = data.get("exclude", ["tempdb"])
    if not isinstance(exclude, list):
        raise ConfigError("exclude must be a list of database names")
    return Config(defaults, databases, list(exclude))


def load_config(path):
    """Load a policy file; `.toml` files are parsed as TOML, anything else as JSON."""
    is_toml = str(path).lower().endswith(".toml")
    try:
        if is_toml:
            import tomllib

            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        else:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc)) from exc
    except ValueError as exc:  # json.JSONDecodeError and tomllib.TOMLDecodeError
        raise ConfigError("%s is not valid %s: %s" % (path, "TOML" if is_toml else "JSON", exc)) from exc
    return parse_config(data)
