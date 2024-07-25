"""Data models for verifier log analysis"""

import json
import re
from dataclasses import dataclass
from enum import Flag, auto

import requests
import pandas as pd

import settings
from util import csv_bool_to_bool, is_nully_str, is_valid_url


class CPUArchitecture(Flag):
    """Enumerated CPU instruction set architectures"""

    X86 = auto()
    ARM = auto()


class Probe(Flag):
    """Enumerated verifier probes"""

    CURL = auto()
    LEGACY = auto()


class OSDCTLVersion(Flag):
    """Enumerated versions of osdctl"""

    V0_34_0 = auto()
    V0_35_0 = auto()
    B994063A = auto()


class ClusterVerifierRecord:
    """Represents a single run of the verifier recorded in a single JSON blob"""

    cid: str
    duration: float
    osdctl_version: OSDCTLVersion
    probe: Probe
    arch: CPUArchitecture
    output: str
    errors: set[str]
    egress_failures: set[str]

    egress_url_regex = re.compile(settings.EGRESS_URL_REGEX_PATTERN)
    verifier_error_regex = re.compile(settings.VERIFIER_ERROR_REGEX_PATTERN)
    ignored_endpoints = settings.IGNORED_ENDPOINTS

    def __init__(self, cid, duration, osdctl_version, probe, arch, output):
        self.cid = cid
        if is_nully_str(self.cid):
            raise ValueError("ClusterVerifierRecord required a cluster ID (cid)")

        self.duration = duration
        self.osdctl_version = osdctl_version
        self.probe = probe
        self.arch = arch

        self.output = output
        self.errors = set()
        self.egress_failures = set()
        if not is_nully_str(self.output):
            self.errors = self.__get_errors()
            self.egress_failures = self.__get_egress_failures()

    def __get_errors(self) -> set[str]:
        """Parse the output log for error messages"""
        errors = set(re.findall(self.verifier_error_regex, self.output))

        return errors

    def __get_egress_failures(self) -> set[str]:
        """Parses the output log for the domains that were blocked"""
        egress_failures = set(re.findall(self.egress_url_regex, self.output))

        return egress_failures

    @classmethod
    def from_dict(cls, in_dict: dict[str, str]) -> "ClusterVerifierRecord":
        """Create an instance of this class from a dictionary produced by json.load"""

        _duration = float(in_dict["duration"])
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

        p_string = in_dict["probe"].strip().upper()
        if in_dict["probe"].strip().upper() == "PROBE":
            p_string = "CURL"
        _probe = Probe[p_string]
        
        _arch = CPUArchitecture[in_dict["arch"].strip().upper()]

        v_string = "V" + in_dict["osdctl_version"].strip().replace(".", "_")
        if len(in_dict["osdctl_version"].strip()) > 8:
            v_string = in_dict["osdctl_version"][:8].strip().upper()
        _osdctl_version = OSDCTLVersion[v_string]

        return cls(_cid, _duration, _osdctl_version, _probe, _arch, _output)

    def to_dict(self):
        return {
            "cid": self.cid,
            "osdctl_version": self.osdctl_version.name,
            "probe": self.probe.name,
            "arch": self.arch.name,
            "errors": self.errors,
            "egress_failures": self.egress_failures,
        }

    def __sub__(self, other):
        """Subtraction operator tries to capture the differences between two CVRs"""
        if self.cid != other.cid:
            raise ArithmeticError("cannot subtract CVRs with differing cluster IDs")
        _cid = self.cid
        _duration = self.duration - other.duration
        _arch = self.arch | other.arch
        _probe = self.probe | other.probe
        _osdctl_version = self.osdctl_version | other.osdctl_version

        _errors = self.errors ^ other.errors
        _egress_failures = self.egress_failures ^ other.egress_failures

        res = ClusterVerifierRecord(_cid, _duration, _osdctl_version, _probe, _arch, "")
        res.errors = self.errors ^ other.errors
        res.egress_failures = self.egress_failures ^ other.egress_failures

        return res

    def __eq__(self, other):
        """
        Equality operator checks if independent variables (i.e., everything other than
        duration, egress_failures, and errors) align.
        """
        return (
            self.cid == other.cid
            and self.arch == other.arch
            and self.probe == other.probe
            and self.osdctl_version == other.osdctl_version
        )

    def __repr__(self):
        return f"<{self.duration:.2f}s {self.probe} run of {self.osdctl_version} on {self.arch} with {len(self.egress_failures)} egress failures and {len(self.errors)} errors>"


def cvrs_to_dataframe(cvr_list: list[ClusterVerifierRecord]):
    df = pd.DataFrame(cvr.to_dict() for cvr in cvr_list)
    df["probe"] = pd.Categorical(df["probe"], categories=[x.name for x in Probe])
    df["arch"] = pd.Categorical(df["arch"], categories=[x.name for x in CPUArchitecture])
    df["osdctl_version"] = pd.Categorical(df["osdctl_version"], categories=[x.name for x in OSDCTLVersion])
    return df
