#!/usr/bin/python2
import os
import sys
import subprocess
import re
import smtplib
from email.mime.text import MIMEText
import logging
import datetime
import argparse

logger = logging.getLogger('fib')
hdlr = logging.FileHandler('/var/log/fib.log', 'w+')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.INFO)

# Run a two step btrfs balance to realocate chunks and free up space
#
# Usage: python script.py <mount_path> [cleanup|forcefree]
#   mount_path: path to the btrfs mount
#   cleanup: if provided stop any outstanding operation and exit

debug=False
MB=float(1024*1024)

# Temporarily set to always run rebalance
force=1

fs_low_pct=50
fs_high_pct=70

# Used/Allocated pct
optimal_usage_threshold=80

# Used/Allocated pct when fs is nearing full
optimal_usage_threshold_full=90

# dusage indicate how the target chunks are picked, for example:
# 10 means pick all chunks which have usage below 10% and relocate their data
dusage_default=0
dusage_oneplus=1
dusage_normal=10


def cleanup(mountpath):
    logger.info("Cleaning up any existing rebalance on: " +mountpath)

    try:
        out=subprocess.check_output(['btrfs', 'balance', 'cancel', mountpath])
    except subprocess.CalledProcessError as e:
        return


def evaluate_usage(mountpath, dryrun=False):
    dev_size=0
    dev_alloc=0
    dev_used=0
    data_size=0
    data_used=0
    meta_size=0
    meta_used=0
    syst_size=0
    syst_used=0
    free=0
    free_expected=0

    try:
        out=subprocess.check_output(['btrfs', 'fi', 'usage', '-b', mountpath])
    except subprocess.CalledProcessError as e:
        logger.error("Failed to retrieve FS usage")
        sys.exit(0)

    for line in out.splitlines():

        if not dev_size and re.match('^\s*Device size:', line):
            dev_size=line.split()[-1]

        if not dev_alloc and re.match('^\s*Device allocated:', line):
            dev_alloc=line.split()[-1]

        if not dev_used and re.match('^\s*Used:', line):
            dev_used=line.split()[-1]

        if not data_size and re.match('^Data,.*Size:', line):
            data_size=re.sub('[^0-9]', '', line.split()[1])
            data_used=re.sub('[^0-9]', '', line.split()[2])

        if not meta_size and re.match('^Metadata,.*Size:', line):
            meta_size=re.sub('[^0-9]', '', line.split()[1])
            meta_used=re.sub('[^0-9]', '', line.split()[2])

        if not syst_size and re.match('^System,.*Size:', line):
            syst_size=re.sub('[^0-9]', '', line.split()[1])
            syst_used=re.sub('[^0-9]', '', line.split()[2])

        if not free and re.match('^\s*Free ', line):
            free=re.sub('[^0-9]', '', line.split()[-1])

    if debug is True:
        print ("dev_size ", dev_size)
        print ("dev_alloc", dev_alloc)
        print ("dev_used ", dev_used)
        print ("data_size", data_size)
        print ("data_used", data_used)
        print ("meta_size", meta_size)
        print ("meta_size", meta_size)
        print ("free", free)

    # Expected free based on what is used
    free_expected=int(dev_size)-int(dev_used)

    # This delta represents space locked by outstanding frees
    delta=float((float(free_expected) - float(free)) / MB)
    delta_pct=float(100 * (float(free_expected) - float(free)) / float(free_expected))

    # Used over allocated, a low number indicates empty unused chunks
    device_alloc_pct=float(100 * float(dev_alloc) / float(dev_size))
    total_used_pct=float(100 * float(dev_used) / float(dev_alloc))
    datapart_used_pct=float(100 * float(data_used) / float(data_size))
    metapart_used_pct=float(100 * float(meta_used) / float(meta_size))

    if dryrun is True:
        print("Allocation is {0:.2f}% of Size".format(device_alloc_pct))
        print("FS free: {0:.2f}".format(float(free) / MB) + "MB Expected: {0:.2f}".format(float(free_expected) / MB) + "MB")
        print("Free delta is: " + "{0:.2f}".format(delta)  + "MB (" + "{0:.2f}%".format(float(delta_pct)) + ")")
        print("Overall used is {0:.2f}% of allocation".format(total_used_pct))
        print("Data partition used is {0:.2f}% of allocation".format(datapart_used_pct))
        print("Metadata partition used is {0:.2f}% of allocation".format(metapart_used_pct))
    else:        
        logger.info("Allocation is {0:.2f}% of Size".format(device_alloc_pct))
        logger.info("FS free: {0:.2f}".format(float(free) / MB) + "MB Expected: {0:.2f}".format(float(free_expected) / MB) + "MB")
        logger.info("Free delta is: " + "{0:.2f}".format(delta)  + "MB (" + "{0:.2f}%".format(float(delta_pct)) + ")")
        logger.info("Overall used is {0:.2f}% of allocation".format(total_used_pct))
        logger.info("Data partition used is {0:.2f}% of allocation".format(datapart_used_pct))
        logger.info("Metadata partition used is {0:.2f}% of allocation".format(metapart_used_pct))

    return device_alloc_pct, (100 * float(dev_used) / float(dev_alloc))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mountpath', help='Mountpath of Filesystem to be re-balanced')
    parser.add_argument('--cleanup', type=bool, help='Cleanup any existing rebalance', default=False)
    parser.add_argument('--forcefree', type=bool, help='Run a rebalance to free chunks >10 percent used', default=False)
    parser.add_argument('--sender', help='Sender email address')
    parser.add_argument('--receiver', help='Receiver email address')
    parser.add_argument('--smtpserver', help='SMTP server address')
    parser.add_argument('--dryrun', type=bool, help='Do a dryrun to check current state only', default=False)
    return parser.parse_args()


