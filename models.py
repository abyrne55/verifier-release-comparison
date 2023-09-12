"""Data models for verifier log analysis"""
import json
import re
from datetime import datetime
from enum import Enum, IntEnum, auto
from typing import Optional

import htmllistparse
import requests
from requests_cache import install_cache, NEVER_EXPIRE

import settings
from util import csv_bool_to_bool, is_nully_str, is_valid_url

# Enable HTTP caching globally
install_cache(".vla-http-cache", backend=("sqlite"), expire_after=NEVER_EXPIRE)


class OCMState(IntEnum):
    """
    States in which an OCM cluster could be, according to
    https://gitlab.cee.redhat.com/service/uhc-clusters-service/-/blob/master/pkg/models/clusters.go

    Int values are assigned such that states can only progress to a greater value
    """

    WAITING = 0
    PENDING = 1
    VALIDATING = 2
    INSTALLING = 3
    READY = 4
    ERROR = 5
    UNINSTALLING = 6
    POWERING_DOWN = 7
    HIBERNATING = 8
    RESUMING = 9
    UNKNOWN = 100

    def is_transient(self):
        """
        Returns True if representing a "non-steady state" (e.g., installing, validating)
        """
        return self not in [
            self.READY,
            self.ERROR,
            self.UNINSTALLING,
            self.HIBERNATING,
        ]

    def __repr__(self):
        return f"{self.__class__.__name__}.{self.name}"


class InFlightState(Enum):
    """
    States in which an in-flight check could be, according to
    https://gitlab.cee.redhat.com/service/uhc-clusters-service/-/blob/master/pkg/models/inflight_checks.go
    """

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"

    def __repr__(self):
        return f"{self.__class__.__name__}.{self.name}"


class Outcome(Enum):
    """Statistical and error outcomes"""

    TRUE_NEGATIVE = auto()
    TRUE_POSITIVE = auto()
    FALSE_NEGATIVE = auto()
    FALSE_POSITIVE = auto()
    ERROR = auto()


