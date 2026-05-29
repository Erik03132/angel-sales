#!/bin/bash
# Kill existing baresip (the one answering incoming calls)
pkill -9 baresip 2>/dev/null
sleep 2

# Start fresh baresip to make an outbound call
# -t 120: quit after 120 seconds (enough for the call)
# -e: execute dial command at startup
/usr/bin/baresip -f /root/.baresip -t 120 -e "dial sip:+79859234644@vpbx400161137.mangosip.ru" 2>&1 &
BPID=$!

# Wait for call to complete
sleep 70
kill $BPID 2>/dev/null
