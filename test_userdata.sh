#!/bin/bash
set -e -x

touch /tmp/xyzzy
echo "Did: touch /tmp/xyzzy"

echo "rm -rf /var/lib/cloud/*" | at now + 1 min
