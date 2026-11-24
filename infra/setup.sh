#!/usr/bin/env bash
# One-time AWS setup in us-west-2: the harness execution role and the before_tool_call hook (Lambda).
# Uses the current AWS credentials (set AWS_PROFILE if needed). Prints the value to export afterwards.
set -euo pipefail
cd "$(dirname "$0")"
export AWS_PAGER=""
R=us-west-2
A=$(aws sts get-caller-identity --query Account --output text)
ROLE=agents-your-rules-harness-role
FN=ayr-before-tool-call

# Harness execution role: model calls, logs, workload identity, and invoking the hook. Nothing else.
aws iam get-role --role-name "$ROLE" >/dev/null 2>&1 || aws iam create-role --role-name "$ROLE" \
  --assume-role-policy-document "$(sed "s/ACCOUNT_ID/${A}/g" harness-trust.json)" >/dev/null
aws iam put-role-policy --role-name "$ROLE" --policy-name harness-exec \
  --policy-document "$(sed -e "s/ACCOUNT_ID/${A}/g" -e "s/REGION/${R}/g" harness-policy.json)"

# Hook Lambda (hook/hook.py).
aws iam get-role --role-name ayr-hook-lambda-role >/dev/null 2>&1 || {
  aws iam create-role --role-name ayr-hook-lambda-role --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name ayr-hook-lambda-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10; }
rm -f /tmp/ayr-hook.zip && (cd ../hook && zip -q /tmp/ayr-hook.zip hook.py)
if aws lambda get-function --function-name "$FN" --region "$R" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FN" --zip-file fileb:///tmp/ayr-hook.zip --region "$R" >/dev/null
else
  aws lambda create-function --function-name "$FN" --runtime python3.13 --handler hook.lambda_handler \
    --role "arn:aws:iam::${A}:role/ayr-hook-lambda-role" --zip-file fileb:///tmp/ayr-hook.zip --timeout 5 --region "$R" >/dev/null
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name hook-invoke --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"arn:aws:lambda:${R}:${A}:function:${FN}\"}]}"

echo "export AYR_HOOK_ARN=arn:aws:lambda:${R}:${A}:function:${FN}"