def send_email(sender, receiver, smtp_server):
    fp = open('/var/log/fib.log', 'rb')
    msg = MIMEText(fp.read())
    fp.close()
    now = datetime.datetime.now()
    curr_update = now.isoformat()
    msg['Subject'] = 'Filesystem balance update '+curr_update
    msg['From'] = sender
    msg['To'] = receiver

    # Send the message via our own SMTP server, but don't include the
    # envelope header.
    s = smtplib.SMTP(smtp_server)
    s.sendmail(sender, [receiver], msg.as_string())
    s.quit()


def main():
    args = parse_args()
    if args.mountpath:
        mountpath = args.mountpath
        logger.info("Using mount path: " + mountpath)
    else:
        print("[ERROR]: Need a mountpath to run rebalance")
        sys.exit(1)

    if args.cleanup is True:
        cleanup(mountpath)
        sys.exit(0)
    if args.dryrun is True:
        evaluate_usage(mountpath,True)
        sys.exit(0)

    if args.forcefree is True:
        dusage_opts=[dusage_default, dusage_oneplus, dusage_normal]
    else:
        dusage_opts=[dusage_default, dusage_oneplus]

    for i in range(0,len(dusage_opts)):
        logger.info("Executing PASS: "+ str(i+1))
        alloc_pct, usage_pct = evaluate_usage(mountpath)
        threshold = optimal_usage_threshold

        # Do nothing on FS with low usage
        if alloc_pct <= fs_low_pct:
            break

        # If the percent used of allocated is below threshold then start rebalance
        if alloc_pct > fs_low_pct:
            if force or usage_pct <= threshold:
                dusage="-dusage="+str(dusage_opts[i])
                logger.info("Starting rebalance pass on: " + mountpath + " dusage = " + str(dusage_opts[i]))
                try:
                    out=subprocess.check_output(['btrfs', 'balance', 'start', dusage, mountpath])
                except subprocess.CalledProcessError as e:
                    logger.error("Failed to start rebalance")
                logger.info(out)

    # Finally, see if need to send email
    if (args.receiver is not None and \
        args.sender is not None and \
        args.smtpserver is not None):
        send_email(sender=args.sender, receiver=args.receiver, smtp_server=args.smtpserver)
    else:
        with open('/var/log/fib.log', 'r') as fin:
            print(fin.read())
        fin.close()

if __name__ == '__main__':
    main()
