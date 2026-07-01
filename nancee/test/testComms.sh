#!/usr/bin/env bash

set -uo pipefail

can0_listener_out="/tmp/can0-listener$$"
can1_listener_out="/tmp/can1-listener$$"
can0_candump_pid=""
can1_candump_pid=""

if [[ "$EUID" -ne 0 ]]; then
    echo "Run with sudo: sudo $0"
    exit 1
fi

get_can_gruent() {
    ip -d link show |
        grep "can state" |
        sed -e 's/.*state //g' -e 's/ restart.*//g' |
        sort -u |
        wc -l
}

stop_candump() {
    if [[ -n "$can0_candump_pid" ]]; then
        kill -INT "$can0_candump_pid" 2>/dev/null || true
        wait "$can0_candump_pid" 2>/dev/null || true
        can0_candump_pid=""
    fi

    if [[ -n "$can1_candump_pid" ]]; then
        kill -INT "$can1_candump_pid" 2>/dev/null || true
        wait "$can1_candump_pid" 2>/dev/null || true
        can1_candump_pid=""
    fi
}

can_deadly() {
    stop_candump

    pkill -INT -x candump 2>/dev/null || true

    rm -f \
        "$can0_listener_out" \
        "$can1_listener_out"

    ip link set can0 down 2>/dev/null || true
    ip link set can1 down 2>/dev/null || true

    sleep 2
}

can_opener() {
    local count=0
    local can_gruent

    rm -f \
        "$can0_listener_out" \
        "$can1_listener_out"

    ip link set can0 type can bitrate 500000 restart-ms 100
    ip link set can1 type can bitrate 500000 restart-ms 100

    ip link set can0 up
    ip link set can1 up

    can_gruent="$(get_can_gruent)"

    while [[ "$count" -lt 3 && "$can_gruent" -gt 1 ]]; do
        echo "WARN: CAN devices are not in the same state; restarting CAN bus."

        ip link set can0 down
        ip link set can1 down

        sleep 1

        ip link set can0 up
        ip link set can1 up

        sleep 2

        count=$((count + 1))
        can_gruent="$(get_can_gruent)"
    done

    candump -f "$can0_listener_out" can0 &
    can0_candump_pid=$!

    candump -f "$can1_listener_out" can1 &
    can1_candump_pid=$!

    sleep 2
}

rpm_check() {
    echo "Sending RPM request from can1..."
    cansend can1 7DF#02010C0000000000

    sleep 1

    echo "Sending simulated ECU RPM response from can0..."
    cansend can0 7E8#04410C0FA0000000
}

rpm_test() {
    echo
    echo "----- can0 listener output -----"
    cat "$can0_listener_out"

    echo
    echo "----- can1 listener output -----"
    cat "$can1_listener_out"

    echo
    echo "----- Test results -----"

    if grep -Eq \
        'can0[[:space:]]+7DF#02010C0000000000' \
        "$can0_listener_out"
    then
        echo "PASS: can0 received the RPM request sent from can1."
    else
        echo "FAIL: can0 did not receive the RPM request from can1."
        return 2
    fi

    if grep -Eq \
        'can1[[:space:]]+7E8#04410C0FA0000000' \
        "$can1_listener_out"
    then
        echo "PASS: can1 received the ECU response sent from can0."
    else
        echo "FAIL: can1 did not receive the ECU response from can0."
        return 3
    fi

    echo "PASS: CAN communication worked in both directions."
}

trap can_deadly EXIT

can_deadly
can_opener
rpm_check

sleep 2

stop_candump
rpm_test
