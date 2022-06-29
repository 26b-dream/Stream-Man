# TODO: Make all of this actually secure, this isn't actually secure in any way

# Standard Library
from dataclasses import dataclass


@dataclass
class HIDIVESecrets:
    EMAIL: str = "EMAIL"
    PASSWORD: str = "PASSWORD"


@dataclass
class CrunchyrollSecrets:
    EMAIL: str = "EMAIL"
    PASSWORD: str = "PASSWORD"


@dataclass
class NetflixSecrets:
    PIN: int = 0000
    NAME: str = "NAME"


@dataclass
class HuluSecrets:
    EMAIL: str = "EMAIL"
    PASSWORD: str = "PASSWORD"
    NAME: str = "NAME"
