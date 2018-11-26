FROM clusterhq/fio-tool
WORKDIR /mnt
CMD ["fio", "--blocksize=8k", "--directory=/mnt", "--filename=test", "--ioengine=libaio", "--readwrite=randwrite", "--size=30G", "--name=test", "--verify=meta", "--do_verify=1", "--verify_pattern=0xdeadbeef", "--direct=1", "--gtod_reduce=1", "--iodepth=128", "--randrepeat=1", "--disable_lat=0", "--gtod_reduce=0"]
