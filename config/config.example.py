# Standard Library
from dataclasses import dataclass


@dataclass
class HIDIVESecrets:
    EMAIL: str = "EMAIL"
    PASSWORD: str = "PASSWORD"


@dataclass
class CrunchyRollSecrets:
    EMAIL: str = "EMAIL"
    PASSWORD: str = "PASSWORD"


@dataclass
class NetflixSecrets:
    PIN: int = 0000
    NAME: str = "NAME"
