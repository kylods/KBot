# Build from a slim Debian/Linux image
FROM debian:stable-slim

# Copy our code into the image
COPY kbot.py kbot.py
COPY requirements.txt requirements.txt
COPY cogs/ cogs/

# Update apt
RUN apt update
RUN apt upgrade -y

# Install ffmpeg
RUN apt install -y ffmpeg

# Install build tooling
RUN apt install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev

# Download Python interpreter code and unpack it
RUN wget https://www.python.org/ftp/python/3.10.12/Python-3.10.12.tgz 
RUN tar -xf Python-3.10.*.tgz

# Build the Python interpreter
RUN cd Python-3.10.12 && ./configure --enable-optimizations && make && make altinstall

# Ensure pip is installed
RUN python3.10 -m ensurepip
RUN python3.10 -m pip install -r requirements.txt

# Run our Python script
CMD ["python3.10", "kbot.py"]