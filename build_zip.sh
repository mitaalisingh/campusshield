#!/bin/sh
# Builds campusshield.zip for upload to AWS Lambda (Python 3.12+, handler: lambda_function.handler)
cd "$(dirname "$0")" && rm -f campusshield.zip && zip -r campusshield.zip core.py api.py lambda_function.py web >/dev/null && ls -la campusshield.zip
