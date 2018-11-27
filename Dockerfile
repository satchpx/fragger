FROM clusterhq/fio-tool
COPY bin/ /opt/bin/
RUN chmod +x /opt/bin/*
WORKDIR /mnt
CMD ["/opt/bin/run-fio"]
