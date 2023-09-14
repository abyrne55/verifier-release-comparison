"""'CSV Analysis Python Script' settings. Configure these before running'"""

# Username and password for remote log HTTP server. Set to None if no auth needed
REMOTE_LOG_AUTH = ("username", "password")

# Name of the log file to parse for egress failures
REMOTE_LOG_FILE_NAME = "osd-network-verifier-logs.txt"

# Regular expression to use for capturing failed egress endpoints (should have a single
# capturing group)
REMOTE_LOG_EGRESS_REGEX_PATTERN = r"egressURL error\: ([\w\-\.]+\:\d+)\n"

# Regular expression to use for capturing other runtime errors (should have a single
# capturing group)
REMOTE_LOG_ERROR_REGEX_PATTERN = (
    r"network verifier error:\s*(exceeded max wait time for \w* waiter"
    r"|missing required permission [\w\d]*:[\w\d]*"
    r"|waiter state transitioned to Failure"
    r"|timed out waiting for the condition"
    r"|unable to cleanup [\w\s]*"
    r"|error performing [\w\d]*:[\w\d]*).*[\n$]"
)

# Regular expression to use for identifying internal customers (no capturing groups)
# Will be evaluated with the IGNORECASE flag
INTERNAL_CUSTOMER_REGEX_PATTERN = r"foo|bar"

# Set of egress endpoints that, if seen, should convert a false positive into a true
# positive. For example, we can assume that a cluster that blocks its Splunk forwarding
# URL will be considered "failed" even if OCM reports it as "ready"
FORCE_FAILURE_ENDPOINTS = set(
    [
        "inputs1.osdsecuritylogs.splunkcloud.com:9997",
        "http-inputs-osdsecuritylogs.splunkcloud.com:443",
    ]
)
