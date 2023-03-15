"""Backup policy configuration (RPO targets per database)."""
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
        return self.databases.get(name.lower(), self.defaults)

    def is_excluded(self, name):
        return name.lower() in {x.lower() for x in self.exclude}


def _policy(section, base, where):
    if not isinstance(section, dict):
        raise ConfigError("%s must be an object" % where)
    unknown = set(section) - POLICY_KEYS
    if unknown:
        raise ConfigError("%s: unknown key(s): %s" % (where, ", ".join(sorted(unknown))))
    values = {}
    for key, value in section.items():
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
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc)) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError("%s is not valid JSON: %s" % (path, exc)) from exc
    return parse_config(data)
