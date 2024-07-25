"""'JSON Analysis Python Script' settings. Configure these before running'"""

# Regular expression to use for capturing failed egress endpoints (should have a single
# capturing group)
EGRESS_URL_REGEX_PATTERN = r"egressURL error\: (?:[a-z]{3,5}:\/\/)?([\w\-\.]+\:\d+)\s"

# Regular expression to use for capturing other runtime errors (should have a single
# capturing group)
VERIFIER_ERROR_REGEX_PATTERN = (
    r"network verifier error:\s*(exceeded max wait time for \w* waiter"
    r"|missing required permission [\w\d]*:[\w\d]*"
    r"|waiter state transitioned to Failure"
    r"|timed out waiting for the condition"
    r"|unable to cleanup [\w\s]*"
    r"|error performing [\w\d]*:[\w\d]*).*[\n$]"
)

# Set of egress endpoints that should be ignored entirely. This might be useful if the
# endpoint was flaky/unreliable during data collection
IGNORED_ENDPOINTS = set(
    [
        "example.com"
    ]
)
