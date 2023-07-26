import csv
import json
import re
import sys
import urllib
from datetime import datetime
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


class ClusterVerifierRecord:
    """Represents a single row in the CSV"""

    def __init__(
        self,
        timestamp: datetime,
        cid: str,
        cname: Optional[str],
        ocm_state: Optional[str],
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

    def __gt__(self, other):
        return self.timestamp > other.timestamp

    def __lt__(self, other):
        return self.timestamp < other.timestamp

    @classmethod
    def from_dict(cls, in_dict: dict[str, str]):
        """Create an instance of this class from a dictionary produced by csv.DictReader"""
        timestamp = datetime.fromisoformat(in_dict["timestamp"].replace("Z", "+00:00"))
        cid = in_dict["cid"]
        cname = in_dict["cname"]
        ocm_state = in_dict["ocm_state"]
        found_verifier_s3_logs = csv_bool_to_bool(in_dict["found_verifier_s3_logs"])
        found_all_tests_passed = csv_bool_to_bool(in_dict["found_all_tests_passed"])
        found_egress_failures = csv_bool_to_bool(in_dict["found_egress_failures"])
        log_download_url = (
            in_dict["log_download_url"] if is_valid_url(in_dict["log_download_url"]) else None
        )
        try:
            ocm_inflight_states = json.loads(in_dict["ocm_inflight_states"])
        except json.decoder.JSONDecodeError:
            ocm_inflight_states = None

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
