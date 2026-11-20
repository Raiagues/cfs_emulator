# Fresh login for the README and native CLI checks. Nothing from the host mission is copied.
FROM debian:trixie-slim
ARG LEARNER_UID=1000
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates sudo \
    && useradd --uid "$LEARNER_UID" --create-home --shell /bin/bash learner \
    && echo 'learner ALL=(root) NOPASSWD: ALL' > /etc/sudoers.d/learner \
    && chmod 0440 /etc/sudoers.d/learner
USER learner
WORKDIR /home/learner
CMD ["/bin/bash"]
