"""All built-in ideas of the bank in one read-only dict (key -> idea). Written in the seeds_*.py files, one group per kind of content."""
from __future__ import annotations

from .seeds_fitness import FITNESS
from .seeds_mind import PERSONAL, PSYCHOLOGY
from .seeds_money import BUSINESS, ECONOMY, SUCCESS
from .seeds_mystery import MYSTERY

BUILTIN_IDEAS: dict[str, dict] = dict([*PSYCHOLOGY, *PERSONAL, *FITNESS, *ECONOMY, *SUCCESS, *BUSINESS, *MYSTERY])
