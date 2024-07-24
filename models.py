"""Data models for verifier log analysis"""

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum, unique
from typing import Optional

import requests

import settings
from util import csv_bool_to_bool, is_nully_str, is_valid_url


@unique
class CPUArchitecture(StrEnum):
    """Enumerated CPU instruction set architectures"""

    X86 = "x86"
    ARM = "arm"


@unique
class Probe(StrEnum):
    """Enumerated verifier probes"""

    CURL = "curl"
    LEGACY = "legacy"

class OSDCTLVersion(StrEnum):
    """Enumerated versions of osdctl"""

    USES_VERIFIER_v0_4_11 = "0.34"
    USES_VERIFIER_v1_0_0 = "0.35"


@dataclass
class ClusterVerifierRecord:
    """Represents a single run of the verifier recorded in a single JSON blob"""

    duration: int
    cid: str
    osdctl_version: OSDCTLVersion
    probe: Probe
    arch: CPUArchitecture
    logpath: str
    output: str

    egress_url_regex = re.compile(settings.EGRESS_URL_REGEX_PATTERN)
    verifier_error_regex = re.compile(settings.VERIFIER_ERROR_REGEX_PATTERN)
    ignored_endpoints = settings.IGNORED_ENDPOINTS

    def get_errors(self) -> set[str]:
        """Parse the output log for error messages"""
        errors = set()
        errors.update(re.findall(self.verifier_error_regex, self.output))

        return errors

    def get_egress_failures(self) -> set[str]:
        """Parses the output log for the domains that were blocked"""
        egress_failures = set()
        egress_failures.update(re.findall(self.egress_url_regex, self.output))

        return egress_failures

    @classmethod
    def from_dict(cls, in_dict: dict[str, str]) -> 'ClusterVerifierRecord':
        """Create an instance of this class from a dictionary produced by csv.DictReader"""

        # Mandatory Fields
        _duration = timedelta(seconds=int(in_dict["duration"]))
        _cid = in_dict["cid"].strip()
        if is_nully_str(_cid):
            raise ValueError(
                "Cannot create ClusterVerifierRecord without cluster ID (cid)"
            )

        _output = in_dict["output"].strip()
        if is_nully_str(_output):
            raise ValueError(
                "Cannot create ClusterVerifierRecord without an output log"
            )

        _probe = Probe(in_dict["probe"].strip())
        _arch = CPUArchitecture(in_dict["arch"].strip())
        _osdctl_version = OSDCTLVersion(in_dict["osdctl_version"].strip())

        # Optional Fields
        try:
            _logpath = in_dict["logpath"].strip()
        except AttributeError as exc:
            # .strip()/.lower() will raise AttributeError for non-str types, but we
            # consider this a ValueError
            raise ValueError("Non-str-typed keys passed to from_dict()") from exc

        return cls(
            _duration, _cid, _osdctl_version, _probe, _arch, _logpath, _output
        )
