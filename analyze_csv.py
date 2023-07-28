"""Analyze a CSV produced by the verifier_log_cronjob.sh and print the results"""
import csv
import sys

from models import ClusterVerifierRecord

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


cvrs = {}
with open(sys.argv[1], newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        cvr = ClusterVerifierRecord.from_dict(row)
        try:
            cvrs[cvr.cid] += cvr
        except KeyError:
            # First time we're seeing a CVR for this cluster ID; store it
            cvrs[cvr.cid] = cvr

for cid, cvr in cvrs.items():
    print(cid + ": " + repr(cvr))

print(len(cvrs))
