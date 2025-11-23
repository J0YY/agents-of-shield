#!/bin/bash
echo "Finding your host IP address for Docker access..."
echo ""
echo "Your host IP addresses (use the first non-127.0.0.1 one):"
ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print "  " $2}'
echo ""
echo "Testing connectivity from Docker..."
HOST_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}')
if [ -n "$HOST_IP" ]; then
  echo "Testing: http://$HOST_IP:3000"
  docker run --rm alpine/curl:latest curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://$HOST_IP:3000 2>&1 | tail -1
  echo ""
  echo "Use this IP in your attack task: http://$HOST_IP:3000"
else
  echo "Could not determine host IP"
fi
