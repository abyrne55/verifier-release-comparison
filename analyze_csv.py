import csv
import json
import re
import sys
import urllib
from datetime import datetime
from enum import Enum
from typing import Optional


def csv_bool_to_bool(csv_bool_str):
    if csv_bool_str.strip().lower() == "true":
        return True
    if csv_bool_str.strip().lower() == "false":
        return False
    return None


def is_valid_url(url):
    regex = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return url is not None and regex.search(url)


def is_nully(s):
    """
    Returns True if s is None, an empty or whitespace-filled string, or some variation of "NULL"
    """
    if s is None:
        return True
    s_strip = s.lower().strip()
    return s_strip == "" or s_strip == "null"


class OCMState(Enum):
    """
    States in which an OCMcluster could be, according to 
    https://gitlab.cee.redhat.com/service/uhc-clusters-service/-/blob/master/pkg/models/clusters.go
    """

    VALIDATING = "validating"
    WAITING = "waiting"
    PENDING = "pending"
    INSTALLING = "installing"
    READY = "ready"
    ERROR = "error"
    UNINSTALLING = "uninstalling"
    UNKNOWN = "unknown"
    POWERING_DOWN = "powering_down"
    RESUMING = "resuming"
    HIBERNATING = "hibernating"


class ClusterVerifierRecord:
    """Represents a single row in the CSV"""

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

    def is_transient(self):
        """
        Returns True if cluster is in a "non-steady state" (e.g., installing, validating)
        """
        return self.ocm_state not in [OCMState.READY, OCMState.ERROR, OCMState.UNINSTALLING, OCMState.HIBERNATING]

    def __gt__(self, other):
        return self.timestamp > other.timestamp

    def __lt__(self, other):
        return self.timestamp < other.timestamp

    @classmethod
    def from_dict(cls, in_dict: dict[str, str]):
        """Create an instance of this class from a dictionary produced by csv.DictReader"""
        
        # Mandatory Fields
        timestamp = datetime.fromisoformat(in_dict["timestamp"].replace("Z", "+00:00"))
        cid = in_dict["cid"].strip()
        if is_nully(cid):
            raise ValueError("Cannot create ClusterVerifierRecord without cluster ID (cid)")
        
        # Optional Fields
        try:
            cname = None if is_nully(in_dict["cname"]) else in_dict["cname"].strip()
            found_verifier_s3_logs = csv_bool_to_bool(in_dict["found_verifier_s3_logs"])
            found_all_tests_passed = csv_bool_to_bool(in_dict["found_all_tests_passed"])
            found_egress_failures = csv_bool_to_bool(in_dict["found_egress_failures"])
            ocm_state_str = in_dict["ocm_state"].lower().strip()
            ocm_inflight_states_str = in_dict["ocm_inflight_states"].strip()
        except AttributeError as exc:
            # .strip()/.lower() will raise AttributeError for non-str types, but we consider 
            # this a ValueError
            raise ValueError("Non-str-typed keys passed to from_dict()") from exc

        # Finish processing "strictly typed" fields (these will raise their own exceptions)
        ocm_state = None if is_nully(ocm_state_str) else OCMState(ocm_state_str)
        ocm_inflight_states = (
            None if is_nully(ocm_inflight_states_str) else json.loads(in_dict["ocm_inflight_states"])
        )
        log_download_url = (
            in_dict["log_download_url"] if is_valid_url(in_dict["log_download_url"]) else None
        )
        
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


# test_dict = {
#     'timestamp': "2023-07-26T01:22:03Z",
#     'cid': "myfancyclusterid",
#     'cname': "fancy-cluster",
#     'ocm_state': "ready",
#     'ocm_inflight_states': "[\"passed\",\"failed\"]",
#     'found_verifier_s3_logs': "TRUE",
#     'found_all_tests_passed': "FALSE",
#     'found_egress_failures': "NULL",
#     'log_download_url': "example.com/logs/dwYEaJQ0Og/"
# }
# print(vars(ClusterVerifierRecord.from_dict(test_dict)))

cvrs = []
with open(sys.argv[1], newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        cvrs.append(ClusterVerifierRecord.from_dict(row))

for cvr in cvrs:
    print(vars(cvr))
