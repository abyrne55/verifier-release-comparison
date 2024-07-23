# verifier-release-comparison
Scripts for comparing logs of old and new osd-network-verifier releases 

*Based on [abyrne55/verifier-log-analysis](https://github.com/abyrne55/verifier-log-analysis)*

## JSON Analysis Python Script
`analyze_json.py` will analyze JSON blobs produced by a separate tool and print the results. To test, create a file at the root of the repo called `test.json` that looks like the following
```json
{
  "duration": #ofseconds,
  "cid": "xxxxx",
  "osdctl_version": “0.34”,
  "probe": "legacy",
  “arch”:  “x86”,
  "error": "string",
  "logpath": "Hello World",
  "output": "execution output string"
}
```
Then run `make build test` to build and run a UBI9 container image containing the tool. If you'd rather not use Docker/Podman, you can also run the script directly using Python 3.9: `python3 analyze_json.py test.json`