class ClusterVerifierRecord:
    """Represents a single row in the CSV"""

    remote_log_egress_regex = re.compile(settings.REMOTE_LOG_EGRESS_REGEX_PATTERN)
    remote_log_error_regex = re.compile(settings.REMOTE_LOG_ERROR_REGEX_PATTERN)
    remote_log_file_name = settings.REMOTE_LOG_FILE_NAME
    remote_log_auth = settings.REMOTE_LOG_AUTH
    force_failure_endpoints = settings.FORCE_FAILURE_ENDPOINTS

    def __init__(
        self,
        timestamp: datetime,
        cid: str,
        cname: Optional[str],
        ocm_state: Optional[OCMState],
        ocm_inflight_states: Optional[list[str]],
        found_verifier_s3_logs: Optional[bool],
        found_all_tests_passed: Optional[bool],
        found_egress_failures: Optional[bool],
        log_download_url: str,
    ):
        self.timestamp = timestamp
        self.cid = cid
        self.cname = cname
        self.ocm_state = ocm_state
        self.ocm_inflight_states = ocm_inflight_states
        self.found_verifier_s3_logs = found_verifier_s3_logs
        self.found_all_tests_passed = found_all_tests_passed
        self.found_egress_failures = found_egress_failures
        self.log_download_url = log_download_url

        # __logs will keep cache downloaded logs
        self.__logs = {}

        # hostedcluster will keep track of this cluster's hypershift status
        self.__hostedcluster = None

        # reached_states keeps track of all states in which we've seen this cluster
        self.reached_states = set()
        if self.ocm_state is not None:
            self.reached_states.update([self.ocm_state])

        # suspected_deleted will be set to True if this record is seen disappearing from OCM
        self.suspect_deleted = False

    def is_incomplete(self) -> bool:
        """Returns True if the CVR is missing information usually obtained from OCM"""
        return [self.cname, self.ocm_state, self.ocm_inflight_states] == [None] * 3

    def get_outcome(self) -> Outcome:
        """Calculate the statistical outcome of this (assumed completed) test record"""
        if (
            self.is_incomplete()
            or len(self.reached_states) == 0
            or len(self.ocm_inflight_states) == 0
        ):
            return None
        if (
            OCMState.READY in self.reached_states
            and InFlightState.PASSED in self.ocm_inflight_states
        ):
            return Outcome.TRUE_NEGATIVE
        if (
            OCMState.READY not in self.reached_states
            and InFlightState.PASSED not in self.ocm_inflight_states
        ):
            return Outcome.TRUE_POSITIVE
        if (
            OCMState.READY not in self.reached_states
            and InFlightState.PASSED in self.ocm_inflight_states
        ):
            return Outcome.FALSE_NEGATIVE
        if (
            OCMState.READY in self.reached_states
            and InFlightState.PASSED not in self.ocm_inflight_states
        ):
            # This *might* be a false positive; check if failed egress endpoints contain
            # a force-failure endpoint
            ff_endpoints = self.get_egress_failures() & self.force_failure_endpoints
            if len(ff_endpoints) > 0:
                return Outcome.TRUE_POSITIVE

            # Now check if logs contain an error
            if len(self.get_errors()) > 0:
                return Outcome.ERROR

            # Finished check edge cases, so it must be a genuine false positive
            return Outcome.FALSE_POSITIVE
        return None

    def get_errors(self) -> set[str]:
        """Parse downloaded logs for error messages"""
        # Trigger log download if necessary
        self.__download_logs()

        # Iterate over each subnet's logs and populate set with blocked egresses
        errors = set()
        for _, log in self.__logs.items():
            errors.update(re.findall(self.remote_log_error_regex, log))

        return errors

    def get_egress_failures(self) -> set[str]:
        """Parses the log files for the domains that were blocked"""
        # Trigger log download if necessary
        self.__download_logs()

        # Iterate over each subnet's logs and populate set with blocked egresses
        egress_failures = set()
        for _, log in self.__logs.items():
            egress_failures.update(re.findall(self.remote_log_egress_regex, log))

        return egress_failures

    def is_hostedcluster(self) -> bool:
        """
        Parses the OCM description file stored in log_download_url and returns True if
        this cluster is an HCP/HyperShift HostedCluster (i.e. "hypershift.enabled").
        May return None if OCM description file is unreadable/missing.
        """
        if self.__hostedcluster is None:
            # HCP status not cached for this cluster ID
            desc_req = requests.get(
                self.log_download_url + "desc.json",
                timeout=5,
                auth=self.remote_log_auth,
            )
            try:
                self.__hostedcluster = bool(desc_req.json()["hypershift"]["enabled"])
            except requests.exceptions.JSONDecodeError:
                # Blank/malformed cluster description JSON. Allow default to None
                pass
        return self.__hostedcluster

    def __download_logs(self):
        """
        Downloads verifier logs stored in log_download_url for each subnet and populates __logs
        """
        if not self.__logs:
            _, listing = htmllistparse.fetch_listing(
                self.log_download_url, timeout=5, auth=self.remote_log_auth
            )
            subnets = (lnk.name for lnk in listing if "subnet" in lnk.name)
            for subnet in subnets:
                self.__logs[subnet] = requests.get(
                    self.log_download_url + subnet + self.remote_log_file_name,
                    timeout=5,
                    auth=self.remote_log_auth,
                ).text

    def __add__(self, other):
        """
        Adding two records together produces the "most current" set of info from both.
        """
        greater_cvr = max(self, other)
        lesser_cvr = min(self, other)

        if greater_cvr.is_incomplete() and not lesser_cvr.is_incomplete():
            lesser_cvr.suspect_deleted = True
            lesser_cvr.timestamp = greater_cvr.timestamp
            return lesser_cvr

        greater_cvr.reached_states.update(lesser_cvr.reached_states)
        return greater_cvr

    def __gt__(self, other):
        """
        We consider another CVR to be "greater" if it's newer or is same age and has
        a greater-or-equal OCMState
        """
        try:
            if self.cid != other.cid:
                raise ArithmeticError(
                    f"Cannot compare {self.__class__.__name__}s with different cluster IDs"
                )
            return self.timestamp > other.timestamp or (
                self.timestamp >= other.timestamp and self.ocm_state > other.ocm_state
            )
        except (AttributeError, TypeError) as exc:
            raise ArithmeticError(
                f"Cannot operate {self.__class__.__name__} against other types"
            ) from exc

    def __lt__(self, other):
        """Defined so that we can use functions like max() and sort()"""
        return not self > other

    def __repr__(self):
        reached_states_str = ""
        if len(self.reached_states) > 0:
            reached_states_str = (
                f"[{''.join(repr(s)+',' for s in self.reached_states)}]"
            )
        in_flight_str = ""
        if self.ocm_inflight_states is not None:
            in_flight_str = (
                f"[{''.join(repr(s)+',' for s in self.ocm_inflight_states)}]"
            )
        return (
            f"<CVR.{self.cid if self.cname is None else self.cname} "
            f"{'' if self.ocm_state is None else repr(self.ocm_state)} "
            f"{reached_states_str} "
            f"{in_flight_str}{'!INC!' if self.is_incomplete() else ''}"
            f"{'!DEL!' if self.suspect_deleted else ''}>"
        )

    @classmethod
    def from_dict(cls, in_dict: dict[str, str]):
        """Create an instance of this class from a dictionary produced by csv.DictReader"""

        # Mandatory Fields
        timestamp = datetime.fromisoformat(in_dict["timestamp"].replace("Z", "+00:00"))
        cid = in_dict["cid"].strip()
        if is_nully_str(cid):
            raise ValueError(
                "Cannot create ClusterVerifierRecord without cluster ID (cid)"
            )

        # Optional Fields
        try:
            cname = None if is_nully_str(in_dict["cname"]) else in_dict["cname"].strip()
            found_verifier_s3_logs = csv_bool_to_bool(in_dict["found_verifier_s3_logs"])
            found_all_tests_passed = csv_bool_to_bool(in_dict["found_all_tests_passed"])
            found_egress_failures = csv_bool_to_bool(in_dict["found_egress_failures"])
            ocm_state_str = in_dict["ocm_state"].upper().strip()
            ocm_inflight_states_str = in_dict["ocm_inflight_states"].strip()
        except AttributeError as exc:
            # .strip()/.lower() will raise AttributeError for non-str types, but we
            # consider this a ValueError
            raise ValueError("Non-str-typed keys passed to from_dict()") from exc

        # Finish processing "strictly typed" fields (these will raise their own exceptions)
        ocm_state = None
        if not is_nully_str(ocm_state_str):
            ocm_state = OCMState[ocm_state_str]

        ocm_inflight_states = None
        if not is_nully_str(ocm_inflight_states_str):
            ocm_inflight_states = list(
                InFlightState(s) for s in json.loads(in_dict["ocm_inflight_states"])
            )

        log_download_url = None
        if is_valid_url(in_dict["log_download_url"]):
            log_download_url = in_dict["log_download_url"]

        return cls(
            timestamp,
            cid,
            cname,
            ocm_state,
            ocm_inflight_states,
            found_verifier_s3_logs,
            found_all_tests_passed,
            found_egress_failures,
            log_download_url,
        )
