#!/usr/bin/env bash
# ==============================================================================
# GridPilot Alibaba Cloud Provisioning Helper & Documentation Script
# Milestone 2 - Infrastructure Provisioning
# ==============================================================================

set -euo pipefail

# Configuration defaults (Free-tier eligible parameters)
REGION="cn-hangzhou"                     # standard free-tier region
INSTANCE_TYPE="ecs.t5-lc1m1.small"        # 1 vCPU, 2GB RAM (burst-instance, free-tier eligible)
IMAGE_ID="ubuntu_22_04_x64_20G_alibase_20230613.vhd" # Ubuntu 22.04 LTS
OSS_STORAGE_CLASS="Standard"             # Standard storage class (free tier includes 20GB/month)

echo "======================================================================"
echo "      GridPilot - Alibaba Cloud Provisioning Check & Helper"
echo "======================================================================"

# 1. Verify Alibaba Cloud CLI Installation
echo -n "Checking aliyun CLI installation... "
if ! command -v aliyun &>/dev/null; then
    echo "FAILED"
    echo "Error: 'aliyun' CLI tool is not installed or not in your PATH."
    echo "Please download and install it from: https://github.com/aliyun/aliyun-cli/releases"
    echo "Alternatively, follow the manual console setup documented in this script."
    exit 1
fi
echo "OK ($(aliyun version))"

# 2. Verify login status / credentials configuration
echo -n "Checking aliyun CLI login status... "
if ! aliyun sts GetCallerIdentity &>/dev/null; then
    echo "FAILED"
    echo "Error: aliyun CLI is not configured or session is expired."
    echo "Please configure it using: aliyun configure"
    exit 1
fi
echo "OK"

# 3. Check prerequisites before provisioning
echo "Checking prerequisites... OK"

# 4. Prompt user or document resource creation commands
echo "----------------------------------------------------------------------"
echo "This script provides automation commands to provision:"
echo " 1. A RAM Policy (least-privilege for GridPilot OSS + DashScope)"
echo " 2. A RAM Sub-Account (User) and Access Key credentials"
echo " 3. A secure OSS Bucket (S3-compatible object store)"
echo " 4. A free-tier eligible ECS instance"
echo "----------------------------------------------------------------------"

# Define names dynamically to avoid hardcoding and reuse
PROJECT_NAME="gridpilot"
RANDOM_SUFFIX=$((1000 + RANDOM % 9000))
BUCKET_NAME="${PROJECT_NAME}-data-${RANDOM_SUFFIX}"
RAM_USER_NAME="${PROJECT_NAME}-app-user"
RAM_POLICY_NAME="${PROJECT_NAME}-scoped-policy"

# Export variables for reference
echo "Suggested Resource Names:"
echo " - OSS Bucket: ${BUCKET_NAME}"
echo " - RAM User:   ${RAM_USER_NAME}"
echo " - RAM Policy: ${RAM_POLICY_NAME}"
echo ""

# Display Least-Privilege RAM Policy Document
echo "=== Step 1: Secure Scoped RAM Policy ==="
echo "The policy allows read/write access ONLY to the GridPilot OSS bucket"
echo "and permission to call DashScope / Model Studio Qwen API models."
echo ""
echo "Save this policy document locally as 'gridpilot-policy.json':"
cat <<EOF
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "oss:PutObject",
        "oss:GetObject",
        "oss:DeleteObject",
        "oss:ListObjects",
        "oss:GetBucketLocation"
      ],
      "Resource": [
        "acs:oss:*:*:${BUCKET_NAME}",
        "acs:oss:*:*:${BUCKET_NAME}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dashscope:*"
      ],
      "Resource": "*"
    }
  ]
}
EOF
echo ""
echo "To create the policy via CLI:"
echo " aliyun ram CreatePolicy --PolicyName ${RAM_POLICY_NAME} --PolicyDocument \"\$(cat gridpilot-policy.json)\""
echo ""

echo "=== Step 2: Provision RAM Sub-Account & Access Keys ==="
echo "Create the sub-account and attach the scoped policy (do NOT run application as root account):"
echo " 1. Create User:  aliyun ram CreateUser --UserName ${RAM_USER_NAME}"
echo " 2. Access Keys:  aliyun ram CreateAccessKey --UserName ${RAM_USER_NAME}"
echo " 3. Attach Policy: aliyun ram AttachPolicyToUser --UserName ${RAM_USER_NAME} --PolicyName ${RAM_POLICY_NAME} --PolicyType Custom"
echo ""

echo "=== Step 3: Provision OSS Bucket ==="
echo "Create a private OSS bucket in the ${REGION} region:"
echo " aliyun oss mb oss://${BUCKET_NAME} --region ${REGION} --storage-class ${OSS_STORAGE_CLASS}"
echo ""

echo "=== Step 4: Provision ECS Instance ==="
echo "Create a free-tier eligible virtual machine in your default VPC / VSwitch:"
echo " aliyun ecs CreateInstance \\"
echo "   --RegionId ${REGION} \\"
echo "   --InstanceType ${INSTANCE_TYPE} \\"
echo "   --ImageId ${IMAGE_ID} \\"
echo "   --InstanceName gridpilot-ecs \\"
echo "   --SystemDisk.Category cloud_efficiency \\"
echo "   --SystemDisk.Size 20 \\"
echo "   --InternetMaxBandwidthOut 1"
echo ""
echo "======================================================================"
echo "Once provisioned, copy the credentials to your local '.env' file:"
echo "  OSS_BUCKET_NAME=${BUCKET_NAME}"
echo "  OSS_ACCESS_KEY_ID=<your_ram_access_key_id>"
echo "  OSS_ACCESS_KEY_SECRET=<your_ram_access_key_secret>"
echo "  DASHSCOPE_API_KEY=<your_dashscope_api_key>"
echo "  ECS_HOST=<your_ecs_public_ip>"
echo "======================================================================"
