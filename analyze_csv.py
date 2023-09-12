"""Analyze a CSV produced by the verifier_log_cronjob.sh and print the results"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from multiprocessing import Manager

from models import ClusterVerifierRecord, Outcome

# Parse command line arguments
arg_parser = argparse.ArgumentParser(
    description="Analyze CSVs produced by verifier_log_cronjob.sh and print the results"
)
# argparse will call open() on csv_file automatically (no need to use "with open(...) as f")
arg_parser.add_argument(
    "csv_file",
    type=argparse.FileType(),
    help="path to the CSV file under analysis",
)
arg_parser.add_argument(
    "--hcp",
    action=argparse.BooleanOptionalAction,
    help=(
        "analyze ONLY data generated from HyperShift/HCP HostedClusters. Conversely, "
        "--no-hcp excludes all HostedCluster data. Set neither of these to analyze "
        "all data. NOTE: setting either flag will cause an extra HTTP request per"
        "cluster ID, likely slowing processing considerably"
    ),
)
arg_parser.add_argument(
    "--since",
    metavar="ISO8601_DATETIME",
    type=str,
    help="ignore data collected before ISO8601_DATETIME (assumed UTC)",
    default=datetime.isoformat(datetime.min),
)
arg_parser.add_argument(
    "--until",
    metavar="ISO8601_DATETIME",
    type=str,
    help="ignore data collected after ISO8601_DATETIME (assumed UTC)",
    default=datetime.isoformat(datetime.max),
)
args = arg_parser.parse_args()
since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
until_dt = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc)

# Read CSV and create a ClusterVerifierRecord (CVR) from each row
cvrs = {}
with Manager() as manager:
    # Use a "dict manager" for our HCP cache (futureproofing against multiprocessing)
    hcp_cache = manager.dict()

    reader = csv.DictReader(args.csv_file)
    for row in reader:
        try:
            cvr = ClusterVerifierRecord.from_dict(row)
        except KeyError as exc:
            print(f"WARN: failed to process {row}: {exc}", file=sys.stderr)
            continue

        # Filter out HCPs according to date bounding and presence of --(no-)hcp flag
        if (cvr.timestamp >= since_dt and cvr.timestamp <= until_dt) and (
            args.hcp is None or args.hcp == cvr.is_hostedcluster(cache=hcp_cache)
        ):
            try:
                cvrs[cvr.cid] += cvr
            except KeyError:
                # First time we're seeing a CVR for this cluster ID; store it
                cvrs[cvr.cid] = cvr
args.csv_file.close()

print(f"Total Clusters,{len(cvrs)},")

# Create a dict of empty lists where every enumerated value of Outcome becomes a key
outcomes = {o: [] for o in Outcome}

# Sort each CVR into the dictionary created above based on outcome
for _, cvr in cvrs.items():
    try:
        outcomes[cvr.get_outcome()].append(cvr)
    except KeyError:
        # We might hit this for NoneType outcomes
        outcomes[cvr.get_outcome()] = [cvr]


# Statistical Measures
# See https://en.wikipedia.org/wiki/Sensitivity_and_specificity
tp = len(outcomes[Outcome.TRUE_POSITIVE])
tn = len(outcomes[Outcome.TRUE_NEGATIVE])
fn = len(outcomes[Outcome.FALSE_NEGATIVE])
fp = len(outcomes[Outcome.FALSE_POSITIVE])
errors = len(outcomes[Outcome.ERROR])

print(
    f"True Negatives,{tn},\nFalse Negatives,{fn},\nTrue Positives,{tp},\n"
    f"False Positives,{fp},\nErrors,{errors},"
)

# fdr = fp / (fp + tp)
fpr = fp / (fp + tn)
# f1 = (2 * tp) / (2 * tp + fp + fn)
# acc = (tp + tn) / (tp + tn + fp + fn)
precision = tp / (tp + fp)
# recall = tp / (tp + fn)
# specificity = tn / (tn + fp)
frustration_risk = fp / (tp + tn + fp + fn)

print(
    f"FPR,{fpr:.2%},\nPrecision,{precision:.2%},\n"
    f"Cx. Frustration Risk,{frustration_risk:.2%},"
)

fp_endpoints = {}
for cvr in outcomes[Outcome.FALSE_POSITIVE]:
    for ep in cvr.get_egress_failures():
        try:
            fp_endpoints[ep] += 1
        except KeyError:
            fp_endpoints[ep] = 1

fp_endpoints_str = " ".join(
    f"{k}={v}"
    for k, v in sorted(fp_endpoints.items(), key=lambda x: x[1], reverse=True)
)
print(f"FP Domains,{fp_endpoints_str},")
