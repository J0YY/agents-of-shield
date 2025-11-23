FROM kalilinux/kali-rolling

# Core recon tooling that the agent frequently calls
RUN apt-get update && apt-get install -y \
    curl \
    nmap \
    gobuster \
    wfuzz \
    dirb \
    dirbuster \
    seclists \
    apache2-utils \
    sshpass \
    html2text \
    unzip \
    python3-html2text

# Wordlist paths expected by prompts/tools
RUN mkdir -p /usr/share/wordlists && \
    ln -sf /usr/share/dirb/wordlists /usr/share/wordlists/dirb && \
    ln -sf /usr/share/dirbuster/wordlists /usr/share/wordlists/dirbuster && \
    ln -sf /usr/share/wfuzz/wordlist /usr/share/wordlists/wfuzz

# Install ProjectDiscovery's httpx binary for compatibility with the prompts
ARG HTTPX_VERSION=1.6.8
RUN ARCH="$(dpkg --print-architecture)" && \
    case "$ARCH" in \
        amd64) HTTPX_PKG="httpx_${HTTPX_VERSION}_linux_amd64.zip" ;; \
        arm64) HTTPX_PKG="httpx_${HTTPX_VERSION}_linux_arm64.zip" ;; \
        *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    curl -L "https://github.com/projectdiscovery/httpx/releases/download/v${HTTPX_VERSION}/${HTTPX_PKG}" -o /tmp/httpx.zip && \
    unzip /tmp/httpx.zip -d /tmp/httpx && \
    mv /tmp/httpx/httpx /usr/local/bin/httpx && \
    chmod +x /usr/local/bin/httpx && \
    rm -rf /tmp/httpx.zip /tmp/httpx

# Update and install Python and other dependencies
RUN apt-get update -y && \
    apt-get install -y python3 python3-pip iputils-ping net-tools

# Install build + CLI utilities needed by the agent
RUN pip install build --break-system-packages

# Copy your project files
COPY . /redteam/
WORKDIR /redteam

# Build and install your package
RUN python3 -m build && pip install dist/*.whl --break-system-packages

CMD ["bash"]
