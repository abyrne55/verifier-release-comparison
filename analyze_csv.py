"""Analyze a CSV produced by the verifier_log_cronjob.sh and print the results"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from requests_cache import install_cache, NEVER_EXPIRE

# Enable HTTP caching globally before importing network-using modules
install_cache(
    ".vla-http-cache",
    backend="sqlite",
    expire_after=NEVER_EXPIRE,
    allowable_methods=["GET"],
)
# pylint: disable=wrong-import-position, C0103
from models import ClusterVerifierRecord, Outcome
from util import OCMClient, is_internal_customer

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
    "--internal-cx",
    action=argparse.BooleanOptionalAction,
    help=(
        "analyze ONLY data generated from internal customers' clusters. Conversely, "
        "--no-internal-cx only analyzes data from external customers' clusters. Set "
        "neither of these to analyze all data. NOTE: setting either flag will cause "
        "2-3 extra HTTP requests per cluster ID, heavily slowing processing. Also, "
        "the OCM_CONFIG environmental variable must point to a valid OCM credentials"
        "file"
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
arg_parser.add_argument(
    "--count",
    type=str,
    choices=["cluster_id", "subnet_id_set"],
    help=(
        "set the basic counting unit. By default, we count 2+ verifier records tagged "
        "with the same cluster ID as a single 'sample' after deduplication. Setting "
        "this to anything other than cluster_id will trigger a second round of "
        "deduplication where, for example, 2+ verifier records associated with the "
        "same set of subnet IDs AND OUTCOME (e.g., false positive) will be counted as "
        "one 'sample'"
    ),
    default="cluster_id",
)
args = arg_parser.parse_args()
since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
until_dt = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc)

# Read CSV and create a ClusterVerifierRecord (CVR) from each row
cvrs = {}
reader = csv.DictReader(args.csv_file)
for row in reader:
    try:
        cvr = ClusterVerifierRecord.from_dict(row)
    except KeyError as exc:
        print(f"WARN: failed to process {row}: {exc}", file=sys.stderr)
        continue

    # Filter out HCPs according to date bounding and presence of --(no-)hcp flag
    if (cvr.timestamp >= since_dt and cvr.timestamp <= until_dt) and (
        args.hcp is None or args.hcp == cvr.is_hostedcluster()
    ):
        try:
            cvrs[cvr.cid] += cvr
        except KeyError:
            # First time we're seeing a CVR for this cluster ID; store it
            cvrs[cvr.cid] = cvr
args.csv_file.close()

# Now for the expensive filtering: checking for internal vs. external customers
# If we have to do this, we use a somewhat-clunky caching approach to avoid making
# extraneous requests to OCM
if args.internal_cx is not None:
    filtered_cvrs = []
    org_id_cache = {}  # Maps org IDs to bools (True == int. cx.)
    ocm_client = OCMClient()
    cvrs_thrown_away = 0
    # Iterate over a list-copy of the cvrs dict (so that we can delete stuff)
    for cid, cvr in list(cvrs.items()):
        try:
            org_id = cvr.get_organization_id(ocm_client)
            try:
                cvr_is_int_cx = org_id_cache[org_id]
            except KeyError:
                # First time we're seeing this org_id; cache internal cx status
                cvr_is_int_cx = is_internal_customer(ocm_client, org_id)
                org_id_cache[org_id] = cvr_is_int_cx

            # Delete CVRs whose internal status doesn't match args.internal_cx
            if not cvr_is_int_cx == args.internal_cx:
                del cvrs[cid]
        except ValueError as exc:
            cvrs_thrown_away += 1
            del cvrs[cid]
    if cvrs_thrown_away > 0:
        print(
            f"WARN: discarded data from {cvrs_thrown_away} clusters due to inability "
            "to determine owner"
        )

# Create a dict of empty lists where every enumerated value of Outcome becomes a key
outcomes = {o: [] for o in Outcome}

# Sort each CVR into the dictionary created above based on outcome
for _, cvr in cvrs.items():
    try:
        outcomes[cvr.get_outcome()].append(cvr)
    except KeyError:
        # We might hit this for NoneType outcomes
        outcomes[cvr.get_outcome()] = [cvr]

# Deduplicate again based on the value of --count
if args.count == "cluster_id":
    # No further deduplication needed
    outcomes_view = outcomes
    unit_friendly_name = "Clusters"
if args.count == "subnet_id_set":
    # outcomes_view becomes a dict of sets of frozensets of subnet IDs (keys unchanged)
    outcomes_view = {
        o: {cvr.get_subnet_id_set() for cvr in cvr_list}
        for o, cvr_list in outcomes.items()
    }
    unit_friendly_name = "Subnet ID Sets"
    print(
        "INFO: performance metrics (e.g., FPR, precision) will NOT be calculated, "
        "as they're invalid/meaningless when deduplicating by network (--count=subnet_id_sets)"
    )


# Statistical Measures
# See https://en.wikipedia.org/wiki/Sensitivity_and_specificity
tp = len(outcomes_view[Outcome.TRUE_POSITIVE])
tn = len(outcomes_view[Outcome.TRUE_NEGATIVE])
fn = len(outcomes_view[Outcome.FALSE_NEGATIVE])
fp = len(outcomes_view[Outcome.FALSE_POSITIVE])
errors = len(outcomes_view[Outcome.ERROR])

print(f"Total {unit_friendly_name},{tp + tn + fn + fp + errors},")
print(
    f"True Negatives,{tn},\nFalse Negatives,{fn},\nTrue Positives,{tp},\n"
    f"False Positives,{fp},\nErrors,{errors},"
)

# Calculate metrics only if counting cluster IDs (other units produce
# meaningless/statistically-invalid numbers due to deduplication)
if args.count == "cluster_id":
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
