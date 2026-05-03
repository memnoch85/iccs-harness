#!/bin/bash
stty -F /dev/serial0 115200 raw -echo
stdbuf -oL cat /dev/serial0 | while read -r line; do
  echo "$line" > flatFileCommsTest.log
done
