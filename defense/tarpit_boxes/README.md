1) Install docker
2) `python tpot.py list` list honeypots
3) `python tpot.py start <honeypot>` spawn honeypot - check tpotce/docker-compose.yml for the default port, use --ports to specify particular bindings
4) `python tpot.py stop` stop honeypots

You will need `docker`, `fuse`, `qemu`, `libfuse` and `libvirt` installed on your system