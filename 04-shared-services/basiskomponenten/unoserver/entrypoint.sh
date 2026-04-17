#!/bin/sh
set -e

timeout="${CONVERSION_TIMEOUT:-120}"

case "$timeout" in
  ''|*[!0-9]*)
    echo "CONVERSION_TIMEOUT must be an integer (got: '$timeout')." >&2
    exit 1
    ;;
esac

exec unoserver --interface 0.0.0.0 --conversion-timeout "$timeout"
