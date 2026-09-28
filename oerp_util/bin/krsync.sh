#!/bin/bash

if [ -z "$KRSYNC_STARTED" ]; then
    export KRSYNC_STARTED=true
    exec rsync --blocking-io --rsh "$0" $@
fi

# Running as --rsh
context=''
pod=$1
shift

# If user uses pod@namespace, rsync passes args as: {us} -l pod namespace ...
if [ "X$pod" = "X-l" ]; then
    pod=$1
    shift
    if [[ "$1" == *.* ]]; then
        context="--context=${1#*.}  --namespace=${1%.*}"
    else
        context="-n $1"
    fi
    shift
fi

exec kubectl $context exec -i $pod -- "$@"