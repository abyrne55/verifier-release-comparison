#!/bin/bash
# Cronjob for fetching osd-network-verifier logs uploaded to an S3 bucket and comparing them to OCM's records
# Run this periodically, every 30 minutes perhaps
# Pre-requisite: have an AWS CLI profile named "default" that allows generation of session tokens (as most
# operations requires MFA) using an MFA "device"'s ARN and a TOTP (we use oathtool for TOTP-generation)
set -uo pipefail

# Constants (!!fill these in before running!!)
S3_BUCKET_NAME= # name of the s3 bucket containing the logs
MFA_ARN= # ARN of the multifactor device, e.g., arn:aws:iam::1234567890:mfa/mytoken
MFA_KEY= # Secret key shown when enrolling an MFA device
TMP_DIR_BASE=/tmp # where to put temporary files (no trailing slash)
TMP_DIR_BASE_URL= # base URL (no trailing slash) of $TMP_DIR_BASE if accessible remotely or "" if not

# Set up transient dir
TRANSIENT_DIR=$TMP_DIR_BASE/transient_clusters
mkdir -p $TRANSIENT_DIR

# Ensure proper arguments provided
BUCKET_LS_OLD="${1}"
BUCKET_LS_NEW="${2}"
if [[ -z "${BUCKET_LS_NEW}" ]]; then
  echo "Specify JSON files containing the 'old' and 'new' listings of the S3 bucket containing osd-network-verifier logs (JSON files will be created if necessary), and this script will output records based on any new files"
  echo "Usage: ${0} OLD_BUCKET_LISTING_JSON_FILE NEW_BUCKET_LISTING_JSON_FILE"
  echo "Will output CSV lines with the following column headers:"
  echo "timestamp,cid,cname,ocm_state,ocm_inflight_states,found_verifier_s3_logs,found_all_tests_passed,found_egress_failures,log_download_url"
  echo "  timestamp: ISO-8601 timestamp, e.g., '2023-07-14T17:08:32Z'"
  echo "  cid: internal cluster ID"
  echo "  cname: name of the cluster as listed in OCM, or NULL if cluster not found in OCM"
  echo "  ocm_state: state of the cluster as listed in OCM, or NULL if cluster not found in OCM"
  echo "  ocm_inflight_states: JSON array of any in-flight checks OCM has on file for this cluster, or NULL if none found"
  echo "  found_verifier_s3_logs: TRUE if verifier output logs were found in S3, otherwise FALSE"
  echo "  found_all_tests_passed: NULL if no logs downloaded, TRUE if 'All tests passed!' was found in the downloaded logs, otherwise FALSE"
  echo "  found_egress_failures: NULL if no logs downloaded, TRUE if 'egress failures found' was found in the downloaded logs, otherwise FALSE"
  echo "  log_download_url: URL of the temporary dir to which logs were downloaded, for audit/debugging purposes"
  exit 1
fi

# Set env-vars with AWS CLI creds
STS_JSON=$(aws sts get-session-token --serial-number $MFA_ARN --token-code $(oathtool -b --totp $MFA_KEY) --duration-seconds 900 --output=json --profile=default)
export AWS_ACCESS_KEY_ID=$(echo $STS_JSON | jq -r ".Credentials.AccessKeyId")
export AWS_SECRET_ACCESS_KEY=$(echo $STS_JSON | jq -r ".Credentials.SecretAccessKey")
export AWS_SESSION_TOKEN=$(echo $STS_JSON | jq -r ".Credentials.SessionToken")

process_cluster_id () {
  TMP_DIR=`mktemp -dp $TMP_DIR_BASE`
  CLUSTER_ID="$1"
  
  # Print timestamp and cid columns
  echo -n "`date --utc +%FT%H:%M:%SZ`,${CLUSTER_ID},"
  
  # Download OCM's description of this cluster (if any)
  ocm describe cluster --json $CLUSTER_ID >$TMP_DIR/desc.json 2>/dev/null
  
  # Report cluster name, state, and inflight states, if they exist in OCM
  OCM_CLUSTER_NAME=$(cat $TMP_DIR/desc.json | jq -r .name) \
    && echo -n "$OCM_CLUSTER_NAME," || echo -n "NULL,"
  OCM_CLUSTER_STATE=$(cat $TMP_DIR/desc.json | jq -r .state) \
    && echo -n "$OCM_CLUSTER_STATE," || echo -n "NULL,"
  OCM_INFLIGHT_STATES=$(ocm get /api/clusters_mgmt/v1/clusters/$CLUSTER_ID/inflight_checks 2>/dev/null | jq -Mc '[ .items[].state ]') \
    && echo -n "\"${OCM_INFLIGHT_STATES//[\"]/\"\"}\"," || echo -n "NULL,"
  
  # If cluster is in a transient state, record it such that it's checked again in the next run
  if [ -n "$OCM_CLUSTER_STATE" ] && [ "$OCM_CLUSTER_STATE" != "ready" ] && [ "$OCM_CLUSTER_STATE" != "error" ]; then
    touch $TRANSIENT_DIR/$CLUSTER_ID
  fi

  # Download logs from S3 and report status
  if [ -z "`aws s3 cp s3://$S3_BUCKET_NAME/$CLUSTER_ID $TMP_DIR --recursive --include '*/osd-network-verifier-logs.txt'`" ]; then
    # No logs downloaded
    echo "FALSE,NULL,NULL,$TMP_DIR,"
    return
  fi

  # Logs found
  echo -n "TRUE,"
  LOG_PATHS=`find $TMP_DIR -name 'osd-network-verifier-logs.txt' -print`
  grep -q "All tests passed!" $LOG_PATHS && echo -n "TRUE," || echo -n "FALSE,"
  grep -q "egress failures found" $LOG_PATHS && echo -n "TRUE," || echo -n "FALSE,"
  
  # Print URL to temp dir
  [ -z "$TMP_DIR_BASE_URL" ] && echo "$TMP_DIR," || echo "$TMP_DIR_BASE_URL/`basename $TMP_DIR`/,"
  
  # Done, chmod $TMP_DIR so it can be read remotely
  chmod 755 $TMP_DIR
}

# If a "new" bucket listing file already exists and has size > 0, turn it into the "old"
if [ -s "${BUCKET_LS_NEW}" ]; then
  cp ${BUCKET_LS_NEW} ${BUCKET_LS_OLD}
fi

# Ensure old bucket file exists
if [ ! -s "${BUCKET_LS_OLD}" ]; then
  echo "WARN: 'old' bucket listing file doesn't exist, so creating an empty one" 1>&2
  echo "{}" > $BUCKET_LS_OLD
fi

# Download new bucket listing
aws s3api list-objects-v2 --bucket $S3_BUCKET_NAME --output=json > $BUCKET_LS_NEW

# Diff old and new, extracting just unique cluster IDs
NEW_CLUSTER_IDS=`jd -set $BUCKET_LS_OLD $BUCKET_LS_NEW | grep -e "^+ " | cut -sd' ' -f2- | jq -r '.Key' | cut -sd'/' -f1 | sort -u` 

# Execute on new clusters
for ID in $NEW_CLUSTER_IDS; do
  process_cluster_id $ID
done

# Execute on previously-seen transient clusters (at least 5 minutes old)
for ID_PATH in `find $TRANSIENT_DIR -type f -mmin +5`; do
  rm $ID_PATH
  process_cluster_id `basename $ID_PATH`
done
 
