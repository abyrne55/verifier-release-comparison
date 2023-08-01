"""'CSV Analysis Python Script' settings. Configure these before running'"""

# Username and password for remote log HTTP server. Set to None if no auth needed
REMOTE_LOG_AUTH = ("username", "password")

# Name of the log file to parse for egress failures
REMOTE_LOG_FILE_NAME = "osd-network-verifier-logs.txt"

# Regular expression to use for capturing failed egress endpoints (should have a single
# capturing group)
REMOTE_LOG_REGEX_PATTERN = r"egressURL error\: ([\w\-\.]+\:\d+)\n"

# Set of egress endpoints that, if seen, should convert a false positive into a true
# positive. For example, we can assume that a cluster that blocks its Splunk forwarding
# URL will be considered "failed" even if OCM reports it as "ready"
FORCE_FAILURE_ENDPOINTS = set(["inputs1.osdsecuritylogs.splunkcloud.com:9997"])
