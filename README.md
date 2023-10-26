# verifier-log-analysis
Scripts for one-off analysis of osd-network-verifier logs

## Logging Cronjob
`verifier_log_cronjob.sh` will pull osd-network-verifier logs from an S3 bucket and correlate them to OCM query responses, producing output that can be piped into a CSV file with the following headers.
```
timestamp,cid,cname,ocm_state,ocm_inflight_states,found_verifier_s3_logs,found_all_tests_passed,found_egress_failures,log_download_url
```
You'll need a Linux system with a cron daemon, bash, [jq](https://jqlang.github.io/jq/), [jd](https://github.com/josephburnett/jd), [ocm](https://github.com/openshift-online/ocm-cli), and the [AWS CLI](https://aws.amazon.com/cli/). If your AWS IAM is set up in a way that requires multi-factor authentication (MFA), you'll also need [oathtool](https://github.com/jaraco/oathtool). Finally, if you want pretty HTML versions of the CSV file, you'll also need [pandoc](https://pandoc.org/).

### Cronjob Installation
Fill in the `# Constants`  section of `verifier_log_cronjob.sh` according to the comments, and mark the file as executable. Ensure your `~/.aws/credentials` file contains a profile named "default" that's allowed to run `aws sts get-session-token`. 

Run the following lines to log into AWS and generate a first-run file listing, replacing `$MFA_ARN`, `$MFA_KEY`, and `$S3_BUCKET_NAME` with the values you filled into the `verifier_log_cronjob.sh`.
```bash
STS_JSON=$(aws sts get-session-token --serial-number $MFA_ARN --token-code $(oathtool -b --totp $MFA_KEY) --duration-seconds 900 --output=json --profile=default)
AWS_ACCESS_KEY_ID=$(echo $STS_JSON | jq -r ".Credentials.AccessKeyId")
AWS_SECRET_ACCESS_KEY=$(echo $STS_JSON | jq -r ".Credentials.SecretAccessKey")
AWS_SESSION_TOKEN=$(echo $STS_JSON | jq -r ".Credentials.SessionToken")
aws s3api list-objects-v2 --bucket $S3_BUCKET_NAME --output=json > /path/to/bucket_listing.latest.json
```
Finally, add the following lines to your crontab, modifying PATH such that it contains all the required utilities mentioned above, and skipping the last line if you don't need pretty HTML output.
```
PATH=/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin
*/15 * * * * timeout -k 30s 2m /path/to/verifier_log_cronjob.sh /path/to/bucket_listing.previous.json /path/to/bucket_listing.latest.json >> /path/to/report.csv
2,17,32,47 * * * * pandoc /path/to/report.csv -o /path/to/report.html --self-contained --css /path/to/table.css --metadata title="Network Verifier In-flight Report (as of `date --utc +\%FT\%RZ`)"
```
This will result in `verifier_log_cronjob.sh` running every 15 minutes with a 2 minute soft timeout (2.5min hard/SIGKILL timeout), followed by `pandoc` (for generating the pretty HTML file) two minutes later.


## CSV Analysis Python Script
`analyze_csv.py` will analyze a CSV produced by the cronjob above and print the results. To test, create a file at the root of the repo called `test.csv` that looks like the following
```
timestamp,cid,cname,ocm_state,ocm_inflight_states,found_verifier_s3_logs,found_all_tests_passed,found_egress_failures,log_download_url
2023-07-14T19:00:01Z,123456789abcdefg,cool-cluster,ready,"[""passed""]",TRUE,TRUE,FALSE,https://example.com/logs/IEw4o8xtBu/,
2023-07-14T20:00:02Z,987654321hijklmn,uncool-cluster,installing,"[""failed""]",TRUE,FALSE,TRUE,https://example.com/logs/IEdH0dSS87/,
2023-07-14T20:30:04Z,101010101opqrstuv,,,NULL,TRUE,TRUE,FALSE,https://example.com/logs/EA1oo5DpoY/,
2023-07-14T20:30:05Z,987654321hijklmn,uncool-cluster,error,"[""failed""]",TRUE,FALSE,TRUE,https://example.com/logs/IEdH0dSS87/,
```
Then copy `settings.py.template` to `settings.py` and adjust settings according to your needs. Finally, run `make build test` to build and run a UBI9 container image containing the tool. If you'd rather not use Docker/Podman, you can also run the script directly using Python 3.9: `python3 analyze_csv.py test.csv`. Note that you may need to run `pip3 install -r requirements.txt` first.

Run `python3 analyze_csv.py --help` for more details on runtime options.
```
$ python3 analyze_csv.py --help
usage: analyze_csv.py [-h] [--hcp | --no-hcp] [--internal-cx | --no-internal-cx] [--since ISO8601_DATETIME] [--until ISO8601_DATETIME] csv_file

Analyze CSVs produced by verifier_log_cronjob.sh and print the results

positional arguments:
  csv_file              path to the CSV file under analysis

options:
  -h, --help            show this help message and exit
  --hcp, --no-hcp       analyze ONLY data generated from HyperShift/HCP HostedClusters. Conversely, --no-hcp excludes all HostedCluster data. Set neither of these to analyze all data. NOTE: setting
                        either flag will cause an extra HTTP request percluster ID, likely slowing processing considerably
  --internal-cx, --no-internal-cx
                        analyze ONLY data generated from internal customers' clusters. Conversely, --no-internal-cx only analyzes data from external customers' clusters. Set neither of these to analyze
                        all data. NOTE: setting either flag will cause 2-3 extra HTTP requests per cluster ID, heavily slowing processing. Also, the OCM_CONFIG environmental variable must point to a
                        valid OCM credentialsfile
  --since ISO8601_DATETIME
                        ignore data collected before ISO8601_DATETIME (assumed UTC)
  --until ISO8601_DATETIME
                        ignore data collected after ISO8601_DATETIME (assumed UTC)
```