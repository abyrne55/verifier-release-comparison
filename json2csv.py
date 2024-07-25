"""Convert JSON blobs produced by a network verifier batch-run tool into a CSV for easier manual analysis"""

import models
import json
import pandas as pd
import argparse

# Parse command line arguments
arg_parser = argparse.ArgumentParser(
    description="Convert JSON blobs produced by a network verifier batch-run tool into a CSV for easier manual analysis"
)
# argparse will call open() on csv_file automatically (no need to use "with open(...) as f")
arg_parser.add_argument(
    "json_path_in",
    type=argparse.FileType(),
    help="path to the JSON file produced by a network verifier batch-run tool",
)
args = arg_parser.parse_args()

loaded_json = json.load(args.json_path_in)
if len(loaded_json) == 0:
    print("ERR: JSON file empty")
    sys.exit(1)

list_of_dicts = []
if isinstance(loaded_json, dict):
    list_of_dicts.append(loaded_json)
elif isinstance(loaded_json, list):
    list_of_dicts = loaded_json
else:
    print("ERR: JSON is not a dict or a list of dicts")
    sys.exit(2)

list_of_cvrs = [models.ClusterVerifierRecord.from_dict(d) for d in list_of_dicts]

df = models.cvrs_to_dataframe(list_of_cvrs)
print(df.to_csv(index_label="idx").replace("set()", "{}"))
    