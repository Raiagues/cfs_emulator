# Test a fresh Linux host for native cFS development and CLI generation.
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /studio
COPY scripts/setup-native.sh scripts/setup-native.sh
COPY hardware/host_tools.py hardware/host_tools.py
RUN ./scripts/setup-native.sh
COPY . .
RUN test ! -e mission/sample_defs && test ! -e mission/build-flight && test ! -e cFS && python3 -m project.nasa_source
RUN --network=none ./start --no-ui project sync
CMD ["./start", "--no-ui", "build", "--target", "native"]
