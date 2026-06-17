"""The SUPERVOID ENTANGLED ecosystem map.

A small, declarative description of where SUPERVOID Publishing sits within the
wider holding so the hierarchy is never collapsed into a single product:

    SUPERVOID ENTANGLED          parent ecosystem / holding
      ├── SUPERVOID Publishing   this system (books, graphic novels, editorial)
      ├── SUPERVOID Movies       future film production division
      └── LOGOSFORGE             writing app / narrative engine subsystem
"""
from __future__ import annotations

from pydantic import BaseModel


class EcosystemMember(BaseModel):
    key: str
    name: str
    role: str
    current: bool  # True for the system serving this API


class Ecosystem(BaseModel):
    parent: str
    this_system: str
    members: list[EcosystemMember]


ECOSYSTEM = Ecosystem(
    parent="SUPERVOID ENTANGLED",
    this_system="SUPERVOID Publishing",
    members=[
        EcosystemMember(
            key="supervoid_publishing",
            name="SUPERVOID Publishing",
            role="Publishing house — books, graphic novels, editorial production.",
            current=True,
        ),
        EcosystemMember(
            key="supervoid_movies",
            name="SUPERVOID Movies",
            role="Film and screen production division (future).",
            current=False,
        ),
        EcosystemMember(
            key="logosforge",
            name="LOGOSFORGE",
            role="Writing app / narrative engine subsystem.",
            current=False,
        ),
    ],
)
