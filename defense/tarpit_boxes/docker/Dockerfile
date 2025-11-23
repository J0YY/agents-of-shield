FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    LIBGUESTFS_BACKEND=direct

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dnsmasq-base \
        ebtables \
        fuse3 \
        iproute2 \
        iptables \
        kmod \
        jq \
        libguestfs-tools \
        libnss3 \
        libvirt-clients \
        libvirt-daemon \
        libvirt-daemon-system \
        linux-image-generic \
        nftables \
        openssh-client \
        pkg-config \
        python3 \
        python3-pip \
        python3-setuptools \
        python3-wheel \
        python3-libvirt \
        qemu-kvm \
        qemu-utils \
        virtiofsd \
        socat \
        virtinst \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
        asyncssh \
        fusepy \
        openai \
        paramiko \
        websocket-client

WORKDIR /opt/tarpit

COPY images /opt/tarpit/images

COPY entrypoint.sh /opt/tarpit/
COPY fuse-fuckry.py /opt/tarpit/
COPY honey_manager_paramiko.py /opt/tarpit/
COPY requirements.txt /opt/tarpit/
COPY netcfg.yaml /opt/tarpit/
COPY id_ed25519 /opt/tarpit/
COPY id_ed25519.pub /opt/tarpit/
COPY libvirt /opt/tarpit/libvirt

RUN chmod +x /opt/tarpit/entrypoint.sh && \
    chown root:root /opt/tarpit/id_ed25519 && \
    chmod 600 /opt/tarpit/id_ed25519

ENTRYPOINT ["/opt/tarpit/entrypoint.sh"]
EXPOSE 2222

