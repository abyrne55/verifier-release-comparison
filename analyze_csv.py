"""Analyze a CSV produced by the verifier_log_cronjob.sh and print the results"""
import argparse
import csv
import sys

from models import ClusterVerifierRecord, Outcome

arg_parser = argparse.ArgumentParser(
    description="Analyze CSVs produced by verifier_log_cronjob.sh and print the results"
)
arg_parser.add_argument(
    "csv_file",
    type=argparse.FileType(encoding="utf-8"),
    nargs=1,
    help="path to the CSV file under analysis",
)
arg_parser.add_argument(
    "--hcp",
    action=argparse.BooleanOptionalAction,
    help=(
        "analyze ONLY data generated from HyperShift/HCP HostedClusters. "
        "Conversely, --no-hcp excludes all HostedCluster data. Set "
        "neither of these to analyze all data"
    ),
)
arg_parser.add_argument(
    "--since",
    metavar="ISO8601_DATETIME",
    type=str,
    help="ignore data collected before ISO8601_DATETIME",
)
arg_parser.add_argument(
    "--until",
    metavar="ISO8601_DATETIME",
    type=str,
    help="ignore data collected after ISO8601_DATETIME",
)

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


print(f"Total deduplicated records: {len(cvrs)}")

outcomes = {}

for _, cvr in cvrs.items():
    try:
        outcomes[cvr.get_outcome()].append(cvr)
    except KeyError:
        outcomes[cvr.get_outcome()] = [cvr]

# pylint: disable=consider-using-dict-items
for oc in outcomes:
    print(f"{oc}: {len(outcomes[oc])}")

# Statistical Measures
# See https://en.wikipedia.org/wiki/Sensitivity_and_specificity
tp = len(outcomes[Outcome.TRUE_POSITIVE])
tn = len(outcomes[Outcome.TRUE_NEGATIVE])
fn = len(outcomes[Outcome.FALSE_NEGATIVE])
fp = len(outcomes[Outcome.FALSE_POSITIVE])

print(
    f"True Negatives,{tn}\nFalse Negatives,{fn}\nTrue Positives,{tp}\nFalse Positives,{fp}"
)

fdr = fp / (fp + tp)
fpr = fp / (fp + tn)
f1 = (2 * tp) / (2 * tp + fp + fn)
acc = (tp + tn) / (tp + tn + fp + fn)
precision = tp / (tp + fp)
recall = tp / (tp + fn)
specificity = tn / (tn + fp)

print(
    f"FDR: {fdr:.1%} | FPR: {fpr:.1%} | Precision: {precision:.1%} | "
    f"Recall (sensitivity): {recall:.1%}"
)
print(f"F1: {f1:.1%} | ACC: {acc:.1%} | Specificity: {specificity:.1%}")

print("False Positives")
fp_endpoints = {}
for cvr in outcomes[Outcome.FALSE_POSITIVE]:
    print(
        f"{cvr.log_download_url} {cvr.is_hostedcluster()}: {repr(cvr)}"
        f"{repr(cvr.get_egress_failures())}"
    )
    for ep in cvr.get_egress_failures():
        try:
            fp_endpoints[ep] += 1
        except KeyError:
            fp_endpoints[ep] = 1

print(repr(fp_endpoints))
